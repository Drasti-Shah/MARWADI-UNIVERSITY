"""Sarvam AI client for Gujarati voice (drop-in replacement for bhashini.py).

Exposes the same surface the app uses:
  * speech_to_english_gu(audio) -> (english, gujarati)   # 2 calls, run in parallel
  * english_to_speech_gu(text)  -> (wav_bytes, gujarati) # translate (en->gu) + TTS
  * gu_to_speech(text_gu)        -> wav_bytes             # TTS of a fixed Gujarati phrase
  * translate / speech_to_english / english_to_speech     # thin wrappers
  * warm_up / aclose / to_twilio_pcm16

Sarvam endpoints (api.sarvam.ai), auth header: api-subscription-key.
"""
from __future__ import annotations

import asyncio
import base64

import httpx

from . import config
from .bhashini import to_twilio_pcm16   # pure WAV transcoder, no network

_client: httpx.AsyncClient | None = None

_HEADERS = {"api-subscription-key": config.SARVAM_API_KEY}


def _http() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            http2=True,
            base_url=config.SARVAM_BASE_URL,
            timeout=httpx.Timeout(30.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=10, keepalive_expiry=60),
        )
    return _client


async def aclose() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def warm_up() -> None:
    """No pipeline handshake needed for Sarvam; nothing to pre-fetch."""
    return None


def _speech_safe(text: str) -> str:
    """Soften punctuation a TTS may mis-read; mirror bhashini behaviour."""
    out = text.replace("!", ".")
    while ".." in out:
        out = out.replace("..", ".")
    return out.strip()


# Proper nouns the translator mis-spells (and the TTS then mis-pronounces).
# Applied to the Gujarati before it is shown or spoken.
_GU_FIXUPS = {
    "મરવાડી": "મારવાડી",   # Marwadi: needs the long 'aa' (મા), not short 'a' (મ)
    "મારવારી": "મારવાડી",  # "Marwari" mis-hearing -> Marwadi
}


def _fix_gu(text: str) -> str:
    for wrong, right in _GU_FIXUPS.items():
        text = text.replace(wrong, right)
    return text


# --------------------------------------------------------------------------- #
# Speech -> text
# --------------------------------------------------------------------------- #
async def _stt_translate(audio_bytes: bytes, audio_format: str) -> str:
    """Saaras: Gujarati audio -> English text (one call)."""
    files = {"file": (f"audio.{audio_format}", audio_bytes, f"audio/{audio_format}")}
    # NOTE: do not pass a `prompt` here -- Saaras echoes it back as the transcript
    # when the audio is silent, which then leaks into the conversation.
    data = {"model": config.SARVAM_STT_TRANSLATE_MODEL}
    r = await _http().post("/speech-to-text-translate", files=files, data=data, headers=_HEADERS)
    r.raise_for_status()
    return (r.json().get("transcript") or "").strip()


async def _stt_transcribe(audio_bytes: bytes, audio_format: str) -> str:
    """Saarika: Gujarati audio -> Gujarati transcript (one call)."""
    files = {"file": (f"audio.{audio_format}", audio_bytes, f"audio/{audio_format}")}
    data = {"model": config.SARVAM_TRANSCRIBE_MODEL,
            "language_code": config.SARVAM_SOURCE_LANG}
    r = await _http().post("/speech-to-text", files=files, data=data, headers=_HEADERS)
    r.raise_for_status()
    return (r.json().get("transcript") or "").strip()


async def speech_to_english_gu(audio_bytes: bytes, audio_format: str = "wav") -> tuple[str, str]:
    """Gujarati audio -> (English text, Gujarati transcript). Both calls in parallel."""
    en, gu = await asyncio.gather(
        _stt_translate(audio_bytes, audio_format),
        _stt_transcribe(audio_bytes, audio_format),
        return_exceptions=True,
    )
    english = "" if isinstance(en, Exception) else en
    gujarati = "" if isinstance(gu, Exception) else gu
    # If the dedicated translate call failed but we have the Gujarati, fall back.
    if not english and gujarati:
        try:
            english = await translate(gujarati, config.SOURCE_LANG, config.PIVOT_LANG)
        except Exception:
            english = ""
    return english.strip(), gujarati.strip()


async def speech_to_english(audio_bytes: bytes, audio_format: str = "wav") -> str:
    english, _gu = await speech_to_english_gu(audio_bytes, audio_format)
    return english


# --------------------------------------------------------------------------- #
# Text -> text / speech
# --------------------------------------------------------------------------- #
def _lang(code: str) -> str:
    """Map bare 'gu'/'en' to Sarvam's 'gu-IN'/'en-IN' (pass through if already BCP-47)."""
    if "-" in code:
        return code
    return {"gu": config.SARVAM_SOURCE_LANG, "en": config.SARVAM_PIVOT_LANG}.get(code, code)


async def translate(text: str, src: str, tgt: str) -> str:
    """Standalone translation via Mayura."""
    if not text:
        return ""
    body = {
        "input": text,
        "source_language_code": _lang(src),
        "target_language_code": _lang(tgt),
        "model": config.SARVAM_TRANSLATE_MODEL,
    }
    r = await _http().post("/translate", json=body, headers=_HEADERS)
    r.raise_for_status()
    return _fix_gu((r.json().get("translated_text") or "").strip())


async def _tts(text_gu: str) -> bytes:
    """Bulbul TTS of Gujarati text -> Twilio-ready PCM16 WAV bytes."""
    body = {
        "inputs": [_fix_gu(_speech_safe(text_gu))],
        "target_language_code": config.SARVAM_SOURCE_LANG,
        "speaker": config.SARVAM_TTS_SPEAKER,
        "model": config.SARVAM_TTS_MODEL,
        "speech_sample_rate": config.TTS_SAMPLE_RATE,
        "enable_preprocessing": True,
    }
    r = await _http().post("/text-to-speech", json=body, headers=_HEADERS)
    r.raise_for_status()
    audios = r.json().get("audios") or []
    if not audios:
        raise RuntimeError("Sarvam TTS returned no audio")
    return to_twilio_pcm16(base64.b64decode(audios[0]))


async def english_to_speech_gu(text: str) -> tuple[bytes, str]:
    """English text -> (Gujarati audio WAV, the Gujarati translation text)."""
    gu = await translate(text, config.PIVOT_LANG, config.SOURCE_LANG)
    if not gu:
        gu = text                      # last-resort: let TTS try the English
    audio = await _tts(gu)
    return audio, gu.strip()


async def english_to_speech(text: str) -> bytes:
    audio, _gu = await english_to_speech_gu(text)
    return audio


async def gu_to_speech(text_gu: str) -> bytes:
    """Speak a phrase that is ALREADY in Gujarati (no translation step)."""
    return await _tts(text_gu)
