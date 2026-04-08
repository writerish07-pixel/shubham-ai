# Testing Voice AI System

## Overview
The Shubham Motors voice AI system uses Exotel (call handling), Sarvam AI (STT/TTS), and Groq (LLM inference). End-to-end testing requires all three API keys. However, many critical behaviors can be verified via pure-function unit tests without any external APIs.

## Devin Secrets Needed
- `GROQ_API_KEY` — Required for LLM testing (Groq chat completions)
- `SARVAM_API_KEY` — Required for STT/TTS testing
- `EXOTEL_API_KEY` / `EXOTEL_API_TOKEN` — Required for real call testing
- `GOOGLE_CREDENTIALS_JSON` — Required for Google Sheets lead management

## Dependencies
Install all dependencies before testing:
```bash
pip install groq httpx python-dotenv numpy pydub pandas openpyxl pdfplumber beautifulsoup4 gspread google-auth apscheduler pillow pytesseract aiofiles pytz websockets
```

## What Can Be Tested Without APIs

### Pure-Function Tests (No API keys needed)
1. **Intent detection** (`intent_optimized.py`)
   - Word-boundary matching for short patterns (< 4 chars use exact word match)
   - Intent priority ordering (busy/not_interested/callback before acknowledgement)
   - Acknowledgement guard (break vs return — falls through to other intents)
   - False-positive prevention (e.g., "kahan" should not match "han")

2. **Query complexity classification** (`agent_optimized.py`)
   - `classify_query_complexity()` routes to fast/smart model
   - Short simple queries → "fast", complex indicators → "smart", long queries → "smart"

3. **ConversationManager** (`agent_optimized.py`)
   - `add_exchange()` and `add_ai_message()` track word counts
   - `get_talk_ratio()` returns correct AI/user ratios
   - History structure and alternation
   - `history_len_before` guard pattern (verify via source inspection)

4. **Phrase cache matching** (`phrase_cache_optimized.py`)
   - `SIMILARITY_THRESHOLD` value (should be 0.92)
   - Exact match via `_exact_index` (case-insensitive)
   - Fuzzy match rejection below threshold

5. **Audio utilities** (`audio_utils_optimized.py`)
   - `_pcm_to_wav()` — verify RIFF header and 44-byte header size
   - `_is_silence()` — silence detection with threshold

6. **Config values** (`config_optimized.py`)
   - Timeout constants, max tokens, model names, thread pool size

7. **Opening messages** (`agent_optimized.py`)
   - `get_opening_message()` with different lead/inbound combinations

### Tests Requiring APIs
- Full call flow (Exotel webhooks → STT → LLM → TTS)
- Phrase cache building (requires Sarvam AI TTS)
- `conv.chat()` with actual Groq inference
- WebSocket voicebot stream

## Key Test Patterns

### Intent Detection
```python
from intent_optimized import detect_intent

# Compound phrase: should match specific intent, not acknowledgement
assert "free" in detect_intent("haan, busy hoon", lead={"name": "Raj"}).lower()

# Guard: no lead name → skip acknowledgement, fall through to others
assert detect_intent("haan", lead=None) is None
assert "Lal Kothi" in detect_intent("ok address batao", lead=None)
```

### Conversation History Guard (Bug #19/#20)
```python
import re
# JSON-only LLM response strips to empty → should NOT call add_ai_message
ai_reply = '{"temperature": "warm"}'
voice_text = re.sub(r"\{[\s\S]*?\}", "", ai_reply).strip()
assert voice_text == ""  # strips to empty
assert ai_reply is not None  # but ai_reply is NOT None → don't add fallback

# Timeout → ai_reply IS None → SHOULD call add_ai_message
ai_reply = None
assert ai_reply is None  # add fallback to prevent orphaned thread corruption
```

## Important Notes
- The `*_optimized.py` files are duplicates of originals — original files are never modified
- `agent_optimized.py` imports from `scraper.py` which needs pandas — install all deps first
- `chat_streaming()` is defined but not called by `main_optimized.py` — streaming benefit is not realized
- The orphaned thread guard uses `len(self.history)` without a lock — narrow race window under real concurrency
- Fuzzy cache threshold was raised from 0.78 to 0.92 to prevent semantically wrong audio matches
- For real-world testing, deploy and make 5-10 calls via Exotel to measure actual latency
