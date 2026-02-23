"""config.py — Central configuration loader"""
import os, json
from dotenv import load_dotenv
load_dotenv()

EXOTEL_API_KEY      = os.getenv("EXOTEL_API_KEY", "")
EXOTEL_API_TOKEN    = os.getenv("EXOTEL_API_TOKEN", "")
EXOTEL_ACCOUNT_SID  = os.getenv("EXOTEL_ACCOUNT_SID", "shubhammotors1")
EXOTEL_PHONE_NUMBER = os.getenv("EXOTEL_PHONE_NUMBER", "+919513886363")
EXOTEL_SUBDOMAIN    = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")

OPENAI_API_KEY      = os.getenv("OPENAI_API_KEY", "")
DEEPGRAM_API_KEY    = os.getenv("DEEPGRAM_API_KEY", "")
ELEVENLABS_API_KEY  = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "fG9s0SXJb213f4UxVHyG")
SARVAM_API_KEY      = os.getenv("SARVAM_API_KEY", "")

BUSINESS_NAME       = os.getenv("BUSINESS_NAME", "Shubham Motors")
BUSINESS_CITY       = os.getenv("BUSINESS_CITY", "Jaipur")
WEBSITE_URL         = os.getenv("WEBSITE_URL", "")
WORKING_HOURS_START = int(os.getenv("WORKING_HOURS_START", "9"))
WORKING_HOURS_END   = int(os.getenv("WORKING_HOURS_END", "19"))
WORKING_DAYS        = os.getenv("WORKING_DAYS", "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday").split(",")

SALES_TEAM = []
for _i in range(1, 6):
    _n = os.getenv(f"SALESPERSON_{_i}_NAME")
    _m = os.getenv(f"SALESPERSON_{_i}_MOBILE")
    if _n and _m:
        SALES_TEAM.append({"name": _n, "mobile": _m})

MAX_FOLLOWUP_ATTEMPTS   = int(os.getenv("MAX_FOLLOWUP_ATTEMPTS", "3"))
DEFAULT_FOLLOWUP_TIME   = os.getenv("DEFAULT_FOLLOWUP_TIME", "10:00")
DEFAULT_LANGUAGE        = os.getenv("DEFAULT_LANGUAGE", "hinglish")
SILENCE_TIMEOUT_SECONDS = int(os.getenv("SILENCE_TIMEOUT_SECONDS", "5"))
PUBLIC_URL              = os.getenv("PUBLIC_URL", "http://localhost:5000")
PORT                    = int(os.getenv("PORT", "5000"))
