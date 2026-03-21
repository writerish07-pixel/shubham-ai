# 🏍️ Shubham Motors AI Voice Agent

An AI-powered voice calling agent for **Shubham Motors**, a Hero MotoCorp authorized dealership in Jaipur, Rajasthan. This system replaces human telecallers with an intelligent AI agent that handles both inbound and outbound calls, manages leads, schedules follow-ups, and improves conversion rates.

## 🌟 Features

- **AI Voice Conversations**: Natural Hinglish conversations using Groq LLM + Sarvam AI TTS/STT
- **Lead Management**: Auto-capture, scoring, and classification (Hot/Warm/Cold/Dead)
- **Automated Follow-ups**: Scheduled calls based on lead status and engagement
- **Sales Intelligence**: Dynamic pitch adjustment based on customer responses
- **Dashboard**: Real-time stats and lead management via web UI
- **Multi-channel Support**: Exotel telephony integration with webhook-based call handling
- **Offer Management**: Upload and parse PDF/Excel offers automatically

## 🏗️ Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Exotel        │────▶│   FastAPI       │────▶│   Groq LLM      │
│   (Telephony)   │     │   Server        │     │   (AI Brain)   │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │                        │
                               ▼                        ▼
                        ┌─────────────────┐     ┌─────────────────┐
                        │   Sarvam AI     │     │   Lead Manager  │
                        │   (TTS/STT)     │     │   & Scheduler   │
                        └─────────────────┘     └─────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- Exotel account (API Key, Token, Account SID)
- Groq API key (for LLM)
- Sarvam AI API key (for TTS/STT)
- Deepgram API key (optional, for STT fallback)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd shubham-motors-ai
   ```

2. **Create virtual environment**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or
   venv\Scripts\activate     # Windows
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

5. **Run the server**
   ```bash
   python main.py
   ```

The server will start at `http://localhost:5000`

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `EXOTEL_API_KEY` | Exotel API Key | Yes |
| `EXOTEL_API_TOKEN` | Exotel API Token | Yes |
| `EXOTEL_ACCOUNT_SID` | Exotel Account SID | Yes |
| `EXOTEL_PHONE_NUMBER` | Your Exophone number | Yes |
| `GROQ_API_KEY` | Groq API key | Yes |
| `SARVAM_API_KEY` | Sarvam AI API key | Yes |
| `DEEPGRAM_API_KEY` | Deepgram API key (optional) | No |
| `PUBLIC_URL` | Public URL for webhooks | Yes (production) |
| `TWILIO_*` | Twilio credentials (optional backup) | No |

### Business Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `BUSINESS_NAME` | Shubham Motors | Dealership name |
| `BUSINESS_CITY` | Jaipur | City location |
| `WORKING_HOURS_START` | 9 | Start hour (24h) |
| `WORKING_HOURS_END` | 19 | End hour (24h) |
| `WORKING_DAYS` | Mon-Sat | Working days |
| `MAX_FOLLOWUP_ATTEMPTS` | 3 | Max call attempts before marking dead |

## 📡 API Endpoints

### Webhooks (Exotel)

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/call/incoming` | POST | Handle incoming calls |
| `/call/handler` | POST | Outbound call handler |
| `/call/gather/{call_sid}` | POST | Handle customer audio recording |
| `/call/status` | POST | Call status updates |
| `/call/audio/opening/{call_sid}` | GET | Stream opening greeting |
| `/call/audio/response/{call_sid}` | GET | Stream AI response |

### REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Root status |
| `/health` | GET | Health check |
| `/dashboard` | GET | Admin dashboard HTML |
| `/api/leads` | GET | List all leads |
| `/api/leads/add` | POST | Add new lead |
| `/api/leads/import` | POST | Import leads from Excel |
| `/api/call/make` | POST | Trigger outbound call |
| `/api/offers/upload` | POST | Upload offer file |
| `/api/stats` | GET | Dashboard statistics |

## 🔧 Development

### Running Tests

```bash
pytest tests/ -v
```

### Project Structure

```
.
├── main.py              # FastAPI server & webhooks
├── agent.py             # AI conversation manager
├── call_handler.py      # Call session management
├── config.py            # Configuration
├── exotel_client.py     # Exotel API client
├── lead_manager.py      # Lead processing logic
├── sheets_manager.py    # Local JSON storage
├── scheduler.py         # Follow-up automation
├── scraper.py           # Hero website scraper
├── voice.py             # TTS/STT integration
├── keep_alive.py        # Server ping for Render
├── requirements.txt     # Dependencies
├── .env.example         # Environment template
└── tests/               # Test suite
```

## ☁️ Deployment (Render)

1. Create a new Web Service on Render
2. Connect your GitHub repository
3. Configure environment variables in Render dashboard
4. Set build command: `pip install -r requirements.txt`
5. Set start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Render YAML

The included `render.yaml` handles automatic deployment configuration.

## 📊 Lead Scoring

Leads are automatically classified:

| Category | Criteria |
|----------|----------|
| 🔥 HOT | Ready to buy within 1 week, has budget |
| 🟡 WARM | Interested, 2-4 weeks timeline |
| ❄️ COLD | Vague interest, needs nurturing |
| ☠️ DEAD | Not interested, max attempts reached |

## 🔄 Automated Workflow

1. **New Lead Import** → Added to queue
2. **Morning Run (9:30 AM)** → AI calls new leads
3. **Call Analysis** → Lead scored & categorized
4. **Hot Leads** → Immediately assigned to salesperson
5. **Follow-up Queue** → Scheduled calls based on next_followup time
6. **Feedback Loop** → AI learns from successful conversions

## 🔐 Security

- API keys stored in environment variables
- No sensitive data in code
- Webhook signature verification (recommended for production)

## 📝 License

Private - Shubham Motors Internal Use Only

## 👤 Author

Built for Shubham Motors, Jaipur by AI Voice Agent Team
