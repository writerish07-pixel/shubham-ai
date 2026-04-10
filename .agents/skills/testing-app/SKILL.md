# Testing the Shubham Motors AI Voice Agent

## Starting the Server
```bash
cd /home/ubuntu/repos/shubham-ai
uvicorn main:app --host 0.0.0.0 --port 5000
```
Server runs on port 5000. The `.env` file must be present in the repo root with API credentials (Exotel, Groq, Sarvam, Deepgram).

## Startup Verification
After ~5 seconds, server logs should show:
- `Hero bike catalog loaded`
- `[Startup] Learning system ready: N vectors in FAISS`
- `[PhraseCache] Cached: ...`

If learning preload fails, you'll see `[Startup] Learning system preload failed: ...`

## Key Test Endpoints

### Health Check
```bash
curl http://localhost:5000/health
```

### Self-Learning Verification (POST only)
```bash
curl -s -X POST "http://localhost:5000/api/learning/verify" | python -m json.tool
```
Expected: `verdict: "WORKING"`, `stored: true`, `retrieved: true`, `top_score > 0.45`

### Learning Status
```bash
curl -s http://localhost:5000/api/learning/status | python -m json.tool
```
Expected: `learning_enabled: true`, `vector_db_status: "active"`, `vector_db_entries >= 0`

### Intelligence Summary
```bash
curl -s http://localhost:5000/api/intelligence/summary | python -m json.tool
```

### Dashboard (browser)
Open `http://localhost:5000/dashboard` — should show lead status cards plus "Learnings" and "Self-Learn" cards.

## Key Directories
- `data/vector_db/` — FAISS index + metadata
- `data/documents/` — uploaded PDFs/images
- `data/intelligence/` — competitor loss JSON files
- `data/learnings.json` — structured learnings from calls

## Notes
- The `/api/learning/verify` endpoint stores a test entry in the vector DB each time it's called. Don't call it excessively in production.
- WebSocket voice stream endpoint is at `/voicebot-stream` — requires Exotel or compatible audio WebSocket client.
- All learning runs async in the background — should not impact call latency.
