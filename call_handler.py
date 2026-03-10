"""
call_handler.py
Manages active call sessions.
Exotel calls our webhook → we stream AI voice back.
Each call gets a ConversationManager instance.
"""
import logging
import re
import time
from typing import Dict

from agent import ConversationManager, get_opening_message
from voice import transcribe_audio, synthesize_speech
import sheets_manager as db

log = logging.getLogger("shubham-ai.calls")

# In-memory store of active calls: call_sid → session data
active_calls: Dict[str, dict] = {}


def start_call_session(call_sid: str, caller_number: str, lead_id: str = None) -> dict:
    """Initialize a new call session."""
    lead = None
    if lead_id:
        lead = db.get_lead_by_id(lead_id)
    elif caller_number:
        lead = db.get_lead_by_mobile(caller_number)
    
    if lead is None and caller_number:
        # Auto-create lead for inbound unknown callers
        new_id = db.add_lead({
            "mobile": caller_number,
            "source": "inbound_call",
            "notes": "Auto-created from inbound call"
        })
        lead = db.get_lead_by_id(new_id)
        lead_id = new_id
    
    is_inbound = lead_id is None or (lead and lead.get("source") == "inbound_call")
    
    session = {
        "call_sid": call_sid,
        "lead_id": lead_id or (lead.get("lead_id") if lead else ""),
        "caller": caller_number,
        "lead": lead,
        "conversation": ConversationManager(lead),
        "start_time": time.time(),
        "language": "hinglish",
        "is_inbound": is_inbound,
        "turn_count": 0,
    }
    
    active_calls[call_sid] = session
    log.info("Session started | SID: %s | Lead: %s | Inbound: %s", call_sid, lead_id, is_inbound)
    return session


def get_opening_audio(call_sid: str) -> bytes:
    """Get the first thing Priya says when call connects."""
    session = active_calls.get(call_sid)
    if not session:
        return b""
    
    lead = session.get("lead")
    is_inbound = session.get("is_inbound", False)
    opening_text = get_opening_message(lead, is_inbound=is_inbound)
    
    # Log opening in conversation
    session["conversation"].history.append({
        "role": "assistant", "content": opening_text
    })
    
    audio = synthesize_speech(opening_text, session.get("language", "hinglish"))
    return audio if audio else b""


def process_customer_speech(call_sid: str, audio_bytes: bytes) -> bytes:
    """
    Core loop: audio in → STT → Groq → TTS → audio out
    Returns audio bytes to play back to customer.
    """
    session = active_calls.get(call_sid)
    if not session:
        return b""
    
    # 1. Speech to Text
    stt_result = transcribe_audio(audio_bytes, "hi-IN")
    customer_text = stt_result.get("text", "").strip()
    detected_lang = stt_result.get("language", "hinglish")
    
    if not customer_text:
        # Silence / unclear audio
        silence_reply = "Ji? Kuch suna nahi -- kya aap phir se bol sakte hain?"
        return synthesize_speech(silence_reply, session["language"]) or b""

    # Update detected language
    session["language"] = detected_lang
    session["turn_count"] += 1

    log.info("[%s] Customer: %s", call_sid, customer_text)

    # 2. Get AI response
    conv = session["conversation"]
    ai_reply = conv.chat(customer_text)

    # Strip any JSON analysis block from voice response (non-greedy)
    voice_text = re.sub(r'\{[\s\S]*?\}', '', ai_reply).strip()

    log.info("[%s] Priya: %s", call_sid, voice_text[:100])
    
    # 3. Text to Speech
    audio_out = synthesize_speech(voice_text, detected_lang)
    return audio_out


def end_call_session(call_sid: str, duration_sec: int = 0) -> dict:
    """
    Called when Exotel sends call-ended webhook.
    Analyzes conversation and updates lead.
    """
    session = active_calls.pop(call_sid, None)
    if not session:
        return {}
    
    from lead_manager import process_call_result

    conv = session["conversation"]
    transcript = conv.get_full_transcript()

    try:
        analysis = conv.analyze_call()
    except Exception as exc:
        log.error("Call analysis failed for SID %s: %s", call_sid, exc)
        analysis = {"temperature": "warm", "next_action": "followup_call", "notes": "Analysis error"}

    lead_id = session.get("lead_id", "")
    actual_duration = duration_sec if duration_sec else int(time.time() - session["start_time"])

    log.info(
        "Call ended | SID: %s | Duration: %ss | Analysis: %s / %s",
        call_sid, actual_duration,
        analysis.get('temperature', '?'), analysis.get('call_outcome', '?'),
    )

    try:
        process_call_result(
            lead_id=lead_id,
            analysis=analysis,
            transcript=transcript,
            duration_sec=actual_duration,
            direction="inbound" if session.get("is_inbound") else "outbound",
        )
    except Exception as exc:
        log.error("process_call_result failed for SID %s: %s", call_sid, exc)

    return analysis
