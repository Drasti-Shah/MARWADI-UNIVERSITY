"""FastAPI server: Twilio voice webhooks -> Bhashini (Gujarati) <-> GPT-4o-mini.

Turn-based flow (low-latency demo):
  /voice    -> play Gujarati greeting, <Record> the caller's answer
  /process  -> download recording -> Bhashini ASR+translate (gu->en)
            -> GPT-4o-mini advisor -> Bhashini translate+TTS (en->gu)
            -> <Play> reply, then <Record> next turn (or hang up)
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

import httpx
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from twilio.twiml.voice_response import VoiceResponse

from . import auth, config, db, voice
from .api import router as api_router
from .openai_agent import next_reply

# Logs carry Gujarati / rupee glyphs; force UTF-8 so a log line can never raise
# (Windows consoles default to cp1252 and would crash on '₹' etc.).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

config.assert_ready()
os.makedirs(config.AUDIO_DIR, exist_ok=True)

app = FastAPI(title="Marwadi University Admission Voice Agent")
app.mount("/static", StaticFiles(directory=os.path.join(config.BASE_DIR, "static")), name="static")
app.include_router(api_router)

class LoginBody(BaseModel):
    username: str
    password: str


@app.get("/")
async def root() -> RedirectResponse:
    """Backend is API-only; the UI is the Next.js console (see FRONTEND_URL)."""
    return RedirectResponse(config.FRONTEND_URL, status_code=307)


@app.post("/api/login")
async def api_login(body: LoginBody) -> JSONResponse:
    if not auth.check_credentials(body.username, body.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    resp = JSONResponse({"ok": True})
    resp.set_cookie(auth.COOKIE, auth.create_session(),
                    httponly=True, samesite="lax", max_age=auth.TTL)
    return resp


@app.post("/api/logout")
async def api_logout(request: Request) -> JSONResponse:
    auth.destroy_session(request.cookies.get(auth.COOKIE))
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(auth.COOKIE)
    return resp

# In-memory per-call state: { CallSid: {"history": [...], "turn": int} }
SESSIONS: dict[str, dict] = {}

GREETING_EN = (
    "Welcome to Marwadi University admissions. I can help you find the right degree. "
    "To start, may I know your name?"
)
CLOSING_EN = "Thank you for calling Marwadi University. Goodbye and best wishes!"
REPROMPT_EN = "Sorry, I did not catch that. Could you please say it again?"
# Fixed Gujarati interjection played right after the student tells their marks,
# just before the agent lists the suitable degrees ("Wow! These are great marks.").
MARKS_CHEER_GU = "અરે વાહ! આ તો ખૂબ સરસ માર્ક્સ છે."
# Fixed short Gujarati question used to ask for the student's marks ("What is your
# percentage?"). Spoken from a cached clip so it's always brief and consistent.
MARKS_QUESTION_GU = "તમારી ટકાવારી કેટલી છે?"
MARKS_QUESTION_EN = "What is your percentage?"
# Short, natural acknowledgements rotated per turn so the caller never hears the
# same masking phrase twice in a row (only played when a reply is slow to render).
FILLERS_EN = ["Okay.", "Sure.", "One moment.", "Got it."]

# Shared keep-alive client for downloading Twilio recordings (avoids a fresh
# TLS handshake every turn).
_twilio_http: httpx.AsyncClient | None = None


def _twilio_client() -> httpx.AsyncClient:
    global _twilio_http
    if _twilio_http is None:
        _twilio_http = httpx.AsyncClient(
            timeout=httpx.Timeout(10.0, connect=5.0),
            auth=(config.TWILIO_ACCOUNT_SID, config.TWILIO_AUTH_TOKEN),
            limits=httpx.Limits(max_keepalive_connections=5, keepalive_expiry=30),
        )
    return _twilio_http


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
# Filler / yes-no words a noisy transcription often produces; never a real name.
_NON_NAME_TOKENS = {
    "yes", "no", "yeah", "yep", "nope", "ok", "okay", "haa", "ha", "haan",
    "na", "naa", "nahi", "hmm", "hm", "hello", "hi", "hey", "huh", "what",
    "sorry", "please", "sure", "vision", "thanks", "thank you", "bye",
}


def _is_valid_name(name: str) -> bool:
    """Reject empty, too-short, or filler-word 'names' from noisy ASR."""
    n = name.strip().lower()
    if len(n) < 2 or not any(c.isalpha() for c in n):
        return False
    return n not in _NON_NAME_TOKENS


def _audio_url(filename: str) -> str:
    return f"{config.PUBLIC_BASE_URL}/static/audio/{filename}"


async def _synthesize(text: str, filename: str) -> str:
    """English text -> Gujarati WAV saved to static/audio. Returns public URL."""
    url, _gu = await _synthesize_gu(text, filename)
    return url


async def _synthesize_gu(text: str, filename: str) -> tuple[str, str]:
    """Like _synthesize but also returns the Gujarati text that was spoken."""
    wav, gu = await voice.english_to_speech_gu(text)
    path = os.path.join(config.AUDIO_DIR, filename)
    with open(path, "wb") as f:
        f.write(wav)
    return _audio_url(filename), gu


async def _cached_audio(text: str, filename: str) -> str:
    """Synthesize a fixed phrase once and reuse the cached WAV on later calls."""
    path = os.path.join(config.AUDIO_DIR, filename)
    if not os.path.exists(path):
        await _synthesize(text, filename)
    return _audio_url(filename)


# Gujarati text of the greeting, cached so each call can log it as the opening
# turn (the greeting is pre-recorded audio, not produced by the per-turn pipeline).
_GREETING_GU = ""


async def _greeting_url() -> str:
    return await _cached_audio(GREETING_EN, "greeting.wav")


async def _ensure_greeting_gu() -> str:
    """Resolve + cache the Gujarati greeting text for the transcript / live chat."""
    global _GREETING_GU
    if not _GREETING_GU:
        path = os.path.join(config.AUDIO_DIR, "greeting.wav")
        if not os.path.exists(path):
            _, _GREETING_GU = await _synthesize_gu(GREETING_EN, "greeting.wav")
        else:
            try:
                _GREETING_GU = await voice.translate(
                    GREETING_EN, config.PIVOT_LANG, config.SOURCE_LANG)
            except Exception:
                _GREETING_GU = ""
    return _GREETING_GU


async def _filler_url(turn: int = 0) -> str:
    """A short acknowledgement, rotated per turn so it doesn't sound repetitive."""
    i = (max(turn, 1) - 1) % len(FILLERS_EN)
    return await _cached_audio(FILLERS_EN[i], f"filler{i}.wav")


async def _closing_url() -> str:
    return await _cached_audio(CLOSING_EN, "closing.wav")


async def _reprompt_url() -> str:
    return await _cached_audio(REPROMPT_EN, "reprompt.wav")


async def _cached_gu_audio(text_gu: str, filename: str) -> str:
    """Cache a fixed Gujarati phrase as audio (TTS directly, no translation)."""
    path = os.path.join(config.AUDIO_DIR, filename)
    if not os.path.exists(path):
        wav = await voice.gu_to_speech(text_gu)
        with open(path, "wb") as f:
            f.write(wav)
    return _audio_url(filename)


async def _marks_cheer_url() -> str:
    return await _cached_gu_audio(MARKS_CHEER_GU, "marks_cheer.wav")


async def _marks_question_url() -> str:
    return await _cached_gu_audio(MARKS_QUESTION_GU, "marks_question.wav")


async def _download_recording(recording_url: str) -> bytes:
    """Fetch the Twilio WAV recording (retrying while it becomes available)."""
    url = recording_url + ".wav"
    client = _twilio_client()
    for attempt in range(6):
        r = await client.get(url)
        if r.status_code == 200 and r.content:
            return r.content
        await asyncio.sleep(0.1 + 0.15 * attempt)   # 0.1,0.25,0.4,0.55,0.7s
    raise RuntimeError(f"Could not download recording: {recording_url}")


def _record(vr: VoiceResponse) -> None:
    """Append a <Record> that captures one caller turn and posts to /process."""
    vr.record(
        action="/process",
        method="POST",
        max_length=30,        # allow longer answers without being cut off
        timeout=3,            # end of turn after 3s of silence: long enough that a
                              # natural pause (or a slow start) doesn't cut the caller off
        play_beep=False,
        trim="trim-silence",
        finish_on_key="#",
    )


def _twiml(vr: VoiceResponse) -> Response:
    return Response(content=str(vr), media_type="application/xml")


async def _emit_reply(vr: VoiceResponse, CallSid: str, reply_url: str,
                      end_call: bool) -> None:
    """Append the agent's reply, then either hang up (with closing) or record next."""
    vr.play(reply_url)
    if end_call:
        try:
            vr.play(await _closing_url())
        except Exception:
            pass
        vr.hangup()
        SESSIONS.pop(CallSid, None)
    else:
        _record(vr)


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
@app.on_event("startup")
async def _startup() -> None:
    db.init_db()                      # create tables if missing
    await voice.warm_up()          # pre-fetch pipeline config
    # Pre-synthesize every fixed phrase so none is rendered mid-call.
    results = await asyncio.gather(
        _greeting_url(), _ensure_greeting_gu(), _closing_url(), _reprompt_url(),
        _marks_cheer_url(), _marks_question_url(),
        *[_filler_url(i + 1) for i in range(len(FILLERS_EN))],
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            print(f"[startup] phrase pre-synthesis skipped: {r}")


@app.on_event("shutdown")
async def _shutdown() -> None:
    await voice.aclose()
    if _twilio_http is not None:
        await _twilio_http.aclose()


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "sessions": len(SESSIONS)}


# --------------------------------------------------------------------------- #
# Twilio webhooks
# --------------------------------------------------------------------------- #
@app.post("/voice")
async def voice_webhook(
    CallSid: str = Form(...),
    From: str = Form(default=""),
    To: str = Form(default=""),
    Direction: str = Form(default="inbound"),
) -> Response:
    """Call entry point (inbound, or Twilio fetching our flow for outbound)."""
    direction0 = "outbound" if Direction.startswith("outbound") else "inbound"
    # The student is the remote party: callee (To) on outbound, caller (From) on inbound.
    student_phone = To if direction0 == "outbound" else From
    # Seed the greeting as the agent's opening turn so (a) the advisor knows it
    # already asked for the name and won't re-ask, and (b) it shows up in the
    # transcript / live chat (the greeting is pre-recorded, not a pipeline turn).
    SESSIONS[CallSid] = {"history": [{"role": "assistant", "content": GREETING_EN}],
                         "turn": 0, "phone": student_phone,
                         "name": "", "qualification": ""}
    # Outbound calls are pre-recorded at dial time; only log if not seen yet.
    if db.get_call(CallSid) is None:
        direction = "outbound" if Direction.startswith("outbound") else "inbound"
        db.record_call(CallSid, To, From, direction, "in-progress")
    # Make sure we have the Gujarati greeting text so the chat shows it in
    # Gujarati like every other turn (startup usually fills this already).
    greeting_gu = _GREETING_GU
    if not greeting_gu:
        try:
            greeting_gu = await _ensure_greeting_gu()
        except Exception:
            greeting_gu = ""
    db.add_turn(CallSid, 0, "assistant", GREETING_EN, greeting_gu)
    vr = VoiceResponse()
    try:
        vr.play(await _greeting_url())
    except Exception:
        vr.say(GREETING_EN, language="en-IN")  # fallback if Bhashini is down
    _record(vr)
    return _twiml(vr)


async def _compute_reply(CallSid: str, recording_url: str, turn: int) -> tuple[str, bool]:
    """Heavy turn work: download -> ASR -> advisor -> TTS.

    Runs as a background task so /process can return a filler immediately and
    mask the dead air. Returns (audio_url_to_play, end_call). On any failure it
    returns the cached reprompt so the call keeps going.
    """
    session = SESSIONS.setdefault(CallSid, {"history": [], "turn": 0})
    t0 = time.perf_counter()
    try:
        audio = await _download_recording(recording_url)
        t1 = time.perf_counter()
        student_en, student_gu = await voice.speech_to_english_gu(audio)
        t2 = time.perf_counter()
        if not student_en:
            return await _reprompt_url(), False

        # Give the advisor the original Gujarati too, so it can transliterate
        # names (which a translation step would otherwise turn into their meaning,
        # e.g. દૃષ્ટિ -> "Vision"). The DB still stores clean en/gu separately.
        content = f"{student_en}  [gu: {student_gu}]" if student_gu else student_en
        session["history"].append({"role": "user", "content": content})
        db.add_turn(CallSid, turn, "user", student_en, student_gu)
        result = await next_reply(session["history"])
        reply_en, end_call = result["reply"], result["end"]
        t3 = time.perf_counter()
        if not reply_en:
            reply_en = "Could you tell me a bit more about your qualification?"

        # When the advisor wants to ask for marks, speak the fixed short Gujarati
        # question ("તમારી ટકાવારી કેટલી છે?") instead of synthesizing the model's
        # text -- always brief, consistent, and skips a TTS call.
        ask_marks = bool(result.get("ask_marks"))
        if ask_marks:
            reply_en = MARKS_QUESTION_EN
        session["history"].append({"role": "assistant", "content": reply_en})

        if ask_marks:
            reply_url, reply_gu = await _marks_question_url(), MARKS_QUESTION_GU
        else:
            # Synthesize so we also capture the Gujarati the agent actually says.
            reply_url, reply_gu = await _synthesize_gu(reply_en, f"{CallSid}-{turn}.wav")
        t4 = time.perf_counter()
        db.add_turn(CallSid, turn, "assistant", reply_en, reply_gu)

        # Persist any newly-captured name/qualification onto the call + lead so
        # the console shows them live (only fills in, never clobbers human edits).
        # The name is double-guarded: the advisor only emits it once confirmed,
        # and we still drop obvious noise words before storing.
        name, qualification = result["name"], result["qualification"]
        if not _is_valid_name(name):
            name = ""
        if name and name != session.get("name"):
            session["name"] = name
            db.set_call_name(CallSid, name)
        if qualification:
            session["qualification"] = qualification
        # The advisor sets cheer=true on the turn that reacts to the student's
        # marks; play the fixed Gujarati interjection before that reply -- but at
        # most ONCE per call, even if the model flags it again on later turns.
        if result.get("cheer") and not session.get("cheered"):
            session["cheered"] = True
            session["pending_cheer"] = True
        else:
            session["pending_cheer"] = False
        if name or qualification:
            phone = session.get("phone")
            if phone:
                db.upsert_lead_from_phone(phone, CallSid, source="call",
                                          name=session.get("name", ""),
                                          qualification=session.get("qualification", ""))
        # Logging must never break a call: guard it separately from the work.
        try:
            print(f"[timing] {CallSid} turn={turn} "
                  f"dl={t1-t0:.2f}s asr={t2-t1:.2f}s llm={t3-t2:.2f}s "
                  f"tts={t4-t3:.2f}s total={t4-t0:.2f}s | "
                  f"'{student_en[:30]}' -> '{reply_en[:30]}' end={end_call}",
                  flush=True)
        except Exception:
            pass
        return reply_url, end_call
    except Exception as e:
        print(f"[compute] turn={turn} error: {e!r}", flush=True)
        return await _reprompt_url(), False


@app.post("/process")
async def process(
    CallSid: str = Form(...),
    RecordingUrl: str = Form(default=""),
    RecordingDuration: str = Form(default="0"),
) -> Response:
    """Receive one caller turn: kick off processing, play a filler, redirect."""
    session = SESSIONS.setdefault(CallSid, {"history": [], "turn": 0})
    session["turn"] += 1
    vr = VoiceResponse()

    # No / empty recording -> reprompt immediately.
    if not RecordingUrl or RecordingDuration in ("", "0"):
        try:
            vr.play(await _reprompt_url())
        except Exception:
            vr.say(REPROMPT_EN, language="en-IN")
        _record(vr)
        return _twiml(vr)

    # Start the heavy work, then acknowledge IMMEDIATELY with a short filler so
    # the caller never hears dead air. /await then plays the reply the instant
    # the pipeline finishes (it returns as soon as the task completes).
    session["task"] = asyncio.ensure_future(
        _compute_reply(CallSid, RecordingUrl, session["turn"])
    )
    try:
        vr.play(await _filler_url(session["turn"]))
    except Exception:
        vr.pause(length=1)
    vr.redirect("/await", method="POST")
    return _twiml(vr)


@app.post("/await")
async def await_reply(CallSid: str = Form(...)) -> Response:
    """Play the reply as soon as the background task finishes (else poll)."""
    session = SESSIONS.get(CallSid)
    vr = VoiceResponse()
    task = session.get("task") if session else None

    if task is None:                       # nothing pending -> just listen
        _record(vr)
        return _twiml(vr)

    try:
        # shield so a timeout here doesn't cancel the still-running work.
        reply_url, end_call = await asyncio.wait_for(asyncio.shield(task), timeout=6.0)
    except asyncio.TimeoutError:
        vr.pause(length=1)                 # still working: brief hold, poll again
        vr.redirect("/await", method="POST")
        return _twiml(vr)

    session.pop("task", None)
    # Marks interjection (fixed Gujarati clip) plays just before the degree list.
    if session.pop("pending_cheer", False):
        try:
            vr.play(await _marks_cheer_url())
        except Exception:
            pass
    await _emit_reply(vr, CallSid, reply_url, end_call)
    return _twiml(vr)


@app.post("/status")
async def status(
    CallSid: str = Form(...),
    CallStatus: str = Form(default=""),
    CallDuration: str = Form(default=""),
) -> dict:
    """Twilio status callback: persist call status/duration and clean up state."""
    if CallStatus:
        try:
            duration = int(CallDuration) if CallDuration.isdigit() else None
            db.update_call_status(CallSid, CallStatus, duration)
        except Exception as e:
            print(f"[status] db update failed: {e!r}", flush=True)
    if CallStatus in ("completed", "failed", "busy", "no-answer", "canceled"):
        # Capture the contact as a lead (once per phone number).
        try:
            call = db.get_call(CallSid)
            if call:
                number = (call["to_number"] if call["direction"] == "outbound"
                          else call["from_number"])
                if number:
                    db.upsert_lead_from_phone(number, CallSid, source="call")
        except Exception as e:
            print(f"[status] lead upsert failed: {e!r}", flush=True)
        SESSIONS.pop(CallSid, None)
    return {"ok": True}
