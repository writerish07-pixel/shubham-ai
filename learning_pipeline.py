"""
learning_pipeline.py — Post-call learning pipeline for self-learning agent.

🔥 SELF-LEARNING ADDED: Extracts structured knowledge from every call:
- Customer intent (what they want)
- Objections raised (price, comparison, delay, etc.)
- Buying signals (test ride, EMI inquiry, visit intent)
- Loss reasons (competitor brand/dealer, why they left)
- Successful handling patterns (what worked in past calls)

Runs ASYNCHRONOUSLY after each call ends — zero impact on call latency.
Results are stored in vector DB (memory_learning.py) for RAG retrieval.
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

import config_learning as config

log = logging.getLogger("shubham-ai.learning")


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Transcript analyzer using Groq LLM
# ══════════════════════════════════════════════════════════════════════════════

_ANALYSIS_PROMPT = """You are a sales intelligence analyzer for a Hero two-wheeler dealership (Shubham Motors, Jaipur).

Analyze this call transcript and extract the following in JSON format:

{
  "customer_intent": "what the customer wants (e.g., buy bike, compare models, check price, test ride, service)",
  "interested_model": "specific Hero model mentioned (or 'unknown')",
  "objections": ["list of objections raised (e.g., 'price too high', 'better mileage in TVS', 'need to think')"],
  "buying_signals": ["list of buying signals (e.g., 'asked about EMI', 'wants test ride', 'asked about delivery')"],
  "competitor_mentioned": "competitor brand name if mentioned (or 'none')",
  "competitor_model": "specific competitor model if mentioned (or 'none')",
  "bought_elsewhere": false,
  "loss_reason": "why customer bought from competitor or another dealer (or 'none')",
  "loss_category": "price|mileage|brand_trust|availability|discount|service|features|resale_value|behavior|finance|other|none",
  "customer_temperature": "hot|warm|cold",
  "key_learning": "one sentence about what we learned from this call that can help future calls",
  "successful_technique": "what sales technique worked well in this call (or 'none')",
  "failed_technique": "what approach did not work (or 'none')"
}

IMPORTANT:
- Return ONLY valid JSON, no extra text
- Be specific and concise
- If customer mentioned buying from another dealer (not brand), note that in loss_reason
- Detect Hindi/Hinglish intent accurately

TRANSCRIPT:
"""

# 🔥 FIX: Use string concatenation instead of str.format() to avoid
# KeyError/ValueError when transcripts contain curly braces (which LLM
# JSON responses frequently do).


async def analyze_call_transcript(transcript: str, call_sid: str = "",
                                   caller: str = "") -> Optional[dict]:
    """
    🔥 SELF-LEARNING ADDED: Analyze a call transcript using Groq LLM.

    Runs asynchronously — meant to be called in a background task after call ends.
    Uses the smart model (70B) for better analysis quality.

    Args:
        transcript: Full call transcript text
        call_sid: Call session ID for logging
        caller: Caller phone number

    Returns:
        Structured analysis dict, or None on failure.
    """
    if not transcript or len(transcript.strip()) < 20:
        log.info("Transcript too short to analyze (call %s)", call_sid)
        return None

    if not config.GROQ_API_KEY:
        log.warning("GROQ_API_KEY not set — cannot analyze transcript")
        return None

    # Truncate very long transcripts
    if len(transcript) > config.MAX_TRANSCRIPT_LENGTH:
        transcript = transcript[:config.MAX_TRANSCRIPT_LENGTH] + "\n...[truncated]"

    prompt = _ANALYSIS_PROMPT + transcript

    try:
        from groq import Groq
        client = Groq(api_key=config.GROQ_API_KEY)

        # 🔥 SELF-LEARNING ADDED: Use smart model for analysis (runs in background, latency ok)
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(None, lambda: client.chat.completions.create(
            model=config.GROQ_SMART_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500,
            response_format={"type": "json_object"},
        ))

        content = response.choices[0].message.content.strip()
        analysis = json.loads(content)

        log.info("Call %s analyzed: intent=%s, temp=%s, competitor=%s",
                 call_sid,
                 analysis.get("customer_intent", "?"),
                 analysis.get("customer_temperature", "?"),
                 analysis.get("competitor_mentioned", "none"))

        return analysis

    except json.JSONDecodeError as e:
        log.error("Failed to parse analysis JSON for call %s: %s", call_sid, e)
        return None
    except Exception as e:
        log.error("Transcript analysis failed for call %s: %s", call_sid, e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Store learnings in vector DB + JSON
# ══════════════════════════════════════════════════════════════════════════════

# 🔥 SELF-LEARNING ADDED: Module-level lock for thread-safe file writes
_file_lock = __import__('threading').Lock()


def _append_json(filepath: Path, entry: dict):
    """Thread-safe append to a JSON array file."""
    with _file_lock:
        data = []
        if filepath.exists():
            try:
                data = json.loads(filepath.read_text(encoding="utf-8"))
            except Exception:
                data = []
        data.append(entry)
        filepath.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


async def process_call_learning(transcript: str, call_sid: str = "",
                                 caller: str = "", call_duration: int = 0):
    """
    🔥 SELF-LEARNING ADDED: Complete post-call learning pipeline.

    Called as a background task after every call ends. Steps:
    1. Analyze transcript with Groq LLM
    2. Store key learning in vector DB for RAG
    3. Store objections in vector DB
    4. Store competitor/loss data for sales intelligence
    5. Log everything to JSON files for analytics

    This function is async and non-blocking — does NOT affect call latency.
    """
    if not config.LEARNING_ENABLED:
        return

    log.info("Starting learning pipeline for call %s", call_sid)
    start_time = time.time()

    # Step 1: Analyze transcript
    analysis = await analyze_call_transcript(transcript, call_sid, caller)
    if not analysis:
        log.info("No analysis result for call %s — skipping learning", call_sid)
        return

    # Step 2: Store in vector DB for RAG
    import memory_learning as memory

    learnings_to_store = []

    # Store key learning
    key_learning = analysis.get("key_learning", "")
    if key_learning and key_learning != "none":
        learnings_to_store.append({
            "text": key_learning,
            "metadata": {
                "type": "conversation",
                "source": f"call_{call_sid}",
                "caller": caller,
                "intent": analysis.get("customer_intent", ""),
                "model": analysis.get("interested_model", ""),
                "temperature": analysis.get("customer_temperature", ""),
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        })

    # Store each objection as a separate learning
    objections = analysis.get("objections", [])
    for obj in objections:
        if obj and obj.strip():
            learnings_to_store.append({
                "text": f"Customer objection: {obj}",
                "metadata": {
                    "type": "objection",
                    "source": f"call_{call_sid}",
                    "model": analysis.get("interested_model", ""),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            })

    # Store buying signals
    buying_signals = analysis.get("buying_signals", [])
    for signal in buying_signals:
        if signal and signal.strip():
            learnings_to_store.append({
                "text": f"Buying signal: {signal}",
                "metadata": {
                    "type": "buying_signal",
                    "source": f"call_{call_sid}",
                    "model": analysis.get("interested_model", ""),
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
            })

    # Store successful technique
    technique = analysis.get("successful_technique", "")
    if technique and technique != "none":
        learnings_to_store.append({
            "text": f"Effective sales technique: {technique}",
            "metadata": {
                "type": "technique",
                "source": f"call_{call_sid}",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
        })

    # Batch store all learnings
    if learnings_to_store:
        stored = memory.store_learnings_batch(learnings_to_store)
        log.info("Stored %d learnings from call %s", stored, call_sid)

    # Step 3: Log to JSON files
    learning_entry = {
        "call_sid": call_sid,
        "caller": caller,
        "duration": call_duration,
        "analysis": analysis,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    _append_json(config.LEARNINGS_FILE, learning_entry)

    # Step 4: Handle competitor/loss intelligence
    if analysis.get("bought_elsewhere") or analysis.get("competitor_mentioned", "none") != "none":
        from sales_intelligence import log_competitor_loss
        await log_competitor_loss(
            call_sid=call_sid,
            caller=caller,
            competitor_brand=analysis.get("competitor_mentioned", "none"),
            competitor_model=analysis.get("competitor_model", "none"),
            loss_reason=analysis.get("loss_reason", ""),
            loss_category=analysis.get("loss_category", "other"),
            interested_model=analysis.get("interested_model", ""),
            bought_elsewhere=analysis.get("bought_elsewhere", False),
        )

    elapsed = time.time() - start_time
    log.info("Learning pipeline completed for call %s in %.1fs", call_sid, elapsed)


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Build transcript from conversation history
# ══════════════════════════════════════════════════════════════════════════════

def build_transcript(conversation_history: list[dict]) -> str:
    """
    Convert conversation history (list of {role, content} dicts) to readable transcript.

    Args:
        conversation_history: List of {"role": "user"/"assistant", "content": "..."}

    Returns:
        Formatted transcript string like:
        "Customer: Namaste, price kitni hai?
         Agent: Namaste! Splendor Plus ki price ₹74K se shuru hai..."
    """
    lines = []
    for msg in conversation_history:
        role = msg.get("role", "")
        content = msg.get("content", "").strip()
        if not content:
            continue
        if role == "user":
            lines.append(f"Customer: {content}")
        elif role == "assistant":
            lines.append(f"Agent: {content}")
    return "\n".join(lines)
