"""Central configuration loaded from environment / .env."""
import os
from dotenv import load_dotenv

load_dotenv()


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


# OpenAI
OPENAI_API_KEY = _get("OPENAI_API_KEY")
OPENAI_MODEL = _get("OPENAI_MODEL", "gpt-4o-mini")

# Bhashini
# --- Direct-inference mode (you only have a Udyat key + an Inference key) ---
# When BHASHINI_INFERENCE_KEY is set we call the Dhruva inference endpoint
# directly with fixed Gujarati service ids and skip getModelsPipeline (no userID needed).
BHASHINI_UDYAT_KEY = _get("BHASHINI_UDYAT_KEY")
BHASHINI_INFERENCE_KEY = _get("BHASHINI_INFERENCE_KEY")
BHASHINI_INFERENCE_URL = _get(
    "BHASHINI_INFERENCE_URL",
    "https://dhruva-api.bhashini.gov.in/services/inference/pipeline",
)
# Header name Bhashini expects for the inference key (usually "Authorization").
BHASHINI_AUTH_HEADER = _get("BHASHINI_AUTH_HEADER", "Authorization")

# --- Legacy ULCA pipeline mode (userID + ulcaApiKey) -- optional fallback ---
BHASHINI_USER_ID = _get("BHASHINI_USER_ID")
BHASHINI_API_KEY = _get("BHASHINI_API_KEY")
BHASHINI_PIPELINE_ID = _get("BHASHINI_PIPELINE_ID", "64392f96daac500b55c543cd")
BHASHINI_CONFIG_URL = _get(
    "BHASHINI_CONFIG_URL",
    "https://meity-auth.ulcacontrib.org/ulca/apis/v0/model/getModelsPipeline",
)

# Default Gujarati service ids (used in direct-inference mode; override if needed).
BHASHINI_ASR_SERVICE_ID = _get(
    "BHASHINI_ASR_SERVICE_ID",
    "ai4bharat/conformer-multilingual-indo_aryan-gpu--t4",
)
BHASHINI_NMT_SERVICE_ID = _get(
    "BHASHINI_NMT_SERVICE_ID",
    "ai4bharat/indictrans-v2-all-gpu--t4",
)
BHASHINI_TTS_SERVICE_ID = _get(
    "BHASHINI_TTS_SERVICE_ID",
    "ai4bharat/indic-tts-coqui-indo_aryan-gpu--t4",
)

# --- Sarvam AI (preferred provider when SARVAM_API_KEY is set) ---
SARVAM_API_KEY = _get("SARVAM_API_KEY")
SARVAM_BASE_URL = _get("SARVAM_BASE_URL", "https://api.sarvam.ai")
# saaras = speech-to-text-translate (audio -> English); saarika = speech-to-text (gu transcript)
SARVAM_STT_TRANSLATE_MODEL = _get("SARVAM_STT_MODEL", "saaras:v2.5")
SARVAM_TRANSCRIBE_MODEL = _get("SARVAM_TRANSCRIBE_MODEL", "saarika:v2.5")
SARVAM_TRANSLATE_MODEL = _get("SARVAM_TRANSLATE_MODEL", "mayura:v1")
SARVAM_TTS_MODEL = _get("SARVAM_TTS_MODEL", "bulbul:v2")
SARVAM_TTS_SPEAKER = _get("SARVAM_TTS_SPEAKER", "anushka")
# Sarvam uses BCP-47 codes (gu-IN, en-IN) rather than Bhashini's bare gu/en.
SARVAM_SOURCE_LANG = _get("SARVAM_SOURCE_LANG", "gu-IN")
SARVAM_PIVOT_LANG = _get("SARVAM_PIVOT_LANG", "en-IN")

# Languages
SOURCE_LANG = _get("SOURCE_LANG", "gu")   # caller's language
PIVOT_LANG = _get("PIVOT_LANG", "en")     # LLM reasoning language
TTS_VOICE_GENDER = _get("TTS_VOICE_GENDER", "female")
TTS_SAMPLE_RATE = int(_get("TTS_SAMPLE_RATE", "8000"))


def use_sarvam() -> bool:
    """True when Sarvam is configured; it then replaces Bhashini for voice."""
    return bool(SARVAM_API_KEY)

# Twilio
TWILIO_ACCOUNT_SID = _get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = _get("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = _get("TWILIO_FROM_NUMBER")

# Dashboard login
ADMIN_USERNAME = _get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = _get("ADMIN_PASSWORD", "marwadi123")

# Next.js console URL (the backend root redirects here; it is API-only now).
FRONTEND_URL = _get("FRONTEND_URL", "http://localhost:3000")

# Server / public URL (ngrok)
PUBLIC_BASE_URL = _get("PUBLIC_BASE_URL").rstrip("/")
HOST = _get("HOST", "0.0.0.0")
PORT = int(_get("PORT", "8000"))

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_PATH = os.path.join(BASE_DIR, "data", "degrees.json")
AUDIO_DIR = os.path.join(BASE_DIR, "static", "audio")


def direct_mode() -> bool:
    """True when we call Dhruva inference directly with an inference key."""
    return bool(BHASHINI_INFERENCE_KEY)


def assert_ready() -> None:
    """Fail fast with a clear message if critical config is missing."""
    missing = [
        n for n, v in {
            "OPENAI_API_KEY": OPENAI_API_KEY,
            "TWILIO_ACCOUNT_SID": TWILIO_ACCOUNT_SID,
            "TWILIO_AUTH_TOKEN": TWILIO_AUTH_TOKEN,
            "PUBLIC_BASE_URL": PUBLIC_BASE_URL,
        }.items() if not v
    ]
    # Voice provider: Sarvam (preferred) OR Bhashini (direct-inference / legacy ULCA).
    if not use_sarvam() and not direct_mode() and not (BHASHINI_USER_ID and BHASHINI_API_KEY):
        missing.append("SARVAM_API_KEY (or BHASHINI_INFERENCE_KEY / BHASHINI_USER_ID+BHASHINI_API_KEY)")
    if missing:
        raise RuntimeError(
            "Missing required env vars: " + ", ".join(missing) +
            ". Copy .env.example to .env and fill them in."
        )
