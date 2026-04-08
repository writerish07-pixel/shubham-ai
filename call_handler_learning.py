"""
call_handler_learning.py — Call session manager with self-learning integration.

🔥 SELF-LEARNING ADDED: Extends call_handler_optimized.py with:
- Uses ConversationManagerLearning (RAG-enabled) instead of ConversationManager
- Triggers async learning pipeline after every call ends
- Tracks competitor mentions during live calls
- Logs structured call data for sales intelligence

Architecture:
- During call: Uses agent_learning.py for RAG-enhanced responses
- After call ends: Fires background task for learning pipeline (zero latency impact)
- All original call_handler_optimized.py functionality preserved
"""
import asyncio
import logging
import re
import time
from datetime import datetime
from typing import Dict

from agent_learning import ConversationManagerLearning, get_opening_message
from voice_optimized import (
    transcribe_audio, synthesize_speech,
    synthesize_speech_async, transcribe_audio_async,
)
import config_learning as config
import sheets_manager as db

log = logging.getLogger("shubham-ai.call-handler-learning")

# In-memory store of active calls: call_sid → session data
active_calls: Dict[str, dict] = {}


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Session management with learning-enabled conversation
# ══════════════════════════════════════════════════════════════════════════════

def start_call_session(call_sid: str, caller_number: str,
                       lead_id: str = None, direction: str = None) -> dict:
    """
    Initialize a new call session with self-learning conversation manager.

    🔥 SELF-LEARNING ADDED: Uses ConversationManagerLearning instead of
    ConversationManager — enables RAG context injection and competitor detection.
    """
    lead = None

    if lead_id:
        lead = db.get_lead_by_id(lead_id)
    elif caller_number:
        lead = db.get_lead_by_mobile(caller_number)

    if lead is None and caller_number:
        source = direction or "inbound_call"
        new_id = db.add_lead({
            "mobile": caller_number,
            "source": source,
            "notes": "Auto-created from inbound call",
        })
        lead = db.get_lead_by_id(new_id)
        lead_id = new_id

    is_inbound = (
        direction != "outbound"
        if direction
        else (lead_id is None or (lead and lead.get("source") == "inbound_call"))
    )

    # 🔥 SELF-LEARNING ADDED: Use learning-enabled conversation manager
    # 🔥 FIX: Use the already-computed is_inbound variable instead of
    # re-deriving it — the simple (direction != "outbound") misses the
    # fallback logic when direction is None.
    session = {
        "call_sid": call_sid,
        "lead_id": lead_id or (lead.get("lead_id") if lead else ""),
        "caller": caller_number,
        "lead": lead,
        "conversation": ConversationManagerLearning(
            lead, is_inbound=is_inbound
        ),
        "start_time": time.time(),
        "language": "hinglish",
        "is_inbound": is_inbound,
        "turn_count": 0,
        "silence_count": 0,
        "is_speaking": False,
    }

    active_calls[call_sid] = session
    log.info(
        "Session started | SID: %s | Lead: %s | Inbound: %s",
        call_sid, lead_id, is_inbound,
    )
    return session


def get_opening_audio(call_sid: str) -> bytes:
    """Generate and return the opening greeting audio for this call."""
    session = active_calls.get(call_sid)
    if not session:
        return b""

    lead = session.get("lead")
    is_inbound = session.get("is_inbound", False)

    opening_text = get_opening_message(lead, is_inbound=is_inbound)
    log.info("Opening text: %s", opening_text[:120])

    session["conversation"].add_ai_message(opening_text)

    audio = synthesize_speech(opening_text, "hinglish")

    if not audio:
        log.warning("synthesize_speech returned empty bytes")
    else:
        log.info("Opening audio: %d bytes", len(audio))

    return audio


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Speech processing with learning-enabled agent
# ══════════════════════════════════════════════════════════════════════════════

async def process_customer_speech_async(call_sid: str, audio_bytes: bytes) -> bytes:
    """
    Async speech processing with RAG-enhanced responses.

    🔥 SELF-LEARNING ADDED: The ConversationManagerLearning.chat() method
    automatically retrieves relevant past learnings via RAG before generating
    a response. This adds ~5-20ms latency (FAISS in-memory search).
    """
    session = active_calls.get(call_sid)
    if not session:
        return b""

    # 1. Speech to Text (async)
    stt_result = await transcribe_audio_async(audio_bytes, "hi-IN")
    customer_text = stt_result.get("text", "").strip()
    detected_lang = stt_result.get("language", "hinglish")

    if not customer_text:
        silence_reply = "Ji? Phir se bol sakte hain?"
        return await synthesize_speech_async(silence_reply, session["language"])

    session["language"] = detected_lang
    session["turn_count"] += 1

    log.info("[%s] Customer: %s", call_sid, customer_text)

    # 2. Try intent detection first (instant, no API call)
    from intent_optimized import detect_intent
    intent_response = detect_intent(customer_text, lead=session.get("lead"))

    if intent_response:
        voice_text = intent_response
        conv = session["conversation"]
        conv.add_exchange(customer_text, voice_text)
        log.info("[%s] Intent matched — skipping Groq", call_sid)
    else:
        # 3. Get AI response (with RAG context injection)
        conv = session["conversation"]
        ai_reply = conv.chat(customer_text)
        voice_text = re.sub(r'\{[\s\S]*?\}', '', ai_reply).strip()

    if not voice_text:
        voice_text = "Ji, samajh rahi hoon. Thoda detail dein?"

    log.info("[%s] Priya: %s", call_sid, voice_text[:120])

    # 4. Text to Speech (async)
    audio_out = await synthesize_speech_async(voice_text, detected_lang)
    return audio_out


def process_customer_speech(call_sid: str, audio_bytes: bytes) -> bytes:
    """Synchronous fallback with learning-enabled agent."""
    session = active_calls.get(call_sid)
    if not session:
        return b""

    stt_result = transcribe_audio(audio_bytes, "hi-IN")
    customer_text = stt_result.get("text", "").strip()
    detected_lang = stt_result.get("language", "hinglish")

    if not customer_text:
        silence_reply = "Ji? Phir se bol sakte hain?"
        return synthesize_speech(silence_reply, session["language"])

    session["language"] = detected_lang
    session["turn_count"] += 1

    from intent_optimized import detect_intent
    intent_response = detect_intent(customer_text, lead=session.get("lead"))

    conv = session["conversation"]
    if intent_response:
        voice_text = intent_response
        conv.add_exchange(customer_text, voice_text)
    else:
        ai_reply = conv.chat(customer_text)
        voice_text = re.sub(r'\{[\s\S]*?\}', '', ai_reply).strip()

    if not voice_text:
        voice_text = "Ji, samajh rahi hoon. Thoda detail dein?"

    audio_out = synthesize_speech(voice_text, detected_lang)
    return audio_out


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: End call with async learning pipeline
# ══════════════════════════════════════════════════════════════════════════════

def end_call_session(call_sid: str, duration_sec: int = 0) -> dict:
    """
    Called when Exotel sends the call-ended webhook.

    🔥 SELF-LEARNING ADDED: After analyzing the call and updating the lead,
    fires a BACKGROUND TASK to run the learning pipeline. This extracts
    intents, objections, buying signals, and loss reasons from the transcript
    and stores them in the vector DB for future RAG retrieval.

    The background task runs async — zero impact on webhook response time.
    """
    session = active_calls.pop(call_sid, None)
    if not session:
        return {}

    from lead_manager import process_call_result

    conv = session["conversation"]
    transcript = conv.get_full_transcript()
    analysis = conv.analyze_call()
    lead_id = session.get("lead_id", "")
    actual_dur = (
        int(time.time() - session["start_time"])
        if not duration_sec
        else duration_sec
    )

    # Log talk ratio
    talk_ratio = conv.get_talk_ratio()
    log.info(
        "Call ended | SID: %s | Duration: %ds | Temp: %s | "
        "Talk ratio: AI=%.0f%% User=%.0f%%",
        call_sid, actual_dur,
        analysis.get("temperature", "?"),
        talk_ratio["ai_ratio"] * 100,
        talk_ratio["user_ratio"] * 100,
    )

    # Process call result (update lead, schedule follow-up, etc.)
    try:
        process_call_result(
            lead_id=lead_id,
            analysis=analysis,
            transcript=transcript,
            duration_sec=actual_dur,
            direction="inbound" if session.get("is_inbound") else "outbound",
        )
    except Exception as exc:
        log.error("process_call_result failed for SID %s: %s", call_sid, exc)

    # Update lead transcript
    if lead_id:
        lead = db.get_lead_by_id(lead_id)
        old_transcript = lead.get("last_transcript", "") if lead else ""
        call_num = int(lead.get("call_count", 0)) if lead else 1
        timestamp = datetime.now().strftime("%d %b %H:%M")
        new_entry = f"[Call {call_num} - {timestamp}]\n{transcript}"
        combined = (
            f"{old_transcript}\n\n{new_entry}".strip()
            if old_transcript
            else new_entry
        )
        db.update_lead(lead_id, {"last_transcript": combined[-3000:]})

    # 🔥 SELF-LEARNING ADDED: Fire background learning pipeline
    if config.LEARNING_ENABLED:
        _fire_learning_pipeline(
            transcript=transcript,
            call_sid=call_sid,
            caller=session.get("caller", ""),
            duration=actual_dur,
        )

    return analysis


def _fire_learning_pipeline(transcript: str, call_sid: str,
                             caller: str, duration: int):
    """
    🔥 SELF-LEARNING ADDED: Fire the learning pipeline as a background task.

    Uses asyncio to run the pipeline without blocking the webhook response.
    If no event loop is running, creates a new one in a thread.
    """
    from learning_pipeline import process_call_learning

    async def _run():
        try:
            await process_call_learning(
                transcript=transcript,
                call_sid=call_sid,
                caller=caller,
                call_duration=duration,
            )
        except Exception as e:
            log.error("Background learning pipeline failed: %s", e)

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_run())
        log.info("Learning pipeline fired as background task for call %s", call_sid)
    except RuntimeError:
        # No running event loop — run in a new thread
        import threading

        def _thread_run():
            asyncio.run(_run())

        t = threading.Thread(target=_thread_run, daemon=True)
        t.start()
        log.info("Learning pipeline fired in background thread for call %s", call_sid)
