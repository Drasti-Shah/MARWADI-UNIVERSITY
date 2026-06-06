"""No-call smoke test for the Marwadi University voice agent.

Exercises the whole pipeline WITHOUT placing a real phone call:
  1. Config            -> assert_ready() passes, secrets present
  2. Data + catalog    -> degrees.json loads, LLM catalog builds
  3. OpenAI advisor    -> simulated multi-turn conversation (text in, text out)
  4. Bhashini voice    -> en->gu translate + TTS produces real WAV bytes

ASR-from-audio and Twilio telephony are intentionally skipped (they need a
live call). Run:  python -m scripts.smoke_test
"""
from __future__ import annotations

import asyncio
import sys

# Windows consoles default to cp1252 and choke on rupee/Gujarati glyphs.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from app import config
from app.degrees import load_degrees, catalog_for_llm

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    icon = {"PASS": "[OK]", "FAIL": "[XX]", "SKIP": "[--]"}[status]
    print(f"{icon} {name}" + (f" - {detail}" if detail else ""))


# --------------------------------------------------------------------------- #
# 1. Config
# --------------------------------------------------------------------------- #
def test_config() -> None:
    try:
        config.assert_ready()
        if config.use_sarvam():
            provider = f"sarvam (stt={config.SARVAM_STT_TRANSLATE_MODEL}, tts={config.SARVAM_TTS_MODEL})"
        else:
            provider = "bhashini (" + ("direct" if config.direct_mode() else "ULCA") + ")"
        record("config.assert_ready", PASS,
               f"model={config.OPENAI_MODEL}, voice={provider}, "
               f"base_url={config.PUBLIC_BASE_URL}")
    except Exception as e:
        record("config.assert_ready", FAIL, str(e))


# --------------------------------------------------------------------------- #
# 2. Data + catalog
# --------------------------------------------------------------------------- #
def test_data() -> None:
    try:
        degrees = load_degrees()
        assert degrees, "no degrees loaded"
        required = {"id", "degree_name", "level", "suitable_for", "duration",
                    "fees", "eligibility", "required_documents"}
        for d in degrees:
            missing = required - d.keys()
            assert not missing, f"{d.get('id','?')} missing {missing}"
        record("data.load_degrees", PASS, f"{len(degrees)} degrees, all fields present")
    except Exception as e:
        record("data.load_degrees", FAIL, str(e))
        return

    try:
        catalog = catalog_for_llm()
        assert "id=" in catalog and len(catalog) > 100
        record("data.catalog_for_llm", PASS, f"{len(catalog)} chars")
    except Exception as e:
        record("data.catalog_for_llm", FAIL, str(e))


# --------------------------------------------------------------------------- #
# 3. OpenAI advisor (simulated conversation, no audio)
# --------------------------------------------------------------------------- #
async def test_advisor() -> None:
    try:
        from app.openai_agent import next_reply
    except Exception as e:
        record("advisor.import", FAIL, str(e))
        return

    # Simulate the full scripted flow: name -> confirm -> qualification -> marks
    # (cheer + degree list) -> pick degree (details, no docs) -> placement -> bye.
    turns = [
        "My name is Riya.",                            # name captured, no confirm
        "I have completed 12th Science.",              # qualification captured, no confirm
        "I scored 85 percent.",                        # marks -> expect cheer + degrees
        "Tell me about Bachelor of Computer Applications.",  # pick -> details, no documents
        "What is the placement ratio?",               # -> generic positive answer
        "Thank you, that is all. Goodbye.",
    ]
    history: list[dict] = []
    try:
        for i, user_text in enumerate(turns, 1):
            history.append({"role": "user", "content": user_text})
            result = await next_reply(history)
            reply, end = result["reply"], result["end"]
            history.append({"role": "assistant", "content": reply})
            assert reply, "empty reply from advisor"
            flags = f"end={end} name='{result['name']}' qual='{result['qualification']}'"
            if result.get("ask_marks"):
                flags += " ASK_MARKS"
            if result.get("cheer"):
                flags += " CHEER"
            print(f"      turn {i}  USER: {user_text}")
            print(f"             BOT : {reply}  ({flags})")
        record("advisor.next_reply", PASS, f"{len(turns)} turns, final end={end}")
    except Exception as e:
        record("advisor.next_reply", FAIL, f"{type(e).__name__}: {e}")


# --------------------------------------------------------------------------- #
# 4. Voice provider (en -> gu translate + TTS) -- Sarvam or Bhashini
# --------------------------------------------------------------------------- #
async def test_voice() -> None:
    try:
        from app import voice
    except Exception as e:
        record("voice.import", FAIL, str(e))
        return
    prov = voice.PROVIDER

    # translate en -> gu
    try:
        gu = await voice.translate("I have completed 12th Science.", "en", "gu")
        if gu.strip():
            record(f"{prov}.translate(en->gu)", PASS, gu)
        else:
            record(f"{prov}.translate(en->gu)", FAIL, "empty translation")
    except Exception as e:
        record(f"{prov}.translate(en->gu)", FAIL, f"{type(e).__name__}: {e}")

    # full en -> gu TTS -> WAV bytes
    try:
        wav = await voice.english_to_speech(
            "Welcome to Marwadi University admissions.")
        assert wav and len(wav) > 100, "no/too-small audio"
        head = wav[:4]
        fmt = "RIFF/WAV" if head == b"RIFF" else f"bytes (head={head!r})"
        record(f"{prov}.english_to_speech", PASS, f"{len(wav)} bytes, {fmt}")
    except Exception as e:
        record(f"{prov}.english_to_speech", FAIL, f"{type(e).__name__}: {e}")

    # fixed Gujarati phrase -> TTS (used for the marks cheer)
    try:
        wav = await voice.gu_to_speech("અરે વાહ! આ તો ખૂબ સરસ માર્ક્સ છે.")
        assert wav and len(wav) > 100, "no/too-small audio"
        record(f"{prov}.gu_to_speech", PASS, f"{len(wav)} bytes")
    except Exception as e:
        record(f"{prov}.gu_to_speech", FAIL, f"{type(e).__name__}: {e}")

    await voice.aclose()


# --------------------------------------------------------------------------- #
async def main() -> int:
    print("=" * 70)
    print(" SMOKE TEST (no phone call)  -  Marwadi University Voice Agent")
    print("=" * 70)

    print("\n[1] CONFIG")
    test_config()

    print("\n[2] DATA + CATALOG")
    test_data()

    print("\n[3] OPENAI ADVISOR  (simulated Gujarati student, text only)")
    await test_advisor()

    print("\n[4] VOICE PROVIDER  (en -> gu translate + TTS)")
    await test_voice()

    print("\n" + "=" * 70)
    n_pass = sum(1 for _, s, _ in results if s == PASS)
    n_fail = sum(1 for _, s, _ in results if s == FAIL)
    n_skip = sum(1 for _, s, _ in results if s == SKIP)
    print(f" SUMMARY: {n_pass} passed, {n_fail} failed, {n_skip} skipped "
          f"(of {len(results)} checks)")
    print("=" * 70)
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
