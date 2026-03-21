"""
main.py — Shubham Motors AI Voice Agent
FastAPI server handling all Exotel webhooks, admin dashboard, lead import, offer upload.
Run: python main.py

KEY DESIGN NOTES:
- Exotel webhooks must respond within ~8-10 seconds or the call drops.
- All TTS/STT/AI calls are blocking HTTP — run them in a ThreadPoolExecutor.
- Exotel ExoML uses <Record> (NOT <Gather input="speech"> which is Twilio TwiML)
  <Record> captures customer audio → Exotel POSTs RecordingUrl → we download + STT.
- Always have a <Say> fallback in case Sarvam TTS is slow/unavailable.
"""
import base64
import os, json, re, io, asyncio, time
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

from fastapi import WebSocket, WebSocketDisconnect

import pandas as pd
import requests as _requests
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, Response
import uvicorn
import numpy as np 

import config
import sheets_manager as db
from call_handler import (
    start_call_session, get_opening_audio,
    end_call_session, active_calls
)
from agent import get_opening_message
from lead_manager import process_call_result, add_leads_from_import, get_dashboard_stats
from exotel_client import make_outbound_call
from scraper import parse_offer_file, scrape_hero_website
from scheduler import start_scheduler, stop_scheduler
from voice import synthesize_speech, transcribe_audio
from keep_alive import keep_alive

# ── App setup ──────────────────────────────────────────────────────────────────
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
_greeting_pcm_cache = {}

# Thread pool for ALL blocking I/O (Sarvam TTS, Deepgram STT, Groq LLM)
# This prevents blocking the FastAPI async event loop
_executor = ThreadPoolExecutor(max_workers=12)


# ── STARTUP / SHUTDOWN using modern lifespan ───────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Modern lifespan context manager for startup/shutdown."""
    # Startup
    keep_alive()
    print(f"\n{'='*60}")
    print(f"  SHUBHAM MOTORS AI AGENT — STARTING UP")
    print(f"  {config.BUSINESS_NAME}, {config.BUSINESS_CITY}")
    print(f"  Public URL: {config.PUBLIC_URL}")
    print(f"  Exophone: {config.EXOTEL_PHONE_NUMBER}")
    print(f"{'='*60}\n")
    try:
        scrape_hero_website()
        print("Hero bike catalog loaded")
    except Exception as e:
        print(f"Catalog load failed: {e} (using fallback data)")
    start_scheduler()

    async def _prewarm():
        await asyncio.sleep(3)  # let server fully start first
        from agent import get_opening_message
        text = get_opening_message(None, is_inbound=True)
        audio = await _run(synthesize_speech, text, "hinglish", timeout=15.0)
        if audio:
            pcm = await _run(_mp3_to_pcm, audio, timeout=5.0)
            if pcm:
                _greeting_pcm_cache["data"] = pcm
                print(f"[Startup] ✅ Greeting PCM cached: {len(pcm)} bytes")
        else:
            print("[Startup] ⚠️ Greeting prewarm failed")
    
    asyncio.create_task(_prewarm())
    
    yield  # Application runs here
    
    # Shutdown
    print("\n[Shutdown] Stopping scheduler...")
    stop_scheduler()
    print("[Shutdown] Done")


app = FastAPI(title="Shubham Motors AI Agent", version="2.1.0", lifespan=lifespan)

# ── HEALTH ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return JSONResponse({
        "status": "running",
        "agent": "Shubham Motors AI Voice Agent",
        "dashboard": f"{config.PUBLIC_URL}/dashboard",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })

@app.get("/health")
async def health():
    return {"status": "ok"}


# ── HELPER FUNCTIONS ───────────────────────────────────────────────────────────

def _is_silence(pcm: bytes, threshold: int = 200) -> bool:
    samples = np.frombuffer(pcm, dtype=np.int16)
    rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
    print(f"[VAD] RMS: {rms:.0f}")
    return rms < threshold

def _hangup_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'


def _xml_safe(text: str) -> str:
    """Escape XML special characters for use inside <Say> tags."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


def _record_xml(call_sid: str, play_url: str = None, say_text: str = None, 
                include_transfer: bool = True, transfer_key: str = "0") -> str:
    """
    Return ExoML that plays audio then records customer's reply.
    Uses Sarvam TTS audio via <Play>.
    
    If include_transfer is True, adds finishOnKey for DTMF transfer to human agent.
    """

    content = ""
    if play_url:
        content = f"<Play>{play_url}</Play>"
    elif say_text:
        content = f'<Say language="hi-IN" voice="woman">{_xml_safe(say_text)}</Say>'
    
    # Add instruction for transfer if enabled
    if say_text and include_transfer:
        transfer_instruction = f'<Say language="hi-IN">Agent se baat ke liye {transfer_key} press karein.</Say>'
        content = transfer_instruction + content
    
    # Use finishOnKey for DTMF transfer
    finish_key = transfer_key if include_transfer else "#"
    
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
{content}
<Record action="{config.PUBLIC_URL}/call/gather/{call_sid}"
        method="POST"
        maxLength="60"
        timeout="10"
        playBeep="false"
        finishOnKey="{finish_key}" />
</Response>"""

def _download_recording(url: str) -> bytes:
    """
    Download a <Record> audio file from Exotel.
    Exotel requires API key+token authentication for recording URLs.
    """
    try:
        r = _requests.get(
            url,
            auth=(config.EXOTEL_API_KEY, config.EXOTEL_API_TOKEN),
            timeout=15
        )
        r.raise_for_status()
        print(f"[Audio] Downloaded {len(r.content)} bytes from Exotel recording")
        return r.content
    except Exception as e:
        print(f"[Audio] Download failed: {e}")
        return b""


async def _run(fn, *args, timeout: float = 12.0):
    """
    Run a blocking function in the thread pool with a timeout.
    Returns None if timeout or exception occurs.
    Essential for keeping Exotel webhook response time under ~8s.
    """
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(_executor, fn, *args),
            timeout=timeout
        )
    except asyncio.TimeoutError:
        print(f"[Async] Timeout ({timeout}s) in {getattr(fn, '__name__', str(fn))}")
        return None
    except Exception as e:
        print(f"[Async] Error in {getattr(fn, '__name__', str(fn))}: {e}")
        return None


# ── HUMAN TRANSFER HANDLER ─────────────────────────────────────────────────────

async def _transfer_to_human(call_sid: str, session: dict):
    """
    Transfer call to a human agent while AI continues listening.
    
    This function:
    1. Gets available agent from pool
    2. Initiates transfer via Exotel
    3. AI continues to listen in background (if supported)
    4. Logs the conversation for learning
    5. Notifies agent with lead context
    """
    from exotel_client import transfer_to_human, get_available_agent
    import sheets_manager as db
    
    # Get agent
    agent = get_available_agent()
    agent_number = agent.get("number")
    
    if not agent_number:
        # No agent available - inform customer
        return Response(
            content=_record_xml(call_sid, say_text="Sorry, koi agent available nahi hai. Hum aapko call back karenge.", 
                               include_transfer=False),
            media_type="application/xml",
        )
    
    # Get conversation transcript so far for the agent
    conv = session.get("conversation")
    transcript = ""
    if conv:
        transcript = conv.get_full_transcript()
        # Add summary of what AI discussed
        session["transcript"] = transcript
        session["transfer_reason"] = "customer_requested"
    
    # Get lead info
    lead_id = session.get("lead_id", "")
    lead_info = {}
    if lead_id:
        lead_info = db.get_lead_by_id(lead_id) or {}
    
    # Mark session as transferring
    session["transferring"] = True
    session["transfer_to"] = agent_number
    session["transfer_time"] = datetime.now().isoformat()
    
    # Log transfer request
    print(f"[Transfer] {call_sid} -> {agent['name']} ({agent_number})")
    print(f"[Transfer] Lead: {lead_info.get('name', 'Unknown')} | {lead_info.get('mobile', '')}")
    
    # Perform transfer via Exotel API
    transfer_result = await _run(transfer_to_human, call_sid, agent_number, timeout=10.0)
    
    if transfer_result and transfer_result.get("success"):
        # Log the conversation before transfer completes
        db.log_call({
            "lead_id": lead_id,
            "mobile": lead_info.get("mobile", ""),
            "direction": session.get("direction", "outbound"),
            "duration_sec": int((datetime.now() - session.get("start_time", datetime.now())).total_seconds()),
            "status": "transferred_to_agent",
            "transcript": transcript[:5000] if transcript else "",
            "sentiment": "neutral",
            "ai_summary": f"Call transferred to {agent['name']}. Customer requested human agent.",
            "next_action": "agent_followup",
        })
        
        # Update lead with transfer info
        if lead_id:
            db.update_lead(lead_id, {
                "status": "agent_assigned",
                "assigned_to": agent["name"],
                "assigned_mobile": agent_number,
                "notes": (lead_info.get("notes", "") + f"\n[TRANSFER] Transferred to {agent['name']} at {datetime.now()}").strip()
            })
        
        # Return transfer response to Exotel
        return Response(
            content=f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say language="hi-IN">Okay, aapka call {agent['name']} ko transfer kar rahi hoon. Please hold on.</Say>
</Response>""",
            media_type="application/xml",
        )
    else:
        # Transfer failed - inform customer
        print(f"[Transfer] FAILED for {call_sid}: {transfer_result}")
        return Response(
            content=_record_xml(call_sid, say_text="Sorry, agent se connect karne mein problem ho rahi hai. Main aapki help karne ki koshish kar rahi hoon.", 
                               include_transfer=True),
            media_type="application/xml",
        )


# ── EXOTEL WEBHOOKS ────────────────────────────────────────────────────────────

@app.api_route("/call/incoming", methods=["GET", "POST"])
async def incoming_call(request: Request, background_tasks: BackgroundTasks):
    if request.method == "GET":
        data = request.query_params
    else:
        data = await request.form()

    call_sid = data.get("CallSid", "").strip()
    caller   = data.get("From", "").strip()

    print(f"\n[Incoming] Call from {caller} | SID: {call_sid}")

    if not call_sid:
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?><Response></Response>',
            media_type="application/xml"
        )

    start_call_session(call_sid, caller)

    greeting = "Namaste! Main Priya bol rahi hoon, Shubham Motors Hero MotoCorp se, Jaipur. Aap ka call receive karke bahut khushi hui! Kaise madad kar sakti hoon aapki?"
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Say language="hi-IN">{_xml_safe(greeting)}</Say>
  <Record action="{config.PUBLIC_URL}/call/gather/{call_sid}"
          method="POST"
          maxLength="60"
          timeout="10"
          playBeep="false"
          finishOnKey="#" />
</Response>"""

    return Response(content=xml, media_type="application/xml")

@app.api_route("/call/handler", methods=["GET", "POST"])
async def outbound_call_handler(request: Request):
    """
    Exotel hits this when our outbound call connects to the customer.
    Same flow as incoming — greet + record.
    """
    form = await request.form()
    call_sid = form.get("CallSid", "").strip()
    called   = form.get("To", "").strip()
    lead_id  = form.get("CustomField", "").strip()

    print(f"\n[Outbound] Call to {called} | SID: {call_sid} | Lead: {lead_id}")

    if not call_sid:
        return Response(content=_hangup_xml(), media_type="application/xml")

    # Avoid duplicate sessions (outbound can sometimes trigger twice)
    if call_sid not in active_calls:
        start_call_session(call_sid, called, lead_id=lead_id)
    else:
        print(f"[Outbound] Session already exists for {call_sid}, skipping duplicate init")

    opening_url = None
    try:
        opening_audio = await _run(get_opening_audio, call_sid, timeout=8.0)
        if opening_audio:
            opening_path = UPLOAD_DIR / f"opening_{call_sid}.mp3"
            opening_path.write_bytes(opening_audio)
            opening_url = f"{config.PUBLIC_URL}/call/audio/opening/{call_sid}"
    except Exception as e:
        print(f"[Outbound] Greeting gen error: {e}")

    if opening_url:
        return Response(
            content=_record_xml(call_sid, play_url=opening_url),
            media_type="application/xml"
        )
    else:
        greeting = (
            "Namaste! Main Priya bol rahi hoon, Shubham Motors Hero MotoCorp se, Jaipur. "
            "Aapki Hero bike enquiry ke baare mein baat karna tha — "
            "kya aap abhi thodi der baat kar sakte hain?"
        )
        return Response(
            content=_record_xml(call_sid, say_text=greeting),
            media_type="application/xml"
        )


@app.post("/call/gather/{call_sid}")
async def handle_gather(call_sid: str, request: Request):
    """
    Exotel POSTs here after <Record> captures customer's speech.

    For <Record> responses: form contains RecordingUrl (audio file URL)
    For <Gather> responses: form contains SpeechResult or Digits

    We download the recording → STT (Deepgram/Sarvam) → Groq LLM → TTS → return ExoML.
    All heavy operations run async in ThreadPoolExecutor with timeouts.
    """
    try:
        form = await request.form()

        # <Record> sends RecordingUrl; <Gather> sends SpeechResult/Digits
        recording_url = form.get("RecordingUrl", "").strip()
        speech_result = form.get("SpeechResult", "").strip()
        digits = form.get("Digits", "").strip()

        print(
            f"[Gather] [{call_sid}] RecordingUrl={bool(recording_url)} "
            f"SpeechResult='{speech_result[:60]}' Digits='{digits}'"
        )

        # ── Get active session ─────────────────────────────────────────
        session = active_calls.get(call_sid)
        if not session:
            print(f"[Gather] [{call_sid}] No session found — hanging up")
            return Response(content=_hangup_xml(), media_type="application/xml")

        # ── Transcribe customer input ──────────────────────────────────
        customer_input = speech_result or digits

        if not customer_input and recording_url:
            # Download recording from Exotel (requires auth)
            audio_bytes = await _run(_download_recording, recording_url, timeout=12.0)

            if audio_bytes:
                # Transcribe with Sarvam/Deepgram
                stt_result = await _run(transcribe_audio, audio_bytes, "hi-IN", timeout=10.0)
                if stt_result:
                    customer_input = stt_result.get("text", "").strip()
                    detected_lang = stt_result.get("language", "hinglish")

                    print(
                        f"[Gather] [{call_sid}] STT: '{customer_input[:120]}' "
                        f"({detected_lang})"
                    )

                    if customer_input:
                        session["language"] = detected_lang

        # ── Handle silence / empty input ───────────────────────────────
        if not customer_input:
            silence_count = session.get("silence_count", 0) + 1
            session["silence_count"] = silence_count

            print(f"[Gather] [{call_sid}] Silence #{silence_count}")

            if silence_count >= 3:
                print(f"[Gather] [{call_sid}] 3 silences — hanging up")
                return Response(content=_hangup_xml(), media_type="application/xml")

            retry_text = "Ji? Kuch clearly suna nahi — kya aap thoda louder bol sakte hain?"

            return Response(
                content=_record_xml(call_sid, say_text=retry_text),
                media_type="application/xml",
            )

        # Reset silence counter on successful speech
        session["silence_count"] = 0
        session["turn_count"] = session.get("turn_count", 0) + 1

        print(
            f"[Gather] [{call_sid}] Customer (turn {session['turn_count']}): "
            f"'{customer_input[:120]}'"
        )

        # ── CHECK FOR HUMAN TRANSFER REQUEST ───────────────────────────
        # 1. DTMF key pressed (transfer_key like "0")
        if digits and digits == config.TRANSFER_DTMF_KEY:
            print(f"[Gather] [{call_sid}] TRANSFER REQUESTED via DTMF!")
            return await _transfer_to_human(call_sid, session)
        
        # 2. Check for transfer keywords in speech
        customer_lower = customer_input.lower()
        if any(kw in customer_lower for kw in config.TRANSFER_KEYWORDS):
            print(f"[Gather] [{call_sid}] TRANSFER REQUESTED via speech: '{customer_input}'")
            return await _transfer_to_human(call_sid, session)

        # ── Get AI response via Groq LLM ───────────────────────────────
        conv = session["conversation"]
        voice_text = None

        ai_reply = await _run(conv.chat, customer_input, timeout=15.0)

        if ai_reply:
            # Strip JSON blocks
            voice_text = re.sub(r"\{[\s\S]*?\}", "", ai_reply).strip()

        if not voice_text:
            voice_text = "Ji, main samajh rahi hoon. Kya aap thoda aur detail de sakte hain?"

        print(f"[Gather] [{call_sid}] Priya: {voice_text[:120]}")

        # ── Detect language for TTS routing ────────────────────────────
        devanagari_count = sum(1 for c in customer_input if "\u0900" <= c <= "\u097F")

        if devanagari_count > len(customer_input) * 0.3:
            lang = "hindi"
        else:
            lang = session.get("language", "hinglish")

        session["language"] = lang

        # ── Generate TTS audio ─────────────────────────────────────────
        audio_url = None

        ai_audio = await _run(synthesize_speech, voice_text, lang, timeout=12.0)

        if ai_audio:
            audio_path = UPLOAD_DIR / f"response_{call_sid}.mp3"
            audio_path.write_bytes(ai_audio)

            audio_url = f"{config.PUBLIC_URL}/call/audio/response/{call_sid}"

        # ── Return response to Exotel ──────────────────────────────────
        if audio_url:
            return Response(
                content=_record_xml(call_sid, play_url=audio_url),
                media_type="application/xml",
            )
        else:
            print(f"[Gather] [{call_sid}] TTS unavailable — using Say fallback")

            return Response(
                content=_record_xml(call_sid, say_text=voice_text),
                media_type="application/xml",
            )

    except Exception as e:
        print(f"[Gather ERROR] {e}")

        return Response(
            content=_record_xml(call_sid, say_text="Sorry, ek technical issue ho gaya."),
            media_type="application/xml",
        )


@app.post("/call/status")
async def call_status(request: Request, background_tasks: BackgroundTasks):
    """
    Exotel hits this when call ends.
    Analyse conversation and update lead in background (don't block Exotel).
    """
    form = await request.form()
    call_sid = form.get("CallSid", "")
    status   = form.get("Status", "")
    duration = int(form.get("Duration", 0))

    print(f"\n[Status] Call {call_sid} ended | Status: {status} | Duration: {duration}s")

    # Process in background — don't make Exotel wait
    background_tasks.add_task(end_call_session, call_sid, duration)

    # Cleanup audio files
    for prefix in ["opening", "response", "retry"]:
        f = UPLOAD_DIR / f"{prefix}_{call_sid}.mp3"
        if f.exists():
            try:
                f.unlink()
            except Exception:
                pass

    return JSONResponse({"received": True})


# ── AUDIO FILE SERVING ─────────────────────────────────────────────────────────

# @app.get("/call/audio/opening/{call_sid}")
# async def serve_opening_audio(call_sid: str):

#     path = UPLOAD_DIR / f"opening_{call_sid}.mp3"

#     if not path.exists():
#         print(f"[Audio] Generating greeting for {call_sid}")

#         audio = await _run(get_opening_audio, call_sid, timeout=10.0)

#         if not audio:
#             return Response(status_code=404)

#         path.write_bytes(audio)

#     return Response(
#         content=path.read_bytes(),
#         media_type="audio/mpeg"
#     )

@app.get("/call/audio/opening/{call_sid}")
async def serve_opening_audio(call_sid: str):
    print(f"[Audio] Opening requested for {call_sid}")
    print(f"[Audio] Files in uploads: {list(UPLOAD_DIR.iterdir())}")

    # Serve call-specific pre-generated file
    path = UPLOAD_DIR / f"opening_{call_sid}.mp3"
    if path.exists():
        print(f"[Audio] ✅ Serving pre-generated file")
        return Response(content=path.read_bytes(), media_type="audio/mpeg")

    # Fallback to warmup file (same greeting, generated at startup)
    warmup = UPLOAD_DIR / "opening_warmup.mp3"
    if warmup.exists():
        print(f"[Audio] ✅ Serving warmup file")
        return Response(content=warmup.read_bytes(), media_type="audio/mpeg")

    # Last resort: generate on-demand
    audio = await _run(get_opening_audio, call_sid, timeout=10.0)
    if not audio:
        print("[Audio] ❌ No audio returned")
        return Response(status_code=404)

    return Response(content=audio, media_type="audio/mpeg")

@app.get("/call/audio/response/{call_sid}")
async def serve_response_audio(call_sid: str):
    path = UPLOAD_DIR / f"response_{call_sid}.mp3"
    if not path.exists():
        return Response(status_code=404)
    return Response(content=path.read_bytes(), media_type="audio/mpeg")


# ── ADMIN API ──────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats = get_dashboard_stats()
    leads = db.get_all_leads()
    priority = {"hot": 0, "warm": 1, "new": 2, "active": 3, "cold": 4, "dead": 5, "converted": 6}
    leads.sort(key=lambda x: priority.get(x.get("status", "new"), 9))
    return HTMLResponse(_render_dashboard(stats, leads[:100]))


@app.get("/api/leads")
async def api_leads():
    return JSONResponse(db.get_all_leads())


@app.post("/api/leads/add")
async def api_add_lead(request: Request):
    data = await request.json()
    lead_id = db.add_lead(data)
    return JSONResponse({"success": True, "lead_id": lead_id})


@app.post("/api/leads/import")
async def import_leads(file: UploadFile = File(...)):
    content = await file.read()
    ext = Path(file.filename).suffix.lower()
    try:
        df = pd.read_csv(io.BytesIO(content)) if ext == ".csv" else pd.read_excel(io.BytesIO(content))
        df.columns = [c.lower().strip().replace(" ", "_") for c in df.columns]
        col_map = {
            "phone": "mobile", "contact": "mobile", "number": "mobile",
            "customer_name": "name", "customer": "name",
            "model": "interested_model", "bike": "interested_model",
        }
        df.rename(columns=col_map, inplace=True)
        leads = df.to_dict(orient="records")
        ids = add_leads_from_import(leads)
        return JSONResponse({"success": True, "imported": len(ids), "skipped": len(leads) - len(ids)})
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/call/make")
async def trigger_call(request: Request, background_tasks: BackgroundTasks):
    data    = await request.json()
    lead_id = data.get("lead_id", "")
    mobile  = data.get("mobile", "")
    if not mobile and lead_id:
        lead = db.get_lead_by_id(lead_id)
        if lead:
            mobile = lead.get("mobile", "")
    if not mobile:
        raise HTTPException(status_code=400, detail="Mobile number required")
    background_tasks.add_task(make_outbound_call, mobile, lead_id)
    return JSONResponse({"success": True, "message": f"Calling {mobile}..."})


@app.post("/api/offers/upload")
async def upload_offer(
    file: UploadFile = File(...),
    title: str = Form(...),
    valid_till: str = Form(""),
    models: str = Form(""),
):
    content  = await file.read()
    filepath = UPLOAD_DIR / file.filename
    filepath.write_bytes(content)
    offer_text = parse_offer_file(str(filepath))
    offer_id   = db.add_offer({
        "title": title,
        "description": offer_text[:2000],
        "valid_till": valid_till,
        "models": models,
    })
    return JSONResponse({"success": True, "offer_id": offer_id, "preview": offer_text[:200]})


@app.get("/api/stats")
async def api_stats():
    return JSONResponse(get_dashboard_stats())


@app.get("/api/active-calls")
async def api_active_calls():
    return JSONResponse({
        "active_calls": len(active_calls),
        "call_sids": list(active_calls.keys())
    })

async def _process_speech(buf: bytes, call_sid: str, stream_sid: str, websocket: WebSocket, state: dict):
    session = active_calls.get(call_sid)
    if not session:
        return
    if len(buf) < 8000:
        print(f"[Voicebot] Buffer too small ({len(buf)} bytes), skipping")
        return
    if _is_silence(buf):
        print("[Voicebot] Silence detected, skipping STT")
        return
    try:
        wav_bytes = _pcm_to_wav(buf)
        if wav_bytes:
            # Save for inspection
            with open("/tmp/debug_audio.wav", "wb") as f:
                f.write(wav_bytes)
            print(f"[Debug] Saved WAV: {len(wav_bytes)} bytes, header: {wav_bytes[:12]}")
        if not wav_bytes:
            print("[Voicebot] Audio conversion failed")
            return
        stt_result = await _run(transcribe_audio, wav_bytes, "hi-IN", timeout=10.0)
        customer_text = stt_result.get("text", "").strip() if stt_result else ""
        print(f"[Voicebot] STT: '{customer_text[:120]}'")

        if not customer_text:
            return

        detected_lang = stt_result.get("language", "hinglish")
        session["language"] = detected_lang

        conv = session["conversation"]
        ai_reply = await _run(conv.chat, customer_text, timeout=15.0)
        voice_text = re.sub(r"\{.*", "", ai_reply, flags=re.DOTALL).strip() if ai_reply else ""
        
        if not voice_text:
            voice_text = "Ji, main samajh rahi hoon. Kya aap thoda aur detail de sakte hain?"

        print(f"[Voicebot] Priya: {voice_text[:120]}")

        audio = await _run(synthesize_speech, voice_text, detected_lang, timeout=12.0)
        if audio:
            pcm = await _run(_mp3_to_pcm, audio, timeout=5.0)
            if pcm:
                b64 = base64.b64encode(pcm).decode("ascii")
                await websocket.send_text(json.dumps({
                    "event": "media",
                    "stream_sid": stream_sid,
                    "media": {"payload": b64}
                }))
                print(f"[Voicebot] Sent response ({len(pcm)} bytes)")
                response_secs = len(pcm) / 16000  # 8kHz 16-bit = 16000 bytes/sec
                state["listen_after"] = time.monotonic() + response_secs + 0.8
                print(f"[Voicebot] Blocking input for {response_secs:.1f}s")

    except Exception as e:
        print(f"[Voicebot] _process_speech error: {e}")

# ── VOICEBOT WEBSOCKET ─────────────────────────────────────────────────────────

# @app.websocket("/call/stream")
# async def voicebot_stream(websocket: WebSocket):
#     await websocket.accept()
#     call_sid = None
#     stream_sid = ""
#     audio_buffer = b""
    
#     print("[Voicebot] WebSocket connected")
    
#     try:
#         async for message in websocket.iter_text():
#             data = json.loads(message)
#             event = data.get("event", "")
            
#             # ── Call started ───────────────────────────────────────────
#             if event == "connected":
#                 print("[Voicebot] Stream connected")
            
#             elif event == "start":
#                 call_sid = data.get("start", {}).get("callSid", "")
#                 stream_sid = data.get("start", {}).get("streamSid", "")
#                 caller = data.get("start", {}).get("from", "")
#                 print(f"[Voicebot] Call started | SID: {call_sid} | From: {caller}")
                
#                 start_call_session(call_sid, caller)
                
#                 # Send opening greeting immediately
#                 session = active_calls.get(call_sid)
#                 if session:
#                     greeting = get_opening_message(session.get("lead"), is_inbound=True)
#                     session["conversation"].history.append({
#                         "role": "assistant", "content": greeting
#                     })
                    
#                     pcm = _greeting_pcm_cache.get("data")

#                     # Generate TTS audio
#                     if not pcm:
#                          # Cache miss — generate on the fly (first call after deploy)
#                         audio = await _run(synthesize_speech, greeting, "hinglish", timeout=10.0)
#                         if audio:
#                             pcm = await _run(_mp3_to_pcm, audio, timeout=5.0)
        
#                     if pcm:
#                         b64 = base64.b64encode(pcm).decode("ascii")
#                         await websocket.send_text(json.dumps({
#                             "event": "media",
#                             "stream_sid": stream_sid,
#                             "media": {"payload": b64}
#                         }))
#                         print(f"[Voicebot] Sent greeting ({len(pcm)} bytes, cached={bool(_greeting_pcm_cache.get('data'))})")
            
#             # ── Incoming audio from customer ───────────────────────────
#             elif event == "media":
#                 payload = data.get("media", {}).get("payload", "")
#                 if payload:
#                     chunk = base64.b64decode(payload)
#                     audio_buffer += chunk
            
#             # ── Customer stopped speaking ──────────────────────────────
#             elif event == "stop":
#                 print(f"[Voicebot] Stream stopped | SID: {call_sid}")
#                 if call_sid:
#                     asyncio.create_task(end_call_session(call_sid, 0))
            
#             # ── Process buffered audio when silence detected ───────────
#             elif event == "mark":
#                 if audio_buffer and call_sid and len(audio_buffer) > 3200:
#                     pcm_bytes = audio_buffer
#                     audio_buffer = b""
                    
#                     # Convert PCM to WAV for Sarvam STT
#                     wav_bytes = _pcm_to_wav(pcm_bytes)
                    
#                     session = active_calls.get(call_sid)
#                     if not session:
#                         continue
                    
#                     # STT
#                     stt_result = await _run(transcribe_audio, wav_bytes, "hi-IN", timeout=10.0)
#                     customer_text = stt_result.get("text", "").strip() if stt_result else ""
                    
#                     print(f"[Voicebot] STT: '{customer_text[:120]}'")
                    
#                     if not customer_text:
#                         silence_count = session.get("silence_count", 0) + 1
#                         session["silence_count"] = silence_count
#                         if silence_count >= 3:
#                             await websocket.send_text(json.dumps({"event": "stop"}))
#                             continue
#                         retry = "Ji? Kuch suna nahi — thoda louder bolein?"
#                         audio = await _run(synthesize_speech, retry, "hinglish", timeout=8.0)
#                     else:
#                         session["silence_count"] = 0
#                         detected_lang = stt_result.get("language", "hinglish")
#                         session["language"] = detected_lang
                        
#                         # Groq LLM
#                         conv = session["conversation"]
#                         ai_reply = await _run(conv.chat, customer_text, timeout=15.0)
#                         voice_text = re.sub(r"\{[\s\S]*?\}", "", ai_reply).strip() if ai_reply else ""
                        
#                         if not voice_text:
#                             voice_text = "Ji, main samajh rahi hoon. Kya aap thoda aur detail de sakte hain?"
                        
#                         print(f"[Voicebot] Priya: {voice_text[:120]}")
                        
#                         # TTS
#                         audio = await _run(synthesize_speech, voice_text, detected_lang, timeout=12.0)
                    
#                     if audio:
#                         pcm = await _run(_mp3_to_pcm, audio, timeout=5.0)
#                         if pcm:
#                             b64 = _encode_pcm(pcm)
#                             await websocket.send_text(json.dumps({
#                                 "event": "media",
#                                 "stream_sid": stream_sid,
#                                 "media": {"payload": b64}
#                             }))
    
#     except WebSocketDisconnect:
#         print(f"[Voicebot] WebSocket disconnected | SID: {call_sid}")
#         if call_sid:
#             asyncio.create_task(end_call_session(call_sid, 0))
#     except Exception as e:
#         print(f"[Voicebot] Error: {e}")
#         if call_sid:
#             asyncio.create_task(end_call_session(call_sid, 0))

@app.websocket("/call/stream")
async def voicebot_stream(websocket: WebSocket):
    await websocket.accept()
    print("[Voicebot] WebSocket connected")

    call_sid = None
    stream_sid = ""
    audio_buffer = b""
    state = {"listen_after": 0.0}
    _busy = [False]

    try:
        async for message in websocket.iter_text():
            data = json.loads(message)
            event = data.get("event", "")

            if event == "connected":
                print("[Voicebot] Stream connected")

            elif event == "start":
                start_data = data.get("start", {})
                print(f"[Voicebot] Start event full data: {json.dumps(start_data)}")
                call_sid = start_data.get("callSid") or start_data.get("call_sid") or ""
                stream_sid = start_data.get("streamSid") or start_data.get("stream_sid") or ""
                caller = start_data.get("from", "")
                print(f"[Voicebot] Call started | SID: {call_sid} | From: {caller}")

                start_call_session(call_sid, caller)
                session = active_calls.get(call_sid)

                if session:
                    greeting = get_opening_message(session.get("lead"), is_inbound=True)
                    session["conversation"].history.append({
                        "role": "assistant", "content": greeting
                    })

                    pcm = _greeting_pcm_cache.get("data")
                    if not pcm:
                        audio = await _run(synthesize_speech, greeting, "hinglish", timeout=10.0)
                        if audio:
                            pcm = await _run(_mp3_to_pcm, audio, timeout=5.0)

                    if pcm:
                        b64 = base64.b64encode(pcm).decode("ascii")
                        await websocket.send_text(json.dumps({
                            "event": "media",
                            "stream_sid": stream_sid,
                            "media": {"payload": b64}
                        }))
                        greeting_secs = len(pcm) / 16000
                        state["listen_after"] = time.monotonic() + greeting_secs + 1.0
                        print(f"[Voicebot] Sent greeting ({len(pcm)} bytes), blocking {greeting_secs:.1f}s")
                        await websocket.send_text(json.dumps({
                            "event": "mark",
                            "stream_sid": stream_sid,
                            "mark": {"name": "greeting_done"}
                        }))

            elif event == "media":
                if _busy[0]:
                    continue
                if time.monotonic() < state["listen_after"]:
                    continue
                payload = data.get("media", {}).get("payload", "")
                if not payload:
                    continue

                chunk = base64.b64decode(payload)
                audio_buffer += chunk

                if len(audio_buffer) >= 64000 and not _busy[0]:
                    buf = audio_buffer
                    audio_buffer = b""
                    _busy[0] = True

                    async def handle_speech(b=buf):
                        try:
                            await _process_speech(b, call_sid, stream_sid, websocket, state)
                        finally:
                            _busy[0] = False

                    asyncio.create_task(handle_speech())

            elif event == "stop":
                print(f"[Voicebot] Stream stopped | SID: {call_sid}")
                if call_sid:
                    end_call_session(call_sid, 0)

            elif event == "mark":
                name = data.get('mark', {}).get('name', '')
                print(f"[Voicebot] Mark received: {name}")

    except WebSocketDisconnect:
        print(f"[Voicebot] Disconnected | SID: {call_sid}")
        if call_sid:
            end_call_session(call_sid, 0)
    except Exception as e:
        print(f"[Voicebot] Error: {e}")
        if call_sid:
            end_call_session(call_sid, 0)

# ── AUDIO CONVERSION HELPERS ───────────────────────────────────────────────────

def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 8000) -> bytes:
    """Convert raw PCM bytes to WAV format for Sarvam STT."""
    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _mp3_to_pcm(mp3_bytes: bytes) -> bytes:
    """Convert audio bytes (WAV or MP3) to raw PCM 16-bit 8kHz mono for Exotel."""
    try:
        from pydub import AudioSegment
        import io
        
        if not mp3_bytes or len(mp3_bytes) < 100:
            print(f"[Audio] Audio too small: {len(mp3_bytes)} bytes")
            return b""
        
        # Detect format from magic bytes
        if mp3_bytes[:4] == b'RIFF':
            fmt = "wav"
        elif mp3_bytes[:3] == b'ID3' or mp3_bytes[:2] in (b'\xff\xfb', b'\xff\xf3'):
            fmt = "mp3"
        else:
            fmt = "wav"  # Sarvam default
        
        print(f"[Audio] Converting {fmt} ({len(mp3_bytes)} bytes) to PCM")
        audio = AudioSegment.from_file(io.BytesIO(mp3_bytes), format=fmt)
        audio = audio.set_frame_rate(8000).set_channels(1).set_sample_width(2)
        print(f"[Audio] PCM ready: {len(audio.raw_data)} bytes")
        return audio.raw_data
    except Exception as e:
        print(f"[Audio] Audio to PCM failed: {e}")
        return b""


def _encode_pcm(pcm_bytes: bytes) -> str:
    """Base64 encode PCM bytes for Exotel WebSocket."""
    return base64.b64encode(pcm_bytes).decode("utf-8")

# ── DASHBOARD HTML ─────────────────────────────────────────────────────────────

def _render_dashboard(stats: dict, leads: list) -> str:
    badge = {
        "hot": "🔥", "warm": "🟡", "cold": "❄️",
        "dead": "☠️", "converted": "✅", "new": "🆕", "active": "📞"
    }
    rows = ""
    for l in leads:
        s = l.get("status", "new")
        ic = badge.get(s, "⚪")
        rows += f"""
        <tr>
          <td>{ic} {l.get('name') or '—'}</td>
          <td>{l.get('mobile','')}</td>
          <td>{l.get('interested_model') or '—'}</td>
          <td><span class="badge badge-{s}">{s.upper()}</span></td>
          <td>{l.get('assigned_to') or '—'}</td>
          <td>{l.get('next_followup') or '—'}</td>
          <td>{l.get('call_count',0)}</td>
          <td>
            <button onclick="callLead('{l.get('lead_id','')}','{l.get('mobile','')}')"
                    class="btn-call">📞 Call</button>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Shubham Motors — AI Agent</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',sans-serif;background:#0d0d1a;color:#e0e0e0;min-height:100vh}}
.header{{background:linear-gradient(135deg,#1a0a2e,#0d1a3e);padding:18px 30px;border-bottom:2px solid #cc2200;display:flex;align-items:center;justify-content:space-between}}
.header h1{{color:#fff;font-size:1.4em}}
.header p{{color:#aaa;font-size:0.8em;margin-top:3px}}
.live{{background:#1a4a1a;color:#4f4;padding:5px 12px;border-radius:20px;font-size:0.8em;font-weight:bold}}
.stats{{display:flex;gap:12px;padding:18px 30px;flex-wrap:wrap}}
.card{{background:#1a1a2e;border-radius:10px;padding:14px 20px;min-width:120px;border:1px solid #2a2a4a;text-align:center}}
.card .num{{font-size:2em;font-weight:bold}}
.card .lbl{{color:#888;font-size:0.75em;margin-top:3px}}
.section{{padding:0 30px 30px}}
.toolbar{{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap}}
.btn{{background:#cc2200;color:#fff;border:none;padding:9px 16px;border-radius:6px;cursor:pointer;font-size:0.85em;font-weight:600}}
.btn:hover{{background:#aa1a00}}
.btn-green{{background:#1a6a1a}}.btn-green:hover{{background:#145014}}
.btn-purple{{background:#5a1a8a}}.btn-purple:hover{{background:#3a0a6a}}
.btn-teal{{background:#1a5a5a}}.btn-teal:hover{{background:#0a4040}}
.btn-call{{background:#1a3a7a;color:#fff;border:none;padding:5px 10px;border-radius:4px;cursor:pointer;font-size:0.78em}}
.btn-call:hover{{background:#0a2a5a}}
table{{width:100%;border-collapse:collapse;background:#1a1a2e;border-radius:10px;overflow:hidden;font-size:0.88em}}
th{{background:#252540;color:#999;padding:11px 10px;text-align:left;font-size:0.8em;text-transform:uppercase;letter-spacing:.5px}}
td{{padding:10px;border-bottom:1px solid #252540}}
tr:hover{{background:#202035}}
.badge{{padding:3px 8px;border-radius:12px;font-size:0.75em;font-weight:bold}}
.badge-hot{{background:#3a0a0a;color:#ff5555}}
.badge-warm{{background:#3a2a0a;color:#ffaa00}}
.badge-cold{{background:#0a1a3a;color:#5588ff}}
.badge-dead{{background:#1a1a1a;color:#777}}
.badge-converted{{background:#0a2a0a;color:#44cc44}}
.badge-new{{background:#0a2a3a;color:#44aaff}}
.badge-active{{background:#1a2a1a;color:#44dd44}}
.modal{{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.85);z-index:1000;align-items:center;justify-content:center}}
.modal.open{{display:flex}}
.mbox{{background:#1a1a2e;border-radius:12px;padding:28px;width:460px;max-width:95vw;border:1px solid #3a3a5a}}
.mbox h3{{margin-bottom:18px;color:#fff}}
label{{color:#999;font-size:0.82em;display:block;margin-bottom:4px}}
input,select,textarea{{width:100%;background:#252540;border:1px solid #3a3a5a;color:#fff;padding:9px 12px;border-radius:6px;margin-bottom:10px;font-size:0.88em}}
.row{{display:flex;gap:8px}}
.hint{{color:#666;font-size:0.78em;margin-bottom:12px}}
#toastContainer{{position:fixed;bottom:20px;right:20px;z-index:9999}}
.toast{{background:#1a3a1a;color:#4f4;border:1px solid #2a5a2a;padding:12px 20px;border-radius:8px;margin-top:8px;font-size:0.9em}}
.toast.err{{background:#3a1a1a;color:#f55;border-color:#5a2a2a}}
</style>
</head>
<body>
<div class="header">
  <div>
    <h1>🏍️ Shubham Motors — AI Voice Agent</h1>
    <p>Hero MotoCorp Authorized Dealer • Lal Kothi, Jaipur</p>
  </div>
  <div class="live">🟢 LIVE</div>
</div>

<div class="stats">
  <div class="card"><div class="num">{stats.get('total',0)}</div><div class="lbl">Total Leads</div></div>
  <div class="card"><div class="num" style="color:#ff5555">{stats.get('hot',0)}</div><div class="lbl">🔥 Hot</div></div>
  <div class="card"><div class="num" style="color:#ffaa00">{stats.get('warm',0)}</div><div class="lbl">🟡 Warm</div></div>
  <div class="card"><div class="num" style="color:#5588ff">{stats.get('cold',0)}</div><div class="lbl">❄️ Cold</div></div>
  <div class="card"><div class="num" style="color:#44cc44">{stats.get('converted',0)}</div><div class="lbl">✅ Converted</div></div>
  <div class="card"><div class="num" style="color:#777">{stats.get('dead',0)}</div><div class="lbl">☠️ Dead</div></div>
  <div class="card"><div class="num" style="color:#44aaff">{stats.get('new',0)}</div><div class="lbl">🆕 New</div></div>
</div>

<div class="section">
  <div class="toolbar">
    <button class="btn" onclick="open_modal('addModal')">➕ Add Lead</button>
    <button class="btn btn-green" onclick="open_modal('importModal')">📥 Import Excel</button>
    <button class="btn btn-purple" onclick="open_modal('offerModal')">🎁 Upload Offer</button>
    <button class="btn btn-teal" onclick="location.reload()">🔄 Refresh</button>
  </div>
  <table>
    <thead>
      <tr>
        <th>Customer</th><th>Mobile</th><th>Interested In</th>
        <th>Status</th><th>Assigned To</th><th>Next Follow-up</th>
        <th>Calls</th><th>Action</th>
      </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>

<!-- Add Lead -->
<div class="modal" id="addModal">
  <div class="mbox">
    <h3>➕ Add New Lead</h3>
    <label>Customer Name</label>
    <input id="f_name" placeholder="Ramesh Kumar">
    <label>Mobile Number *</label>
    <input id="f_mobile" placeholder="9876543210">
    <label>Interested Model</label>
    <select id="f_model">
      <option value="">-- Select Model --</option>
      <option>Splendor Plus</option><option>HF Deluxe</option>
      <option>Passion Pro</option><option>Glamour</option>
      <option>Super Splendor</option><option>Destini 125</option>
      <option>Maestro Edge 125</option><option>Xoom 110</option>
      <option>Xtreme 160R</option><option>Xtreme 125R</option>
      <option>Mavrick 440</option><option>XPulse 200</option>
    </select>
    <label>Budget (₹)</label>
    <input id="f_budget" placeholder="80000">
    <label>Area / Source</label>
    <input id="f_area" placeholder="Malviya Nagar / Facebook Ad">
    <label>Notes</label>
    <textarea id="f_notes" rows="2" placeholder="Any special requirement..."></textarea>
    <div class="row">
      <button class="btn" onclick="addLead()">💾 Save Lead</button>
      <button class="btn" style="background:#333" onclick="close_modal('addModal')">Cancel</button>
    </div>
  </div>
</div>

<!-- Import -->
<div class="modal" id="importModal">
  <div class="mbox">
    <h3>📥 Import Leads from Excel / CSV</h3>
    <p class="hint">Columns needed: name, mobile, interested_model, budget, area, source</p>
    <input type="file" id="importFile" accept=".xlsx,.xls,.csv">
    <div class="row" style="margin-top:8px">
      <button class="btn btn-green" onclick="importLeads()">Import</button>
      <button class="btn" style="background:#333" onclick="close_modal('importModal')">Cancel</button>
    </div>
    <div id="importResult" style="margin-top:10px;color:#4f4;font-size:0.85em"></div>
  </div>
</div>

<!-- Offer Upload -->
<div class="modal" id="offerModal">
  <div class="mbox">
    <h3>🎁 Upload Offer / Scheme</h3>
    <label>Offer Title *</label>
    <input id="o_title" placeholder="Diwali Special — ₹5,000 off + Free Accessories">
    <label>Valid Till</label>
    <input id="o_valid" type="date">
    <label>Applicable Models (comma separated)</label>
    <input id="o_models" placeholder="Splendor Plus, HF Deluxe, Glamour">
    <label>Upload File (PDF / Excel / Image)</label>
    <input type="file" id="offerFile" accept=".pdf,.xlsx,.xls,.png,.jpg,.jpeg">
    <div class="row" style="margin-top:8px">
      <button class="btn btn-purple" onclick="uploadOffer()">Upload</button>
      <button class="btn" style="background:#333" onclick="close_modal('offerModal')">Cancel</button>
    </div>
    <div id="offerResult" style="margin-top:10px;color:#4f4;font-size:0.85em"></div>
  </div>
</div>

<div id="toastContainer"></div>

<script>
function open_modal(id)  {{ document.getElementById(id).classList.add('open') }}
function close_modal(id) {{ document.getElementById(id).classList.remove('open') }}

function toast(msg, err=false) {{
  const t = document.createElement('div');
  t.className = 'toast' + (err ? ' err' : '');
  t.textContent = msg;
  document.getElementById('toastContainer').appendChild(t);
  setTimeout(() => t.remove(), 4000);
}}

document.querySelectorAll('.modal').forEach(m =>
  m.addEventListener('click', e => {{ if (e.target === m) m.classList.remove('open') }})
);

async function addLead() {{
  const mobile = document.getElementById('f_mobile').value.trim();
  if (!mobile) {{ toast('Mobile number is required!', true); return; }}
  const data = {{
    name: document.getElementById('f_name').value,
    mobile,
    interested_model: document.getElementById('f_model').value,
    budget: document.getElementById('f_budget').value,
    area: document.getElementById('f_area').value,
    notes: document.getElementById('f_notes').value,
  }};
  const r = await fetch('/api/leads/add', {{
    method:'POST', headers:{{'Content-Type':'application/json'}}, body:JSON.stringify(data)
  }});
  const res = await r.json();
  if (res.success) {{ toast('Lead added! ID: ' + res.lead_id); close_modal('addModal'); setTimeout(()=>location.reload(),1500); }}
  else {{ toast('Error adding lead', true); }}
}}

async function importLeads() {{
  const file = document.getElementById('importFile').files[0];
  if (!file) {{ toast('Please select a file', true); return; }}
  const fd = new FormData(); fd.append('file', file);
  const r = await fetch('/api/leads/import', {{method:'POST', body:fd}});
  const res = await r.json();
  document.getElementById('importResult').textContent =
    `Imported: ${{res.imported}} leads | Skipped: ${{res.skipped}} duplicates`;
}}

async function callLead(leadId, mobile) {{
  if (!confirm(`Call ${{mobile}} now?\\nPriya will call this number immediately.`)) return;
  const r = await fetch('/api/call/make', {{
    method:'POST', headers:{{'Content-Type':'application/json'}},
    body: JSON.stringify({{lead_id: leadId, mobile}})
  }});
  const res = await r.json();
  toast(res.message || 'Call initiated!');
}}

async function uploadOffer() {{
  const title = document.getElementById('o_title').value.trim();
  const file  = document.getElementById('offerFile').files[0];
  if (!title) {{ toast('Offer title is required!', true); return; }}
  if (!file)  {{ toast('Please select a file', true); return; }}
  const fd = new FormData();
  fd.append('file', file);
  fd.append('title', title);
  fd.append('valid_till', document.getElementById('o_valid').value);
  fd.append('models', document.getElementById('o_models').value);
  const r = await fetch('/api/offers/upload', {{method:'POST', body:fd}});
  const res = await r.json();
  document.getElementById('offerResult').textContent =
    res.success ? 'Offer uploaded! AI will use this in all calls.' : 'Upload failed';
}}

setInterval(async () => {{
  try {{ await fetch('/api/stats'); }} catch(e) {{}}
}}, 30000);
</script>
</body>
</html>"""


# ── ENTRY POINT ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=False)
