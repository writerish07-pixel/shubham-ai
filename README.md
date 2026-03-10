# Shubham Motors AI Voice Agent

An AI-powered outbound calling bot for **Shubham Motors** (Hero MotoCorp dealership, Jaipur). The system makes automated phone calls, conducts AI voice conversations in Hindi/Hinglish, scores leads, and manages follow-ups.

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   Exotel     │────▶│  FastAPI      │────▶│  Groq LLM    │
│  Telephony   │◀────│  (main.py)    │◀────│  (llama-3.3) │
└──────────────┘     └──────┬───────┘     └──────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       ┌───────────┐ ┌──────────┐ ┌──────────┐
       │ Sarvam AI │ │ Deepgram │ │  JSON DB │
       │ TTS + STT │ │ STT      │ │ (data/)  │
       └───────────┘ └──────────┘ └──────────┘
```

### Key Components

| File | Purpose |
|---|---|
| `main.py` | FastAPI server, Exotel webhooks, API endpoints, dashboard |
| `agent.py` | AI conversation manager (Groq LLM with system prompts) |
| `call_handler.py` | Call session lifecycle (start, process, end) |
| `voice.py` | Speech-to-text (Sarvam/Deepgram) and text-to-speech (Sarvam) |
| `lead_manager.py` | Lead scoring, follow-up scheduling, salesperson assignment |
| `sheets_manager.py` | Thread-safe JSON storage for leads, calls, offers |
| `exotel_client.py` | Exotel API client with retry logic |
| `scheduler.py` | APScheduler for automated follow-ups and morning calls |
| `scraper.py` | Hero MotoCorp website scraper for bike catalog |
| `config.py` | Configuration loader with validation |

## Prerequisites

- Python 3.10+
- [Exotel](https://exotel.com/) account with API credentials
- [Groq](https://groq.com/) API key
- [Sarvam AI](https://www.sarvam.ai/) API key (for Hindi TTS/STT)
- [Deepgram](https://deepgram.com/) API key (STT fallback)
- [ngrok](https://ngrok.com/) for local development (Exotel webhooks need a public URL)

## Quick Start

### 1. Clone and install dependencies

```bash
git clone https://github.com/writerish07-pixel/shubham-ai.git
cd shubham-ai
python -m venv venv
source venv/bin/activate  # Linux/Mac
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your actual API keys and configuration
```

### 3. Start ngrok (for Exotel webhooks)

```bash
ngrok http 5000
# Copy the https URL and set it as PUBLIC_URL in .env
```

### 4. Run the server

```bash
python main.py
# Server starts on http://localhost:5000
```

### 5. Configure Exotel webhooks

In your Exotel dashboard, set these webhook URLs:
- **Incoming call**: `https://your-ngrok-url/call/incoming`
- **Outbound call**: `https://your-ngrok-url/call/outbound`
- **Call status**: `https://your-ngrok-url/call/status`

## API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Dashboard (HTML) |
| GET | `/health` | Health check |
| POST | `/call/incoming` | Exotel incoming call webhook |
| POST | `/call/outbound` | Exotel outbound call webhook |
| POST | `/call/gather` | Exotel gather (speech input) webhook |
| POST | `/call/status` | Exotel call status webhook |
| GET | `/api/leads` | List all leads |
| POST | `/api/leads/add` | Add a single lead |
| POST | `/api/leads/import` | Import leads from CSV/Excel |
| POST | `/api/call/make` | Trigger an outbound call |
| POST | `/api/offers/upload` | Upload offer/promotion file |
| GET | `/api/stats` | Dashboard statistics |
| GET | `/api/active-calls` | List active call sessions |

## Running Tests

```bash
pip install pytest pytest-asyncio httpx
python -m pytest tests/ -v
```

## Project Structure

```
shubham-ai/
├── main.py              # FastAPI application entry point
├── agent.py             # AI conversation manager (Groq LLM)
├── call_handler.py      # Call session management
├── voice.py             # TTS/STT integrations
├── lead_manager.py      # Lead scoring and follow-up logic
├── sheets_manager.py    # Thread-safe JSON storage
├── exotel_client.py     # Exotel API client
├── scheduler.py         # APScheduler automated jobs
├── scraper.py           # Hero website scraper
├── config.py            # Configuration with validation
├── import_template.py   # (Reserved for import templates)
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
├── .gitignore           # Git ignore rules
├── tests/               # Automated test suite
│   └── test_app.py      # API, storage, lead logic tests
├── data/                # JSON data storage (gitignored)
│   ├── leads.json
│   ├── calls.json
│   └── offers.json
└── uploads/             # Audio files (gitignored)
```

## Deployment

### Production Checklist

1. Set all required API keys in `.env`
2. Set `PUBLIC_URL` to your production domain (not localhost)
3. Use a process manager (e.g., `gunicorn`, `systemd`, or Docker)
4. Example with gunicorn:
   ```bash
   pip install gunicorn
   gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:5000
   ```
5. Ensure `data/` directory is persistent across deploys
6. Configure Exotel webhooks to point to your production URL
7. Monitor logs for any configuration warnings at startup

### Environment Variables

See `.env.example` for the full list of configuration options.

**Required for core functionality:**
- `EXOTEL_API_KEY`, `EXOTEL_API_TOKEN`, `EXOTEL_ACCOUNT_SID`
- `GROQ_API_KEY`
- `SARVAM_API_KEY`
- `PUBLIC_URL` (must be publicly accessible)

**Optional:**
- `DEEPGRAM_API_KEY` (STT fallback)
- `WEBSITE_URL` (Hero website for scraping; uses fallback catalog if empty)
- `GOOGLE_SHEET_ID` (not used in current JSON-based storage)
