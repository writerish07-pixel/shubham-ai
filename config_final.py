"""
config_final.py — Configuration for self-learning sales agent system (FIXED).

🔥 FIX: This is the corrected version of config_learning.py.
ISSUE: config_learning.py imported from `config_optimized` which was RENAMED to `config`
during the repo cleanup (PR #13). This caused an ImportError on every import.

FIX: Changed `import config_optimized as _base` → `import config as _base`
Also added missing re-exports: LLM_MIN_TOKENS_FLOOR, END_OF_SPEECH_SILENCE_MS, MIN_SPEECH_BYTES

To activate: Replace config_learning.py with this file (or rename).
"""
import os
import logging
from pathlib import Path

from dotenv import load_dotenv

# 🔥 FIX: Import from `config` (was `config_optimized` — file was renamed in PR #13)
import config as _base

load_dotenv()

log = logging.getLogger("shubham-ai.config-learning")

# ── Re-export all base config ─────────────────────────────────────────────────
# This allows `import config_final as config` to be a drop-in replacement
EXOTEL_API_KEY = _base.EXOTEL_API_KEY
EXOTEL_API_TOKEN = _base.EXOTEL_API_TOKEN
EXOTEL_ACCOUNT_SID = _base.EXOTEL_ACCOUNT_SID
EXOTEL_PHONE_NUMBER = _base.EXOTEL_PHONE_NUMBER
EXOTEL_SUBDOMAIN = _base.EXOTEL_SUBDOMAIN
EXOTEL_APP_ID = _base.EXOTEL_APP_ID

GROQ_API_KEY = _base.GROQ_API_KEY
GROQ_FAST_MODEL = _base.GROQ_FAST_MODEL
GROQ_SMART_MODEL = _base.GROQ_SMART_MODEL
GROQ_MODEL = _base.GROQ_MODEL

DEEPGRAM_API_KEY = _base.DEEPGRAM_API_KEY
SARVAM_API_KEY = _base.SARVAM_API_KEY
NGROK_AUTH_TOKEN = _base.NGROK_AUTH_TOKEN

GOOGLE_SHEET_ID = _base.GOOGLE_SHEET_ID
GOOGLE_CREDENTIALS = _base.GOOGLE_CREDENTIALS

BUSINESS_NAME = _base.BUSINESS_NAME
BUSINESS_CITY = _base.BUSINESS_CITY
WEBSITE_URL = _base.WEBSITE_URL
WORKING_HOURS_START = _base.WORKING_HOURS_START
WORKING_HOURS_END = _base.WORKING_HOURS_END
WORKING_DAYS = _base.WORKING_DAYS

SALES_TEAM = _base.SALES_TEAM

MAX_FOLLOWUP_ATTEMPTS = _base.MAX_FOLLOWUP_ATTEMPTS
DEFAULT_FOLLOWUP_TIME = _base.DEFAULT_FOLLOWUP_TIME
DEFAULT_LANGUAGE = _base.DEFAULT_LANGUAGE
SILENCE_TIMEOUT_SECONDS = _base.SILENCE_TIMEOUT_SECONDS
PUBLIC_URL = _base.PUBLIC_URL
PORT = _base.PORT

STT_TIMEOUT_SEC = _base.STT_TIMEOUT_SEC
LLM_TIMEOUT_SEC = _base.LLM_TIMEOUT_SEC
TTS_TIMEOUT_SEC = _base.TTS_TIMEOUT_SEC
RECORDING_DOWNLOAD_TIMEOUT = _base.RECORDING_DOWNLOAD_TIMEOUT

LLM_MAX_TOKENS_FAST = _base.LLM_MAX_TOKENS_FAST
LLM_MAX_TOKENS_SMART = _base.LLM_MAX_TOKENS_SMART

# 🔥 FIX: Added missing re-export — used by agent.py talk ratio enforcement
LLM_MIN_TOKENS_FLOOR = _base.LLM_MIN_TOKENS_FLOOR

THREAD_POOL_SIZE = _base.THREAD_POOL_SIZE
WS_AUDIO_BUFFER_THRESHOLD = _base.WS_AUDIO_BUFFER_THRESHOLD

# 🔥 FIX: Added missing re-exports — used by main.py WebSocket handler
END_OF_SPEECH_SILENCE_MS = _base.END_OF_SPEECH_SILENCE_MS
MIN_SPEECH_BYTES = _base.MIN_SPEECH_BYTES

validate_config = _base.validate_config


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING: New configuration for learning system
# ══════════════════════════════════════════════════════════════════════════════

# ── Data directories ──────────────────────────────────────────────────────────
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# Vector DB storage
VECTOR_DB_DIR = DATA_DIR / "vector_db"
VECTOR_DB_DIR.mkdir(exist_ok=True)

# Document storage for uploaded PDFs/images
DOCUMENTS_DIR = DATA_DIR / "documents"
DOCUMENTS_DIR.mkdir(exist_ok=True)

# Sales intelligence data
INTELLIGENCE_DIR = DATA_DIR / "intelligence"
INTELLIGENCE_DIR.mkdir(exist_ok=True)

# ── Vector DB / Embedding settings ────────────────────────────────────────────
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2").strip()
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "384"))

# How many past learnings to inject into RAG prompt
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))

# Minimum similarity score for RAG retrieval (0-1)
RAG_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.45"))

# ── Learning pipeline settings ────────────────────────────────────────────────
LEARNINGS_FILE = DATA_DIR / "learnings.json"
OBJECTIONS_FILE = DATA_DIR / "objections.json"
COMPETITOR_LOSSES_FILE = INTELLIGENCE_DIR / "competitor_losses.json"
DEALER_LOSSES_FILE = INTELLIGENCE_DIR / "dealer_losses.json"

# Max transcript length to analyze (chars) — prevents huge LLM calls
MAX_TRANSCRIPT_LENGTH = int(os.getenv("MAX_TRANSCRIPT_LENGTH", "4000"))

# Background learning — runs async after call ends
LEARNING_ENABLED = os.getenv("LEARNING_ENABLED", "true").strip().lower() == "true"

# ── Document learning settings ────────────────────────────────────────────────
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))

DOC_CHUNK_SIZE = int(os.getenv("DOC_CHUNK_SIZE", "500"))
DOC_CHUNK_OVERLAP = int(os.getenv("DOC_CHUNK_OVERLAP", "50"))

# ── Sales intelligence settings ───────────────────────────────────────────────
COMPETITOR_BRANDS = [
    "bajaj", "tvs", "honda", "yamaha", "suzuki", "royal enfield",
    "ktm", "kawasaki", "bmw", "jawa", "ola", "ather", "revolt",
]

LOSS_REASON_CATEGORIES = [
    "price",           # Too expensive / got better price elsewhere
    "mileage",         # Better mileage from competitor
    "brand_trust",     # Trusts competitor brand more
    "availability",    # Model not available / long delivery time
    "discount",        # Got better discount from competitor dealer
    "service",         # Better service center / after-sales from competitor
    "features",        # Better features in competitor model
    "resale_value",    # Better resale value perception
    "behavior",        # Salesperson behavior / experience at dealership
    "finance",         # Better finance/EMI options elsewhere
    "other",           # Other reasons
]
