"""config.py — Central configuration loader"""
import os, json
from dotenv import load_dotenv
load_dotenv()

EXOTEL_API_KEY      = os.getenv("EXOTEL_API_KEY", "")
EXOTEL_API_TOKEN    = os.getenv("EXOTEL_API_TOKEN", "")
EXOTEL_ACCOUNT_SID  = os.getenv("EXOTEL_ACCOUNT_SID", "shubhammotors1")
EXOTEL_PHONE_NUMBER = os.getenv("EXOTEL_PHONE_NUMBER", "+919513886363")
EXOTEL_SUBDOMAIN    = os.getenv("EXOTEL_SUBDOMAIN", "api.exotel.com")

# Airtel IQ — Indian number provider, competitive pricing
# Get API credentials from: https://iq.airtel.in/developer
AIRTEL_IQ_API_KEY      = os.getenv("AIRTEL_IQ_API_KEY", "")
AIRTEL_IQ_API_SECRET   = os.getenv("AIRTEL_IQ_API_SECRET", "")
AIRTEL_IQ_ACCOUNT_ID   = os.getenv("AIRTEL_IQ_ACCOUNT_ID", "")
AIRTEL_IQ_PHONE_NUMBER = os.getenv("AIRTEL_IQ_PHONE_NUMBER", "")
AIRTEL_IQ_SUBDOMAIN    = os.getenv("AIRTEL_IQ_SUBDOMAIN", "api.airtel.in")

# Plivo — Recommended Exotel alternative. Indian DIDs, self-service signup.
# Sign up + buy number: https://console.plivo.com (free trial credit)
# Auth ID + Token from: console.plivo.com → Dashboard (top right)
PLIVO_AUTH_ID      = os.getenv("PLIVO_AUTH_ID", "")
PLIVO_AUTH_TOKEN   = os.getenv("PLIVO_AUTH_TOKEN", "")
PLIVO_PHONE_NUMBER = os.getenv("PLIVO_PHONE_NUMBER", "")

# Ozonetel KooKoo — Indian company, Indian DIDs, self-service, good developer API.
# Sign up: https://kookoo.in | Docs: https://kookoo.in/devcenter
OZONETEL_API_KEY      = os.getenv("OZONETEL_API_KEY", "")
OZONETEL_PHONE_NUMBER = os.getenv("OZONETEL_PHONE_NUMBER", "")

# TELEPHONY_PROVIDER: "exotel" | "plivo" | "ozonetel" | "airtel_iq"
TELEPHONY_PROVIDER = os.getenv("TELEPHONY_PROVIDER", "exotel")

# Groq — 10x faster than OpenAI, 10x cheaper. Best for real-time voice AI.
# Get free API key: https://console.groq.com
# Models: llama-3.3-70b-versatile (best), llama-3.1-8b-instant (fastest)
GROQ_API_KEY        = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL          = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

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
