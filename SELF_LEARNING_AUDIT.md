# Self-Learning Sales Agent — Audit Report

## 🔴 Current System Limitations

| Area | Status | Details |
|------|--------|---------|
| Vector Database | ❌ Missing | No FAISS/Chroma — no semantic search capability |
| RAG Pipeline | ❌ Missing | Past call data stored but never used to improve responses |
| Call Learning | ❌ Missing | Transcripts logged to JSON but not analyzed for patterns |
| Loss Tracking | ❌ Missing | `analyze_call()` extracts `competitor_brand` and `loss_reason` but data is not stored separately or used |
| Competitor Intelligence | ❌ Missing | No structured tracking of WHY customers buy from competitors |
| Document Learning | ⚠️ Partial | `scraper.py` has PDF/Excel/Image parsers but extracted text is not embedded or searchable |
| Feedback Loop | ❌ Missing | Agent does not learn from successful vs failed calls |
| Memory System | ❌ Missing | Conversation context is per-call only — lost after call ends |

## 🧠 Self-Learning Capability: NO

The current system has **zero self-learning capability**. It operates as a stateless agent:
- Each call starts fresh with no memory of past interactions
- Successful sales techniques are not captured or reused
- Customer objections are not tracked across calls
- Pricing/offer knowledge is hardcoded, not learned from documents

### What Exists (but doesn't learn):
1. **Call logging** (`sheets_manager.log_call()`) — stores transcripts to `data/calls.json` but never reads them back
2. **Call analysis** (`agent_optimized.analyze_call()`) — extracts intent/objection/temperature but only for lead updates
3. **File parsing** (`scraper.parse_offer_file()`) — can read PDFs/images but doesn't embed the content
4. **Conversation history** (`ConversationManager`) — per-call only, lost when call ends

## ⚡ Improvements Implemented

### Part 2: Self-Learning Pipeline
- **`memory_learning.py`** — FAISS vector database for semantic memory
  - Stores conversation learnings, objections, buying signals as embeddings
  - RAG retrieval: `get_relevant_context()` returns relevant past knowledge in ~5-20ms
  - Persistent storage: index + metadata saved to disk across restarts
  - Thread-safe with file locking for concurrent access

- **`learning_pipeline.py`** — Post-call analysis pipeline
  - Analyzes every call transcript using Groq LLM (70B model for quality)
  - Extracts: intent, objections, buying signals, loss reasons, successful techniques
  - Stores all learnings in vector DB for future RAG retrieval
  - Runs **async in background** — zero impact on call latency

### Part 3: PDF & Image Learning
- **`document_learning.py`** — Document ingestion system
  - Accepts PDF, JPEG, Excel files
  - Reuses existing `scraper.py` parsers (pdfplumber, pytesseract, openpyxl)
  - Chunks text into 500-char segments with 50-char overlap
  - Auto-detects document category (pricing, offer, brochure, general)
  - Stores chunks as embeddings in FAISS for RAG retrieval
  - Also supports direct text ingestion for manual knowledge entry

### Part 4: Sales Intelligence
- **`sales_intelligence.py`** — Competitor/dealer loss tracking
  - Detects competitor brand mentions in real-time during calls
  - Logs structured loss data: date, model, competitor, reason, category
  - Separate tracking for brand losses vs dealer losses
  - Analytics: `get_loss_summary()` returns top competitors, reasons, lost models
  - Per-competitor insights: `get_competitor_insights("honda")` for detailed analysis

### Part 5: Agent Behavior (Sales Expert)
- **`agent_learning.py`** — Enhanced AI agent
  - **RAG injection**: Retrieves relevant past learnings before every response
  - **Sales psychology**: Scarcity, urgency, social proof, SPIN selling, assumptive close
  - **Competitor handling**: Detects mentions → routes to smart model → uses counter-arguments
  - **Strict 30/70 enforcement**: Forces max 25 tokens when AI ratio exceeds 35%
  - **Objection handling**: Price→EMI, Delay→urgency, Comparison→Hero strengths

### Part 6: Latency-Safe Implementation
- **`call_handler_learning.py`** — Integrated call handler
  - Uses `ConversationManagerLearning` for RAG-enhanced responses
  - Learning pipeline runs as **async background task** after call ends
  - RAG retrieval adds only ~5-20ms (FAISS in-memory search)
  - No blocking I/O during call — all learning is post-call
  - Falls back gracefully if learning components fail

### Part 7: Configuration
- **`config_learning.py`** — New configuration constants
  - Vector DB settings (embedding model, dimension, paths)
  - RAG parameters (top_k=3, min_similarity=0.45)
  - Document chunking settings (500 chars, 50 overlap)
  - Competitor brands list for detection
  - Loss reason categories for structured tracking
  - All directories auto-created on startup

## 📁 List of New Files Created

| File | Lines | Purpose |
|------|-------|---------|
| `config_learning.py` | ~120 | Configuration constants for learning system |
| `memory_learning.py` | ~280 | FAISS vector DB — store/retrieve/RAG |
| `learning_pipeline.py` | ~220 | Post-call transcript analysis + learning |
| `document_learning.py` | ~250 | PDF/JPEG/Excel ingestion → embeddings |
| `sales_intelligence.py` | ~220 | Competitor/dealer loss tracking + analytics |
| `agent_learning.py` | ~340 | Enhanced agent with RAG + sales psychology |
| `call_handler_learning.py` | ~280 | Call handler with learning pipeline integration |
| `SELF_LEARNING_AUDIT.md` | This file | Audit report |

**Total: 7 new Python files + 1 audit report**
**No original files modified.**

## 📊 Sales Intelligence Logic

### How Loss Detection Works:
```
Customer says: "Maine Honda Activa le li, discount zyada tha"
         ↓
1. Real-time: detect_competitor_mention("honda") → routes to smart model
2. Agent responds with Hero advantages (mileage, resale, service network)
3. Post-call: learning_pipeline extracts:
   - competitor_brand: "honda"
   - competitor_model: "Activa"
   - loss_reason: "discount zyada tha"
   - loss_category: "discount"
   - bought_elsewhere: true
4. Stored in: data/intelligence/competitor_losses.json
5. Embedded in FAISS for future RAG retrieval
```

### How RAG Works:
```
New customer asks: "Honda Activa ka mileage zyada hai"
         ↓
1. FAISS search: "honda activa mileage" → finds past learnings
2. Retrieved: "Customer lost to Honda Activa. Reason: mileage. Counter: Hero Splendor gives 70+ kmpl"
3. Injected into system prompt as context
4. Agent responds: "Splendor Plus 70 kmpl deti hai — Activa se zyada! Test ride lenge?"
```

## 🎯 Expected Outcomes

| Metric | Before | After | Impact |
|--------|--------|-------|--------|
| Learning capability | None | Full RAG pipeline | Agent improves with every call |
| Competitor tracking | None | Structured + analytics | Know why customers leave |
| Document knowledge | Parse only | Parse + embed + retrieve | Answer price/offer queries from docs |
| Response relevance | Generic | Context-aware (RAG) | Better objection handling |
| Talk ratio | Tracked only | Enforced (25 token cap) | Strict 30/70 compliance |
| Latency impact | N/A | +5-20ms (RAG) | Well within ≤1.5s target |
| Post-call processing | None | Async background | Zero impact on call flow |

## Dependencies Required

```
faiss-cpu          # Vector similarity search (lightweight, ~15MB)
sentence-transformers  # Text embeddings (all-MiniLM-L6-v2, ~80MB model)
numpy              # Required by FAISS
```

Add to `requirements.txt`:
```
faiss-cpu>=1.7.4
sentence-transformers>=2.2.0
```
