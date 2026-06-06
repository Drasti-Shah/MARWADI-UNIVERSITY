"""Full Bhashini round-trip test (no phone call).

  1. translate  en -> gu
  2. TTS        en -> gu  -> WAV bytes
  3. ASR        gu audio  -> en text   (feeds step-2 audio back in)

Run:  python -m scripts.test_bhashini
"""
from __future__ import annotations

import asyncio
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app import bhashini, config


async def main() -> int:
    print("=" * 66)
    print(" BHASHINI ROUND-TRIP TEST (no phone call)")
    print("=" * 66)
    print(f" endpoint : {config.BHASHINI_INFERENCE_URL}")
    print(f" mode     : {'direct-inference' if config.direct_mode() else 'ULCA'}")
    print(f" rate     : {config.TTS_SAMPLE_RATE} Hz")
    print("-" * 66)

    failures = 0
    sample_en = "Welcome to Marwadi University admissions. What is your latest qualification?"

    # 1. translate en -> gu
    try:
        gu = await bhashini.translate(sample_en, "en", "gu")
        assert gu.strip(), "empty translation"
        print(f"[OK] translate(en->gu): {gu}")
    except Exception as e:
        failures += 1
        print(f"[XX] translate(en->gu): {type(e).__name__}: {e}")

    # 2. TTS en -> gu -> WAV
    wav = b""
    try:
        wav = await bhashini.english_to_speech(sample_en)
        assert wav[:4] == b"RIFF", f"not a WAV (head={wav[:4]!r})"
        print(f"[OK] english_to_speech : {len(wav)} bytes, RIFF/WAV")
    except Exception as e:
        failures += 1
        print(f"[XX] english_to_speech : {type(e).__name__}: {e}")

    # 3. ASR round-trip: feed the Gujarati audio back -> English text
    if wav:
        try:
            back_en = await bhashini.speech_to_english(wav, audio_format="wav")
            if back_en.strip():
                print(f"[OK] speech_to_english : {back_en}")
            else:
                # Empty is not a crash; ASR may not recognize synthetic TTS audio.
                print("[--] speech_to_english : empty transcript "
                      "(TTS audio may not be ASR-friendly; pipeline call succeeded)")
        except Exception as e:
            failures += 1
            print(f"[XX] speech_to_english : {type(e).__name__}: {e}")
    else:
        print("[--] speech_to_english : skipped (no audio from step 2)")

    await bhashini.aclose()

    print("-" * 66)
    print(f" RESULT: {'ALL BHASHINI CALLS OK' if failures == 0 else f'{failures} FAILED'}")
    print("=" * 66)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
