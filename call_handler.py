"""
call_handler.py
Manages active call sessions.
Exotel calls our webhook → we stream AI voice back.
Each call gets a ConversationManager instance.
"""
import time
from typing import Dict
from agent import ConversationManager, get_opening_message
from voice import synthesize_speech
import sheets_manager as db

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
        lead    = db.get_lead_by_id(new_id)
        lead_id = new_id

    is_inbound = (lead_id is None) or (lead and lead.get("source") == "inbound_call")

    session = {
        "call_sid":      call_sid,
        "lead_id":       lead_id or (lead.get("lead_id") if lead else ""),
        "caller":        caller_number,
        "lead":          lead,
        "conversation":  ConversationManager(lead),
        "start_time":    time.time(),
        "language":      "hinglish",
        "is_inbound":    is_inbound,
        "turn_count":    0,
        "silence_count": 0,
    }

    active_calls[call_sid] = session
    print(f"[CallHandler] Session started | SID: {call_sid} | Lead: {lead_id} | Inbound: {is_inbound}")
    return session


def get_opening_audio(call_sid: str) -> bytes:
    """Get the first thing Priya says when call connects."""
    session = active_calls.get(call_sid)
    if not session:
        return b""

    lead         = session.get("lead")
    is_inbound   = session.get("is_inbound", False)
    opening_text = get_opening_message(lead, is_inbound=is_inbound)

    # Log opening in conversation history
    session["conversation"].history.append({
        "role": "assistant", "content": opening_text
    })

    audio = synthesize_speech(opening_text, session.get("language", "hinglish"))
    return audio


def end_call_session(call_sid: str, duration_sec: int = 0) -> dict:
    """
    Called when Exotel sends call-ended webhook.
    Analyses conversation and updates lead.
    """
    session = active_calls.pop(call_sid, None)
    if not session:
        return {}

    from lead_manager import process_call_result

    conv            = session["conversation"]
    transcript      = conv.get_full_transcript()
    analysis        = conv.analyze_call()
    lead_id         = session.get("lead_id", "")
    actual_duration = int(time.time() - session["start_time"]) if not duration_sec else duration_sec

    print(f"[CallHandler] Call ended | SID: {call_sid} | Duration: {actual_duration}s "
          f"| Temp: {analysis.get('temperature','?')} | Outcome: {analysis.get('call_outcome','?')}")

    process_call_result(
        lead_id=lead_id,
        analysis=analysis,
        transcript=transcript,
        duration_sec=actual_duration,
        direction="inbound" if session.get("is_inbound") else "outbound"
    )

    return analysis