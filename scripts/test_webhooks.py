"""Twilio webhook test (no phone call, no real network).

Drives the FastAPI app with a TestClient while mocking the external edges:
  * voice.warm_up / english_to_speech(_gu) / speech_to_english(_gu) / gu_to_speech
  * main._download_recording                                  (no Twilio fetch)
  * main.next_reply (OpenAI advisor)                          (no OpenAI call)

Covers: /health, /voice, /process (fast path, slow path + /await, end-call,
empty-recording), and /status cleanup. Run:  python -m scripts.test_webhooks
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from unittest.mock import AsyncMock, patch

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi.testclient import TestClient

from app import config, db, main, voice

# Isolate persistence: point the DB at a throwaway file so the test never
# writes call/transcript rows into the real data/app.db.
db.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="voiceagent-test-db-"), "test.db")
db._conn = None

FAKE_WAV = b"RIFF\x00\x00\x00\x00WAVEfake-audio-bytes"
GU = "ગુજરાતી લખાણ"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(f"{'[OK]' if ok else '[XX]'} {name}" + (f" - {detail}" if detail else ""))


def run() -> int:
    # --- mock every external edge -----------------------------------------
    # Redirect audio writes to a throwaway dir so the test never poisons the
    # real static/audio greeting cache with mock bytes.
    tmp_audio = tempfile.mkdtemp(prefix="voiceagent-test-audio-")
    patches = [
        patch.object(config, "AUDIO_DIR", tmp_audio),
        patch.object(voice, "warm_up", AsyncMock(return_value=None)),
        patch.object(voice, "english_to_speech", AsyncMock(return_value=FAKE_WAV)),
        patch.object(voice, "english_to_speech_gu",
                     AsyncMock(return_value=(FAKE_WAV, GU))),
        patch.object(voice, "gu_to_speech", AsyncMock(return_value=FAKE_WAV)),
        patch.object(voice, "translate", AsyncMock(return_value=GU)),
        patch.object(voice, "speech_to_english",
                     AsyncMock(return_value="I have completed 12th Science")),
        patch.object(voice, "speech_to_english_gu",
                     AsyncMock(return_value=("I have completed 12th Science",
                                             "મેં ૧૨મું વિજ્ઞાન પૂર્ણ કર્યું"))),
        patch.object(main, "_download_recording", AsyncMock(return_value=FAKE_WAV)),
    ]
    for p in patches:
        p.start()

    # Advisor reply is controlled per-test below. next_reply returns a dict.
    advisor = patch.object(
        main, "next_reply",
        AsyncMock(return_value={
            "reply": "Great! I recommend B.Tech in Computer Engineering.",
            "end": False, "name": "Riya", "qualification": "12th Science",
            "cheer": False, "ask_marks": False}),
    )
    advisor.start()

    try:
        # TestClient context fires startup/shutdown lifecycle events.
        with TestClient(main.app) as client:
            # 1. /health
            r = client.get("/health")
            check("GET /health", r.status_code == 200 and r.json().get("status") == "ok",
                  f"{r.status_code} {r.json()}")

            # 2. /voice -> greeting + <Record action=/process>
            r = client.post("/voice", data={"CallSid": "CALL1"})
            body = r.text
            ok = (r.status_code == 200 and "<Play>" in body
                  and 'action="/process"' in body and "<Record" in body)
            check("POST /voice", ok, "plays greeting then records")
            check("  session created", "CALL1" in main.SESSIONS,
                  f"turn={main.SESSIONS.get('CALL1', {}).get('turn')}")

            # 3. /process -> short filler + redirect to /await (acknowledge with
            #    no dead air); /await then plays the reply and records next turn.
            r = client.post("/process", data={
                "CallSid": "CALL1",
                "RecordingUrl": "https://api.twilio.com/rec/RE123",
                "RecordingDuration": "4",
            })
            body = r.text
            ok = (r.status_code == 200 and "<Play>" in body
                  and "<Redirect" in body and "/await" in body)
            check("POST /process (turn)", ok, "plays filler then redirects, no dead air")
            check("  task pending", "task" in main.SESSIONS.get("CALL1", {}),
                  "background work started")

            r = client.post("/await", data={"CallSid": "CALL1"})
            body = r.text
            ok = r.status_code == 200 and "<Play>" in body and "<Record" in body
            check("POST /await (reply)", ok, "plays reply then records next turn")
            hist = main.SESSIONS["CALL1"]["history"]
            # history seeds with the greeting (assistant), then user + reply.
            check("  history updated",
                  len(hist) == 3 and hist[0]["role"] == "assistant"
                  and hist[1]["role"] == "user",
                  f"{len(hist)} msgs, user='{hist[1]['content']}'")
            check("  name captured", main.SESSIONS["CALL1"].get("name") == "Riya",
                  f"name={main.SESSIONS['CALL1'].get('name')!r}")

            # 3b. ask_marks turn -> /await plays the fixed marks-question clip.
            main.next_reply.return_value = {
                "reply": "(ignored)", "end": False, "name": "Riya",
                "qualification": "12th Science", "cheer": False, "ask_marks": True}
            client.post("/process", data={
                "CallSid": "CALL1", "RecordingUrl": "https://api.twilio.com/rec/RE150",
                "RecordingDuration": "3"})
            r = client.post("/await", data={"CallSid": "CALL1"})
            check("POST /await (ask marks)", "marks_question.wav" in r.text,
                  "plays the fixed short marks question")

            # 3c. marks turn -> advisor flags cheer -> /await plays the fixed
            #     Gujarati cheer clip BEFORE the degree-list reply, and only once.
            main.next_reply.return_value = {
                "reply": "You can consider B.Tech CSE or BCA. Which interests you?",
                "end": False, "name": "Riya", "qualification": "12th Science",
                "cheer": True, "ask_marks": False}
            client.post("/process", data={
                "CallSid": "CALL1", "RecordingUrl": "https://api.twilio.com/rec/RE200",
                "RecordingDuration": "3"})
            r = client.post("/await", data={"CallSid": "CALL1"})
            check("POST /await (marks cheer)",
                  r.text.count("<Play>") >= 2 and "marks_cheer.wav" in r.text,
                  "plays cheer clip before the degree list")
            client.post("/process", data={
                "CallSid": "CALL1", "RecordingUrl": "https://api.twilio.com/rec/RE201",
                "RecordingDuration": "3"})
            r = client.post("/await", data={"CallSid": "CALL1"})
            check("  cheer plays once", "marks_cheer.wav" not in r.text,
                  "a later cheer flag is ignored")
            main.next_reply.return_value = {
                "reply": "Great! I recommend B.Tech in Computer Engineering.",
                "end": False, "name": "Riya", "qualification": "12th Science",
                "cheer": False, "ask_marks": False}

            # 4. /process empty recording -> reprompt immediately
            r = client.post("/process", data={
                "CallSid": "CALL1", "RecordingUrl": "", "RecordingDuration": "0",
            })
            ok = r.status_code == 200 and "<Play>" in r.text and "<Record" in r.text
            check("POST /process (empty rec)", ok, "reprompts and records again")

            # 5. end-call: advisor sets end=True -> /await hangs up, session gone.
            main.next_reply.return_value = {
                "reply": "Thank you, goodbye!", "end": True, "name": "Riya",
                "qualification": "12th Science", "cheer": False, "ask_marks": False}
            r = client.post("/process", data={
                "CallSid": "CALL1",
                "RecordingUrl": "https://api.twilio.com/rec/RE999",
                "RecordingDuration": "3",
            })
            check("POST /process (end turn)", "<Redirect" in r.text, "redirects to /await")
            r = client.post("/await", data={"CallSid": "CALL1"})
            body = r.text
            check("POST /await (end=True)", "<Hangup" in body, "hangs up")
            check("  session removed", "CALL1" not in main.SESSIONS, "cleaned up on end")

            # 6. /status completed -> cleanup
            main.SESSIONS["CALL2"] = {"history": [], "turn": 0}
            r = client.post("/status", data={"CallSid": "CALL2", "CallStatus": "completed"})
            check("POST /status (completed)",
                  r.status_code == 200 and "CALL2" not in main.SESSIONS,
                  "session cleaned on call completion")
    finally:
        advisor.stop()
        for p in patches:
            p.stop()

    print("-" * 60)
    n_ok = sum(1 for _, ok, _ in results if ok)
    n_bad = len(results) - n_ok
    print(f" RESULT: {n_ok}/{len(results)} checks passed"
          + (f", {n_bad} FAILED" if n_bad else ""))
    return 1 if n_bad else 0


if __name__ == "__main__":
    print("=" * 60)
    print(" TWILIO WEBHOOK TEST (mocked edges, no phone call)")
    print("=" * 60)
    sys.exit(run())
