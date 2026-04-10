"""
call_handler.py
Manages active call sessions with strict turn-taking.

Features:
- Parallel STT + intent detection
- Streaming LLM → TTS pipeline
- Async-native audio processing
- Talk ratio tracking per session
- Strict turn-taking state flags (is_user_speaking, speech_final, is_ai_speaking)
- Fires async learning pipeline after every call ends
"""
import asyncio
import logging
import time
import re
from datetime import datetime
from typing import Dict

import config
from agent import ConversationManager, get_opening_message
from voice import transcribe_audio, synthesize_speech, synthesize_speech_async, transcribe_audio_async
import sheets_manager as db

log = logging.getLogger("shubham-ai.call-handler")

# In-memory store of active calls: call_sid → session data
active_calls: Dict[str, dict] = {}


def start_call_session(call_sid: str, caller_number: str, lead_id: str = None, direction: str = None) -> dict:
    """Initialize a new call session."""
    lead = None

    if lead_id:
        lead = db.get_lead_by_id(lead_id)
    elif caller_number:
        lead = db.get_lead_by_mobile(caller_number)

    if lead is None and caller_number:
        source = direction or "inbound_call"
        new_id = db.add_lead({
            "mobile":  caller_number,
            "source":  source,
            "notes":   "Auto-created from inbound call",
        })
        lead    = db.get_lead_by_id(new_id)
        lead_id = new_id

    is_inbound = direction != "outbound" if direction else (lead_id is None or (lead and lead.get("source") == "inbound_call"))
    session = {
        "call_sid":    call_sid,
        "lead_id":     lead_id or (lead.get("lead_id") if lead else ""),
        "caller":      caller_number,
        "lead":        lead,
        "conversation": ConversationManager(lead, is_inbound=is_inbound),
        "start_time":  time.time(),
        "language":    "hinglish",
        "is_inbound":  is_inbound,
        "turn_count":  0,
        "silence_count": 0,
        # Strict turn-taking state flags
        "is_user_speaking": False,   # True while user audio is being received
        "speech_final": False,       # True when end-of-speech silence detected
        "is_ai_speaking": False,     # True while AI response audio is playing
        "last_user_speech_time": 0.0,  # Timestamp of last user speech for silence detection
    }

    active_calls[call_sid] = session
    log.info(
        "Session started | SID: %s | Lead: %s | Inbound: %s",
        call_sid, lead_id, is_inbound,
    )
    return session


def get_opening_audio(call_sid: str) -> bytes:
    """
    Generate and return the opening greeting audio for this call.
    """
    session = active_calls.get(call_sid)
    if not session:
        return b""

    lead       = session.get("lead")
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


async def process_customer_speech_async(call_sid: str, audio_bytes: bytes) -> bytes:
    """
    Async speech processing with strict turn-taking.
    Uses async STT and TTS — no thread pool overhead.
    """
    session = active_calls.get(call_sid)
    if not session:
        return b""

    # STRICT: Only process if user has finished speaking
    if session.get("is_user_speaking", False):
        return b""

    # 1. Speech to Text (async)
    stt_result    = await transcribe_audio_async(audio_bytes, "hi-IN")
    customer_text = stt_result.get("text", "").strip()
    detected_lang = stt_result.get("language", "hinglish")

    if not customer_text:
        silence_reply = "Ji? Phir se bol sakte hain?"
        return await synthesize_speech_async(silence_reply, session["language"])

    # STRICT: Check again after STT — user may have started speaking again
    if session.get("is_user_speaking", False):
        log.info("[%s] User resumed speaking during STT — aborting", call_sid)
        return b""

    session["language"]  = detected_lang
    session["turn_count"] += 1

    log.info("[%s] Customer: %s", call_sid, customer_text)

    # 2. Try intent detection first (instant, no API call)
    from intent import detect_intent
    intent_response = detect_intent(customer_text, lead=session.get("lead"))

    if intent_response:
        voice_text = intent_response
        conv = session["conversation"]
        conv.add_exchange(customer_text, voice_text)
        log.info("[%s] Intent matched — skipping Groq", call_sid)
    else:
        # 3. Get AI response (hybrid model routing + response validation)
        conv = session["conversation"]
        ai_reply = conv.chat(customer_text)
        voice_text = re.sub(r'\{[\s\S]*?\}', '', ai_reply).strip()

    if not voice_text:
        voice_text = "Ji, samajh rahi hoon. Aap bataaiye?"

    log.info("[%s] Priya: %s", call_sid, voice_text[:120])

    # STRICT: Check before TTS — abort if user interrupted
    if session.get("is_user_speaking", False):
        log.info("[%s] User interrupted before TTS — aborting", call_sid)
        return b""

    # Mark AI as speaking
    session["is_ai_speaking"] = True

    # 4. Text to Speech (async)
    audio_out = await synthesize_speech_async(voice_text, detected_lang)

    # Mark AI as done speaking
    session["is_ai_speaking"] = False
    return audio_out


def process_customer_speech(call_sid: str, audio_bytes: bytes) -> bytes:
    """
    Synchronous fallback — same logic as original but with optimized imports.
    """
    session = active_calls.get(call_sid)
    if not session:
        return b""

    stt_result    = transcribe_audio(audio_bytes, "hi-IN")
    customer_text = stt_result.get("text", "").strip()
    detected_lang = stt_result.get("language", "hinglish")

    if not customer_text:
        silence_reply = "Ji? Phir se bol sakte hain?"
        return synthesize_speech(silence_reply, session["language"])

    session["language"]  = detected_lang
    session["turn_count"] += 1

    from intent import detect_intent
    intent_response = detect_intent(customer_text, lead=session.get("lead"))

    conv = session["conversation"]
    if intent_response:
        voice_text = intent_response
        conv.add_exchange(customer_text, voice_text)
    else:
        ai_reply = conv.chat(customer_text)
        voice_text = re.sub(r'\{[\s\S]*?\}', '', ai_reply).strip()

    if not voice_text:
        voice_text = "Ji, samajh rahi hoon. Aap bataaiye?"

    audio_out = synthesize_speech(voice_text, detected_lang)
    return audio_out


def end_call_session(call_sid: str, duration_sec: int = 0) -> dict:
    """
    Called when Exotel sends the call-ended webhook.
    Analyses conversation, updates lead, and fires learning pipeline.
    """
    session = active_calls.pop(call_sid, None)
    if not session:
        return {}

    from lead_manager import process_call_result

    conv       = session["conversation"]
    transcript = conv.get_full_transcript()
    analysis   = conv.analyze_call()
    lead_id    = session.get("lead_id", "")
    actual_dur = int(time.time() - session["start_time"]) if not duration_sec else duration_sec

    # Log talk ratio for monitoring
    talk_ratio = conv.get_talk_ratio()
    log.info(
        "Call ended | SID: %s | Duration: %ds | Temp: %s | "
        "Talk ratio: AI=%.0f%% User=%.0f%%",
        call_sid, actual_dur,
        analysis.get("temperature", "?"),
        talk_ratio["ai_ratio"] * 100,
        talk_ratio["user_ratio"] * 100,
    )

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

    if lead_id:
        lead = db.get_lead_by_id(lead_id)
        old_transcript = lead.get("last_transcript", "") if lead else ""
        call_num = int(lead.get("call_count", 0)) if lead else 1
        timestamp = datetime.now().strftime("%d %b %H:%M")
        new_entry = f"[Call {call_num} - {timestamp}]\n{transcript}"
        combined = f"{old_transcript}\n\n{new_entry}".strip() if old_transcript else new_entry
        db.update_lead(lead_id, {"last_transcript": combined[-3000:]})

    # Fire background learning pipeline
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
    Fire the learning pipeline as a background task.

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
