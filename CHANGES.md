# CHANGES.md - All Modifications Made

This document lists all changes made to the Shubham Motors AI Voice Agent codebase.

---

## Summary of Changes

| Date | Change Type | Description |
|------|-------------|-------------|
| 2026-03-20 | New Feature | Human Agent Transfer with AI Transcript Learning |
| 2026-03-20 | Bug Fix | FastAPI lifespan handler replacement |
| 2026-03-20 | Cleanup | Removed dead/commented code |
| 2026-03-20 | Config | Added environment configuration |
| 2026-03-21 | Cleanup | Removed empty files, dead code |

---

## Detailed Changes

### 1. Human Agent Transfer (New Feature)

**Files Modified:** `config.py`, `exotel_client.py`, `main.py`, `.env.example`

**Changes:**
- Added `transfer_to_human()` function in `exotel_client.py` - transfers calls via Exotel API
- Added `get_available_agent()` function for round-robin agent selection
- Added DTMF key transfer (press `0` during call)
- Added voice keyword detection (agent, manager, supervisor, etc.)
- Added `_transfer_to_human()` handler in `main.py`
- Added config variables:
  - `PRIMARY_AGENT_NUMBER` - Primary agent phone number
  - `PRIMARY_AGENT_NAME` - Agent name
  - `AGENT_NUMBERS` - List of agents for round-robin
  - `TRANSFER_KEYWORDS` - Keywords to trigger transfer
  - `TRANSFER_DTMF_KEY` - DTMF key for transfer (default: "0")

**How it works:**
1. Customer says "I want to talk to agent" OR presses `0`
2. AI says: "Okay, aapka call agent ko transfer kar rahi hoon"
3. Call transfers to human agent with full transcript
4. Lead status updated to `agent_assigned`

---

### 2. FastAPI Lifespan Handler (Bug Fix)

**File Modified:** `main.py`

**Changes:**
- Replaced deprecated `@app.on_event("startup")` and `@app.on_event("shutdown")`
- Implemented modern `@asynccontextmanager async def lifespan(app: FastAPI)` pattern
- Proper startup/shutdown for scheduler, bike catalog, and keep-alive

---

### 3. Environment Configuration (New Feature)

**File Modified:** `.env.example`

**Changes:**
- Added complete environment variable template
- Added human agent transfer configuration
- Added all API keys and settings
- Added deployment instructions

---

### 4. Removed Dead Code (Cleanup)

**Files Modified:** `main.py`

**Removed:**
- Twilio commented code (lines ~188-200)
- Duplicate incoming_call function (commented)
- Large block of commented websocket code (~130 lines)
- Duplicate serve_opening_audio function (commented)

**Files Deleted:**
- `import_template.py` - Empty file (0 bytes)

---

### 5. Keep Alive Module (New Feature)

**File Added:** `keep_alive.py`

**Purpose:**
- Ping server periodically to keep it awake on platforms like Render.com
- Prevents cold starts

---

### 6. Configuration Validation (Improvement)

**File Modified:** `config.py`

**Changes:**
- Added validation for human agent configuration
- Added warning if no agent is configured for transfers

---

## Production Dependencies

Required packages (already in requirements.txt):
- `fastapi` - Web framework
- `uvicorn` - ASGI server
- `groq` - AI LLM (Groq API)
- `requests` - HTTP requests
- `sarvamai` or direct API - TTS/STT
- `deepgram` - STT fallback
- `exotel` or direct API - Telephony
- `apscheduler` - Auto follow-up scheduling
- `pandas` - Data handling
- `python-dotenv` - Environment variables

---

## Configuration Required

Create `.env` file with:

```bash
# Exotel (Required)
EXOTEL_API_KEY=your_exotel_api_key
EXOTEL_API_TOKEN=your_exotel_api_token
EXOTEL_ACCOUNT_SID=shubhammotors1
EXOTEL_PHONE_NUMBER=+919513886363

# Groq AI (Required)
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile

# Sarvam AI (Required for TTS/STT)
SARVAM_API_KEY=your_sarvam_api_key

# Deepgram (Optional - STT fallback)
DEEPGRAM_API_KEY=your_deepgram_api_key

# Human Agent Transfer (Required for transfer feature)
PRIMARY_AGENT_NUMBER=+919999999991
PRIMARY_AGENT_NAME=Rajesh
TRANSFER_DTMF_KEY=0

# Business Info
BUSINESS_NAME=Shubham Motors
BUSINESS_CITY=Jaipur
PUBLIC_URL=https://your-app.onrender.com
```

---

## Running the Application

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Edit .env with your API keys

# Run locally
python main.py

# Or with uvicorn
uvicorn main:app --host 0.0.0.0 --port 5000
```

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root info |
| `/health` | GET | Health check |
| `/call/incoming` | POST | Exotel incoming call webhook |
| `/call/handler` | POST | Exotel call handler webhook |
| `/call/gather/{call_sid}` | POST | Speech input webhook |
| `/call/status` | POST | Call status webhook |
| `/call/stream` | WS | Real-time voice stream |
| `/api/leads` | GET | List all leads |
| `/api/leads/add` | POST | Add new lead |
| `/api/call/make` | POST | Trigger outbound call |
| `/api/import` | POST | Import leads from CSV/Excel |
| `/api/upload/offer` | POST | Upload offer file |
| `/api/stats` | GET | Dashboard statistics |
| `/dashboard` | GET | Admin dashboard HTML |

---

## Notes

- This codebase uses **Exotel** for telephony, **Sarvam AI** for TTS/STT, and **Groq** for LLM
- All Twilio-related code has been removed
- WebSocket streaming is for real-time voice (optional feature)
- Default transfer method: Customer presses `0` or says "agent"
- All conversation transcripts are saved for AI learning
