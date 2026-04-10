"""
config.py — Central configuration loader with validation.

OPTIMIZATIONS:
- Added GROQ_FAST_MODEL for hybrid model routing (small/fast queries)
- Added GROQ_SMART_MODEL for complex queries
- Added latency-related configuration constants
- Added streaming and performance tuning knobs

SELF-LEARNING:
- Vector DB / FAISS settings for RAG retrieval
- Document learning settings (chunk size, upload limits)
- Sales intelligence settings (competitor brands, loss categories)
- Background learning pipeline toggle
"""
import os
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("shubham-ai")

# -- Exotel telephony ---------------------------------------------------------
EXOTEL_API_KEY      = os.getenv("EXOTEL_API_KEY", "").strip()
EXOTEL_API_TOKEN    = os.getenv("EXOTEL_API_TOKEN", "").strip()
EXOTEL_ACCOUNT_SID  = os.getenv("EXOTEL_ACCOUNT_SID", "shubhammotors1").strip()
EXOTEL_PHONE_NUMBER = os.getenv("EXOTEL_PHONE_NUMBER", "+919513886363").strip()
EXOTEL_SUBDOMAIN    = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com").strip()
EXOTEL_APP_ID       = os.getenv("EXOTEL_APP_ID", "1186396")

# -- AI / ML APIs -------------------------------------------------------------
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "").strip()

# Hybrid model routing — fast model for simple queries, smart model for complex
GROQ_FAST_MODEL     = os.getenv("GROQ_FAST_MODEL", "llama-3.1-8b-instant").strip()
GROQ_SMART_MODEL    = os.getenv("GROQ_SMART_MODEL", "llama-3.3-70b-versatile").strip()
GROQ_MODEL          = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

DEEPGRAM_API_KEY    = os.getenv("DEEPGRAM_API_KEY", "").strip()
SARVAM_API_KEY      = os.getenv("SARVAM_API_KEY", "").strip()
NGROK_AUTH_TOKEN    = os.getenv("NGROK_AUTH_TOKEN", "").strip()

# -- Google Sheets (optional) -------------------------------------------------
GOOGLE_SHEET_ID     = os.getenv("GOOGLE_SHEET_ID", "").strip()
try:
    GOOGLE_CREDENTIALS = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON", "{}"))
except Exception:
    GOOGLE_CREDENTIALS = {}

# -- Business info ------------------------------------------------------------
BUSINESS_NAME       = os.getenv("BUSINESS_NAME", "Shubham Motors").strip()
BUSINESS_CITY       = os.getenv("BUSINESS_CITY", "Jaipur").strip()
WEBSITE_URL         = os.getenv("WEBSITE_URL", "").strip()
WORKING_HOURS_START = int(os.getenv("WORKING_HOURS_START", "9"))
WORKING_HOURS_END   = int(os.getenv("WORKING_HOURS_END", "19"))
WORKING_DAYS        = [
    d.strip() for d in os.getenv(
        "WORKING_DAYS",
        "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday",
    ).split(",")
    if d.strip()
]

# -- Sales team ---------------------------------------------------------------
SALES_TEAM = []
for _i in range(1, 6):
    _n = (os.getenv(f"SALESPERSON_{_i}_NAME") or "").strip()
    _m = (os.getenv(f"SALESPERSON_{_i}_MOBILE") or "").strip()
    if _n and _m:
        SALES_TEAM.append({"name": _n, "mobile": _m})

# -- Call settings ------------------------------------------------------------
MAX_FOLLOWUP_ATTEMPTS   = int(os.getenv("MAX_FOLLOWUP_ATTEMPTS", "3"))
DEFAULT_FOLLOWUP_TIME   = os.getenv("DEFAULT_FOLLOWUP_TIME", "10:00").strip()
DEFAULT_LANGUAGE        = os.getenv("DEFAULT_LANGUAGE", "hinglish").strip()
SILENCE_TIMEOUT_SECONDS = int(os.getenv("SILENCE_TIMEOUT_SECONDS", "5"))
PUBLIC_URL              = os.getenv("PUBLIC_URL", "http://localhost:5000").strip()
PORT                    = int(os.getenv("PORT", "5000"))

# Latency tuning constants
STT_TIMEOUT_SEC         = float(os.getenv("STT_TIMEOUT_SEC", "8.0"))
LLM_TIMEOUT_SEC         = float(os.getenv("LLM_TIMEOUT_SEC", "6.0"))
TTS_TIMEOUT_SEC         = float(os.getenv("TTS_TIMEOUT_SEC", "6.0"))
RECORDING_DOWNLOAD_TIMEOUT = float(os.getenv("RECORDING_DOWNLOAD_TIMEOUT", "8.0"))

# Token limits tuned for complete sentences without mid-sentence cutoffs
LLM_MAX_TOKENS_FAST     = int(os.getenv("LLM_MAX_TOKENS_FAST", "100"))
LLM_MAX_TOKENS_SMART    = int(os.getenv("LLM_MAX_TOKENS_SMART", "150"))

# Minimum tokens floor — talk ratio enforcement cannot reduce below this
LLM_MIN_TOKENS_FLOOR    = int(os.getenv("LLM_MIN_TOKENS_FLOOR", "80"))

THREAD_POOL_SIZE        = int(os.getenv("THREAD_POOL_SIZE", "16"))

# WebSocket audio buffer — 32000 bytes = ~2s at 8kHz/16-bit mono
WS_AUDIO_BUFFER_THRESHOLD = int(os.getenv("WS_AUDIO_BUFFER_THRESHOLD", "32000"))

# End-of-speech silence detection (700ms = balanced between interruption and sluggishness)
END_OF_SPEECH_SILENCE_MS  = int(os.getenv("END_OF_SPEECH_SILENCE_MS", "700"))

# Minimum audio bytes to consider as valid speech (filters noise/breathing)
MIN_SPEECH_BYTES          = int(os.getenv("MIN_SPEECH_BYTES", "8000"))

# User interrupt detection — AI stops speaking when user starts
AI_INTERRUPT_ENABLED      = os.getenv("AI_INTERRUPT_ENABLED", "true").strip().lower() == "true"

# Response validation — retry incomplete responses up to N times
MAX_RESPONSE_RETRIES      = int(os.getenv("MAX_RESPONSE_RETRIES", "1"))

# Talk ratio target — AI 30%, customer 70%
TALK_RATIO_TARGET         = float(os.getenv("TALK_RATIO_TARGET", "0.30"))
TALK_RATIO_HARD_LIMIT     = float(os.getenv("TALK_RATIO_HARD_LIMIT", "0.40"))


# ── Self-learning system ─────────────────────────────────────────────────────

# Data directories
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

VECTOR_DB_DIR = DATA_DIR / "vector_db"
VECTOR_DB_DIR.mkdir(exist_ok=True)

DOCUMENTS_DIR = DATA_DIR / "documents"
DOCUMENTS_DIR.mkdir(exist_ok=True)

INTELLIGENCE_DIR = DATA_DIR / "intelligence"
INTELLIGENCE_DIR.mkdir(exist_ok=True)

# Vector DB / Embedding settings
EMBEDDING_MODEL     = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2").strip()
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "384"))

# RAG retrieval settings
RAG_TOP_K          = int(os.getenv("RAG_TOP_K", "3"))
RAG_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.45"))

# Learning pipeline settings
LEARNINGS_FILE         = DATA_DIR / "learnings.json"
OBJECTIONS_FILE        = DATA_DIR / "objections.json"
COMPETITOR_LOSSES_FILE = INTELLIGENCE_DIR / "competitor_losses.json"
DEALER_LOSSES_FILE     = INTELLIGENCE_DIR / "dealer_losses.json"

MAX_TRANSCRIPT_LENGTH = int(os.getenv("MAX_TRANSCRIPT_LENGTH", "4000"))
LEARNING_ENABLED      = os.getenv("LEARNING_ENABLED", "true").strip().lower() == "true"

# Document learning settings
MAX_UPLOAD_SIZE    = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))
DOC_CHUNK_SIZE     = int(os.getenv("DOC_CHUNK_SIZE", "500"))
DOC_CHUNK_OVERLAP  = int(os.getenv("DOC_CHUNK_OVERLAP", "50"))

# Sales intelligence — competitor brands for detection
COMPETITOR_BRANDS = [
    "bajaj", "tvs", "honda", "yamaha", "suzuki", "royal enfield",
    "ktm", "kawasaki", "bmw", "jawa", "ola", "ather", "revolt",
]

LOSS_REASON_CATEGORIES = [
    "price", "mileage", "brand_trust", "availability", "discount",
    "service", "features", "resale_value", "behavior", "finance", "other",
]


# -- Startup validation -------------------------------------------------------
def validate_config() -> list:
    """Return a list of warnings about missing/invalid configuration."""
    warnings = []
    if not EXOTEL_API_KEY:
        warnings.append("EXOTEL_API_KEY is not set -- outbound calls will fail")
    if not EXOTEL_API_TOKEN:
        warnings.append("EXOTEL_API_TOKEN is not set -- outbound calls will fail")
    if not GROQ_API_KEY:
        warnings.append("GROQ_API_KEY is not set -- AI conversations will fail")
    if not SARVAM_API_KEY:
        warnings.append("SARVAM_API_KEY is not set -- TTS/STT will fall back to Deepgram only")
    if not DEEPGRAM_API_KEY:
        warnings.append("DEEPGRAM_API_KEY is not set -- STT fallback unavailable")
    if PUBLIC_URL == "http://localhost:5000" or "localhost" in PUBLIC_URL:
        warnings.append(
            "PUBLIC_URL is localhost -- Exotel callbacks will fail. "
            "Set PUBLIC_URL env var to your Render/ngrok URL, or it will be auto-detected from the first incoming request."
        )
    if not SALES_TEAM:
        warnings.append("No salesperson configured -- hot lead assignment disabled")
    return warnings
