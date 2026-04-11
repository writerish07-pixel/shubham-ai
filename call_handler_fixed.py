# call_handler.py (FIXED VERSION - PRODUCTION READY)

import asyncio
import logging
import time
import re
from datetime import datetime
from typing import Dict

import config
from agent import ConversationManager, get_opening_message
from voice import (
    transcribe_audio,
    synthesize_speech,
    synthesize_speech_async,
    transcribe_audio_async
)
import sheets_manager as db

log = logging.getLogger("shubham-ai.call-handler")

active_calls: Dict[str, dict] = {}

def safe_tts(text: str, lang="hinglish") -> bytes:
    try:
        audio = synthesize_speech(text, lang)
        if audio:
            return audio
    except Exception as e:
        log.error("TTS failed: %s", e)

    return synthesize_speech("Ji boliye", "hinglish")

def start_call_session(call_sid: str, caller_number: str, lead_id: str = None, direction: str = None) -> dict:

    lead = None

    if lead_id:
        lead = db.get_lead_by_id(lead_id)
    elif caller_number:
        lead = db.get_lead_by_mobile(caller_number)

    if lead is None and caller_number:
        new_id = db.add_lead({
            "mobile": caller_number,
            "source": "inbound_call",
            "notes": "Auto-created from inbound call",
        })
        lead = db.get_lead_by_id(new_id)
        lead_id = new_id

    session = {
        "call_sid": call_sid,
        "lead_id": lead_id,
        "caller": caller_number,
        "lead": lead,
        "conversation": ConversationManager(lead),
        "start_time": time.time(),
        "language": "hinglish",
        "turn_count": 0,
    }

    active_calls[call_sid] = session
    log.info("Call session started: %s", call_sid)
    return session

def get_opening_audio(call_sid: str) -> bytes:

    session = active_calls.get(call_sid)
    if not session:
        return safe_tts("Namaste")

    try:
        lead = session.get("lead")
        opening_text = get_opening_message(lead, is_inbound=True)

        log.info("Opening text: %s", opening_text)

        audio = synthesize_speech(opening_text, "hinglish")

        if not audio:
            raise Exception("Empty audio")

        return audio

    except Exception as e:
        log.error("Opening failed: %s", e)
        return safe_tts("Namaste, Aap kaun si bike dekh rahe hain?")

async def process_customer_speech_async(call_sid: str, audio_bytes: bytes) -> bytes:

    session = active_calls.get(call_sid)
    if not session:
        return safe_tts("Ji boliye")

    try:
        stt_result = await transcribe_audio_async(audio_bytes, "hi-IN")
        customer_text = stt_result.get("text", "").strip()
        lang = stt_result.get("language", "hinglish")

        if not customer_text:
            return await synthesize_speech_async("Ji boliye", lang)

        log.info("[%s] Customer: %s", call_sid, customer_text)

        from intent import detect_intent
        intent_response = detect_intent(customer_text, lead=session.get("lead"))

        conv = session["conversation"]

        if intent_response:
            reply = intent_response
            conv.add_exchange(customer_text, reply)
        else:
            ai_reply = conv.chat(customer_text)
            reply = re.sub(r'\{[\s\S]*?\}', '', ai_reply).strip()

        if not reply:
            reply = "Ji, samajh rahi hoon. Aap bataaiye?"

        log.info("[%s] AI: %s", call_sid, reply)

        audio = await synthesize_speech_async(reply, lang)

        if not audio:
            return await synthesize_speech_async("Ji boliye", lang)

        return audio

    except Exception as e:
        log.error("[%s] ERROR: %s", call_sid, e)
        return await synthesize_speech_async("Ji boliye", "hinglish")

def process_customer_speech(call_sid: str, audio_bytes: bytes) -> bytes:

    session = active_calls.get(call_sid)
    if not session:
        return safe_tts("Ji boliye")

    try:
        stt = transcribe_audio(audio_bytes, "hi-IN")
        text = stt.get("text", "").strip()

        if not text:
            return safe_tts("Ji boliye")

        from intent import detect_intent
        intent = detect_intent(text, lead=session.get("lead"))

        conv = session["conversation"]

        if intent:
            reply = intent
            conv.add_exchange(text, reply)
        else:
            reply = conv.chat(text)

        reply = re.sub(r'\{[\s\S]*?\}', '', reply).strip()

        return safe_tts(reply or "Ji boliye")

    except Exception as e:
        log.error("Sync error: %s", e)
        return safe_tts("Ji boliye")

def end_call_session(call_sid: str, duration_sec: int = 0) -> dict:

    session = active_calls.pop(call_sid, None)
    if not session:
        return {}

    conv = session["conversation"]

    transcript = conv.get_full_transcript()
    analysis = conv.analyze_call()

    log.info("Call ended: %s", call_sid)

    return analysis
