"""Bhashini (ULCA / Dhruva) client for Gujarati voice.

Latency strategy:
  * Fetch the pipeline config ONCE (service ids + inference endpoint) and cache it.
  * Inbound turn  = 1 HTTP call  : Gujarati audio -> [ASR] -> [translation gu->en] -> English text.
  * Outbound turn = 1 HTTP call  : English text -> [translation en->gu] -> [TTS gu] -> audio bytes.
  * Reuse a single keep-alive httpx.AsyncClient (HTTP/2) for connection reuse.
"""
from __future__ import annotations

import array
import asyncio
import base64
import io
import struct
import sys
import wave

import httpx

from . import config

_client: httpx.AsyncClient | None = None
_pipeline: dict | None = None
_lock = asyncio.Lock()


def to_twilio_pcm16(wav_bytes: bytes) -> bytes:
    """Transcode a WAV to 16-bit PCM so Twilio <Play> can decode it.

    Bhashini TTS returns 32-bit IEEE-float WAV (format tag 3); Twilio only plays
    PCM. Convert float->int16 (and 8-bit uint->int16) in pure stdlib, preserving
    channel count and sample rate. Pass-through if already PCM16 or unrecognized.
    """
    d = wav_bytes
    if d[:4] != b"RIFF" or d.find(b"fmt ") < 0:
        return wav_bytes
    fi = d.find(b"fmt ")
    tag, ch, rate, _byterate, _align, bits = struct.unpack("<HHIIHH", d[fi + 8: fi + 24])
    di = d.find(b"data", fi)
    if di < 0:
        return wav_bytes
    size = struct.unpack("<I", d[di + 4: di + 8])[0]
    raw = d[di + 8: di + 8 + size] if size else d[di + 8:]

    if tag == 1 and bits == 16:
        return wav_bytes  # already Twilio-friendly

    if tag == 3 and bits == 32:                       # IEEE float -> int16
        floats = array.array("f")
        floats.frombytes(raw[: len(raw) - (len(raw) % 4)])
        if sys.byteorder == "big":
            floats.byteswap()
        pcm = array.array(
            "h",
            (32767 if s >= 1.0 else -32768 if s <= -1.0 else int(s * 32767.0)
             for s in floats),
        )
    elif tag == 1 and bits == 8:                      # uint8 PCM -> int16
        pcm = array.array("h", ((b - 128) << 8 for b in raw))
    else:
        return wav_bytes                              # unknown encoding; let Twilio try

    if sys.byteorder == "big":
        pcm.byteswap()
    out = io.BytesIO()
    w = wave.open(out, "wb")
    w.setnchannels(ch or 1)
    w.setsampwidth(2)
    w.setframerate(rate or config.TTS_SAMPLE_RATE)
    w.writeframes(pcm.tobytes())
    w.close()
    return out.getvalue()


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            http2=True,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=60),
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _ensure_pipeline() -> dict:
    """Resolve and cache service ids + the inference endpoint/auth header."""
    global _pipeline
    if _pipeline is not None:
        return _pipeline

    async with _lock:
        if _pipeline is not None:
            return _pipeline

        # Direct-inference mode: you hold an inference key, so call Dhruva
        # directly with fixed service ids -- no getModelsPipeline / userID needed.
        if config.direct_mode():
            _pipeline = {
                "url": config.BHASHINI_INFERENCE_URL,
                "auth_name": config.BHASHINI_AUTH_HEADER,
                "auth_value": config.BHASHINI_INFERENCE_KEY,
                "asr": config.BHASHINI_ASR_SERVICE_ID,
                "nmt": config.BHASHINI_NMT_SERVICE_ID,
                "tts": config.BHASHINI_TTS_SERVICE_ID,
            }
            return _pipeline

        body = {
            "pipelineTasks": [
                {"taskType": "asr", "config": {"language": {"sourceLanguage": config.SOURCE_LANG}}},
                {"taskType": "translation", "config": {"language": {"sourceLanguage": config.SOURCE_LANG, "targetLanguage": config.PIVOT_LANG}}},
                {"taskType": "translation", "config": {"language": {"sourceLanguage": config.PIVOT_LANG, "targetLanguage": config.SOURCE_LANG}}},
                {"taskType": "tts", "config": {"language": {"sourceLanguage": config.SOURCE_LANG}}},
            ],
            "pipelineRequestConfig": {"pipelineId": config.BHASHINI_PIPELINE_ID},
        }
        headers = {
            "userID": config.BHASHINI_USER_ID,
            "ulcaApiKey": config.BHASHINI_API_KEY,
            "Content-Type": "application/json",
        }
        resp = await _http().post(config.BHASHINI_CONFIG_URL, json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()

        endpoint = data["pipelineInferenceAPIEndPoint"]
        api_key = endpoint["inferenceApiKey"]

        # Pick the first serviceId per (task, direction).
        asr_id = config.BHASHINI_ASR_SERVICE_ID
        nmt_id = config.BHASHINI_NMT_SERVICE_ID
        tts_id = config.BHASHINI_TTS_SERVICE_ID
        for task in data.get("pipelineResponseConfig", []):
            ttype = task.get("taskType")
            cfgs = task.get("config", [])
            if not cfgs:
                continue
            sid = cfgs[0].get("serviceId")
            if ttype == "asr" and not asr_id:
                asr_id = sid
            elif ttype == "translation" and not nmt_id:
                nmt_id = sid
            elif ttype == "tts" and not tts_id:
                tts_id = sid

        _pipeline = {
            "url": endpoint["callbackUrl"],
            "auth_name": api_key["name"],
            "auth_value": api_key["value"],
            "asr": asr_id,
            "nmt": nmt_id,
            "tts": tts_id,
        }
    return _pipeline


async def _infer(tasks: list[dict], input_data: dict) -> dict:
    p = await _ensure_pipeline()
    headers = {p["auth_name"]: p["auth_value"], "Content-Type": "application/json"}
    resp = await _http().post(
        p["url"], json={"pipelineTasks": tasks, "inputData": input_data}, headers=headers
    )
    resp.raise_for_status()
    return resp.json()


async def speech_to_english_gu(audio_bytes: bytes, audio_format: str = "wav") -> tuple[str, str]:
    """Gujarati audio -> (English text, original Gujarati ASR text), one call."""
    p = await _ensure_pipeline()
    tasks = [
        {"taskType": "asr", "config": {
            "language": {"sourceLanguage": config.SOURCE_LANG},
            "serviceId": p["asr"], "audioFormat": audio_format,
            "samplingRate": config.TTS_SAMPLE_RATE}},
        {"taskType": "translation", "config": {
            "language": {"sourceLanguage": config.SOURCE_LANG, "targetLanguage": config.PIVOT_LANG},
            "serviceId": p["nmt"]}},
    ]
    audio_b64 = base64.b64encode(audio_bytes).decode("ascii")
    data = await _infer(tasks, {"audio": [{"audioContent": audio_b64}]})

    english, gujarati = "", ""
    for out in data.get("pipelineResponse", []):
        if out.get("taskType") == "asr":
            gujarati = out["output"][0].get("source", "")
        elif out.get("taskType") == "translation":
            english = out["output"][0].get("target", "")
    return english.strip(), gujarati.strip()


async def speech_to_english(audio_bytes: bytes, audio_format: str = "wav") -> str:
    """Gujarati audio -> English text (ASR + translation in one call)."""
    english, _gu = await speech_to_english_gu(audio_bytes, audio_format)
    return english


def _speech_safe(text: str) -> str:
    """Soften punctuation the TTS mis-reads aloud.

    Bhashini TTS verbalizes '!' as the word "factorial"; turn exclamations into a
    plain period (and collapse any doubled punctuation that produces).
    """
    out = text.replace("!", ".")
    while ".." in out:
        out = out.replace("..", ".")
    return out.strip()


async def english_to_speech_gu(text: str) -> tuple[bytes, str]:
    """English text -> (Gujarati audio WAV, the Gujarati translation text), one call."""
    text = _speech_safe(text)
    p = await _ensure_pipeline()
    tasks = [
        {"taskType": "translation", "config": {
            "language": {"sourceLanguage": config.PIVOT_LANG, "targetLanguage": config.SOURCE_LANG},
            "serviceId": p["nmt"]}},
        {"taskType": "tts", "config": {
            "language": {"sourceLanguage": config.SOURCE_LANG},
            "serviceId": p["tts"], "gender": config.TTS_VOICE_GENDER,
            "samplingRate": config.TTS_SAMPLE_RATE}},
    ]
    data = await _infer(tasks, {"input": [{"source": text}]})

    gujarati, audio = "", None
    for out in data.get("pipelineResponse", []):
        if out.get("taskType") == "translation":
            gujarati = out["output"][0].get("target", "")
        elif out.get("taskType") == "tts":
            audio = to_twilio_pcm16(base64.b64decode(out["audio"][0]["audioContent"]))
    if audio is None:
        raise RuntimeError("Bhashini TTS returned no audio")
    return audio, gujarati.strip()


async def english_to_speech(text: str) -> bytes:
    """English text -> Gujarati audio (translation + TTS in one call). Returns WAV bytes."""
    audio, _gu = await english_to_speech_gu(text)
    return audio


async def gu_to_speech(text_gu: str) -> bytes:
    """Speak a phrase already in Gujarati (TTS only, no translation step)."""
    p = await _ensure_pipeline()
    tasks = [
        {"taskType": "tts", "config": {
            "language": {"sourceLanguage": config.SOURCE_LANG},
            "serviceId": p["tts"], "gender": config.TTS_VOICE_GENDER,
            "samplingRate": config.TTS_SAMPLE_RATE}},
    ]
    data = await _infer(tasks, {"input": [{"source": _speech_safe(text_gu)}]})
    for out in data.get("pipelineResponse", []):
        if out.get("taskType") == "tts":
            return to_twilio_pcm16(base64.b64decode(out["audio"][0]["audioContent"]))
    raise RuntimeError("Bhashini TTS returned no audio")


async def translate(text: str, src: str, tgt: str) -> str:
    """Standalone translation helper (used by the data translation script)."""
    p = await _ensure_pipeline()
    tasks = [{"taskType": "translation", "config": {
        "language": {"sourceLanguage": src, "targetLanguage": tgt}, "serviceId": p["nmt"]}}]
    data = await _infer(tasks, {"input": [{"source": text}]})
    for out in data.get("pipelineResponse", []):
        if out.get("taskType") == "translation":
            return out["output"][0].get("target", "")
    return ""


async def warm_up() -> None:
    """Pre-fetch pipeline config at startup so the first call is fast."""
    try:
        await _ensure_pipeline()
    except Exception as e:  # don't crash boot; will retry lazily
        print(f"[bhashini] warm-up failed (will retry on first call): {e}")
