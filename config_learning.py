"""
config_learning.py — Configuration for self-learning sales agent system.

🔥 SELF-LEARNING ADDED: New configuration constants for:
- Vector database (FAISS) settings
- Learning pipeline parameters
- Document ingestion settings
- Sales intelligence tracking
- RAG (Retrieval-Augmented Generation) parameters

Extends config_optimized.py — import that first, then override/add here.
"""
import os
import logging
from pathlib import Path

from dotenv import load_dotenv

# 🔥 SELF-LEARNING ADDED: Import all base config from optimized version
import config_optimized as _base

load_dotenv()

log = logging.getLogger("shubham-ai.config-learning")

# ── Re-export all base config ─────────────────────────────────────────────────
# This allows `import config_learning as config` to be a drop-in replacement
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

THREAD_POOL_SIZE = _base.THREAD_POOL_SIZE
WS_AUDIO_BUFFER_THRESHOLD = _base.WS_AUDIO_BUFFER_THRESHOLD

validate_config = _base.validate_config


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: New configuration for learning system
# ══════════════════════════════════════════════════════════════════════════════

# ── Data directories ──────────────────────────────────────────────────────────
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

# 🔥 SELF-LEARNING ADDED: Vector DB storage
VECTOR_DB_DIR = DATA_DIR / "vector_db"
VECTOR_DB_DIR.mkdir(exist_ok=True)

# 🔥 SELF-LEARNING ADDED: Document storage for uploaded PDFs/images
DOCUMENTS_DIR = DATA_DIR / "documents"
DOCUMENTS_DIR.mkdir(exist_ok=True)

# 🔥 SELF-LEARNING ADDED: Sales intelligence data
INTELLIGENCE_DIR = DATA_DIR / "intelligence"
INTELLIGENCE_DIR.mkdir(exist_ok=True)

# ── Vector DB / Embedding settings ────────────────────────────────────────────
# 🔥 SELF-LEARNING ADDED: Embedding model — small, fast, good quality
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2").strip()
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "384"))

# 🔥 SELF-LEARNING ADDED: How many past learnings to inject into RAG prompt
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))

# 🔥 SELF-LEARNING ADDED: Minimum similarity score for RAG retrieval (0-1)
RAG_MIN_SIMILARITY = float(os.getenv("RAG_MIN_SIMILARITY", "0.45"))

# ── Learning pipeline settings ────────────────────────────────────────────────
# 🔥 SELF-LEARNING ADDED: JSON files for structured learning data
LEARNINGS_FILE = DATA_DIR / "learnings.json"
OBJECTIONS_FILE = DATA_DIR / "objections.json"
COMPETITOR_LOSSES_FILE = INTELLIGENCE_DIR / "competitor_losses.json"
DEALER_LOSSES_FILE = INTELLIGENCE_DIR / "dealer_losses.json"

# 🔥 SELF-LEARNING ADDED: Max transcript length to analyze (chars) — prevents huge LLM calls
MAX_TRANSCRIPT_LENGTH = int(os.getenv("MAX_TRANSCRIPT_LENGTH", "4000"))

# 🔥 SELF-LEARNING ADDED: Background learning — runs async after call ends
LEARNING_ENABLED = os.getenv("LEARNING_ENABLED", "true").strip().lower() == "true"

# ── Document learning settings ────────────────────────────────────────────────
# 🔥 SELF-LEARNING ADDED: Max file size for upload (bytes) — 10MB default
MAX_UPLOAD_SIZE = int(os.getenv("MAX_UPLOAD_SIZE", str(10 * 1024 * 1024)))

# 🔥 SELF-LEARNING ADDED: Chunk size for document embedding (chars)
DOC_CHUNK_SIZE = int(os.getenv("DOC_CHUNK_SIZE", "500"))
DOC_CHUNK_OVERLAP = int(os.getenv("DOC_CHUNK_OVERLAP", "50"))

# ── Sales intelligence settings ───────────────────────────────────────────────
# 🔥 SELF-LEARNING ADDED: Competitor brands to detect
COMPETITOR_BRANDS = [
    "bajaj", "tvs", "honda", "yamaha", "suzuki", "royal enfield",
    "ktm", "kawasaki", "bmw", "jawa", "ola", "ather", "revolt",
]

# 🔥 SELF-LEARNING ADDED: Loss reason categories
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
