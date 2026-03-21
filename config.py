"""config.py — Central configuration loader with validation."""
import os
import json
import logging

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("shubham-ai")

# -- Exotel telephony ---------------------------------------------------------
EXOTEL_API_KEY      = os.getenv("EXOTEL_API_KEY", "").strip()
EXOTEL_API_TOKEN    = os.getenv("EXOTEL_API_TOKEN", "").strip()
EXOTEL_ACCOUNT_SID  = os.getenv("EXOTEL_ACCOUNT_SID", "shubhammotors1").strip()
EXOTEL_PHONE_NUMBER = os.getenv("EXOTEL_PHONE_NUMBER", "+919513886363").strip()
EXOTEL_SUBDOMAIN    = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com").strip()

# -- AI / ML APIs -------------------------------------------------------------
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "").strip()
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

# -- Human Agent Transfer -------------------------------------------------------
# Primary agent for transfer (salesperson)
PRIMARY_AGENT_NUMBER    = os.getenv("PRIMARY_AGENT_NUMBER", "").strip()
PRIMARY_AGENT_NAME     = os.getenv("PRIMARY_AGENT_NAME", "Sales Agent").strip()

# Secondary agents (can be rotated)
AGENT_NUMBERS = []
for i in range(1, 6):
    agent_num = (os.getenv(f"AGENT_{i}_NUMBER") or "").strip()
    agent_name = (os.getenv(f"AGENT_{i}_NAME") or f"Agent {i}").strip()
    if agent_num:
        AGENT_NUMBERS.append({"number": agent_num, "name": agent_name})

# Transfer trigger - customer can say keywords or press a key
TRANSFER_KEYWORDS = [
    "transfer", "agent", "manager", "supervisor", "human",
    "baat karna hai", "agent se baat karni hai", "aadmi se baat karna hai",
    "madad", "sirf manager"
]
# DTMF key for transfer (customer presses this during call)
TRANSFER_DTMF_KEY = os.getenv("TRANSFER_DTMF_KEY", "0")


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
    if PUBLIC_URL == "http://localhost:5000":
        warnings.append("PUBLIC_URL is localhost -- Exotel webhooks require a public URL (use ngrok)")
    if not SALES_TEAM:
        warnings.append("No salesperson configured -- hot lead assignment disabled")
    if not PRIMARY_AGENT_NUMBER and not AGENT_NUMBERS:
        warnings.append("No human agent configured -- transfer to human will not work")
    return warnings
