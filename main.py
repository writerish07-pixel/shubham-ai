"""
main.py — Shubham Motors AI Voice Agent
FastAPI server handling all Exotel webhooks, admin dashboard, lead import, offer upload.
Run: python main.py

KEY DESIGN NOTES:
- Exotel webhooks must respond within ~8-10 seconds or the call drops.
- All TTS/STT/AI calls are blocking HTTP — run them in a ThreadPoolExecutor.
- Exotel ExoML uses <Record> (NOT <Gather input="speech"> which is Twilio TwiML).
  <Record> captures customer audio → Exotel POSTs RecordingUrl → we download + STT.
- CRITICAL: Sarvam TTS returns WAV bytes. We detect format and serve correct MIME type.
  Serving WAV as audio/mpeg causes silent audio and call disconnection.
"""

import os, json, re, io, asyncio, csv
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import requests as _requests
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, Response
import uvicorn

import config
import sheets_manager as db
from call_handler import (
    start_call_session,
    end_call_session, active_calls
)
from agent import get_opening_message
from lead_manager import process_call_result, add_leads_from_import, get_dashboard_stats
from exotel_client import make_outbound_call as _exotel_make_call
import airtel_iq_client as _airtel_iq
import plivo_client as _plivo
from scraper import parse_offer_file, scrape_hero_website
from scheduler import start_scheduler, stop_scheduler
from voice import synthesize_speech, transcribe_audio, audio_fmt

# ── App setup ──────────────────────────────────────────────────────────────────
app = FastAPI(title="Shubham Motors AI Agent", version="2.3.0")
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# Thread pool for ALL blocking I/O (Sarvam TTS/STT, OpenAI GPT, Exotel API)
_executor = ThreadPoolExecutor(max_workers=12)


# ── STARTUP / SHUTDOWN ─────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    print(f"\n{'='*60}")
    print(f"  SHUBHAM MOTORS AI AGENT — STARTING UP")
    print(f"  {config.BUSINESS_NAME}, {config.BUSINESS_CITY}")
    print(f"  Public URL: {config.PUBLIC_URL}")
    print(f"  Exophone: {config.EXOTEL_PHONE_NUMBER}")
    print(f"  Sarvam TTS: {'READY' if config.SARVAM_API_KEY else 'NOT CONFIGURED'}")
    print(f"  ElevenLabs: {'READY' if config.ELEVENLABS_API_KEY else 'NOT CONFIGURED'}")
    print(f"{'='*60}\n")
    try:
        scrape_hero_website()
        print("[Startup] Hero bike catalog loaded")
    except Exception as e:
        print(f"[Startup] Catalog load failed: {e} (using fallback data)")
    start_scheduler()


@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()


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

def _hangup_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'


def _xml_safe(text: str) -> str:
    """Escape XML special characters for <Say> tags."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


def _record_xml(call_sid: str, play_url: str = None, say_text: str = None,
                provider: str = "exotel") -> str:
    """
    Return ExoML/TwiML that plays audio (or says text), then records customer reply.

    Uses <Record> verb — works on both Exotel and Airtel IQ.
    The action URL differs by provider so Airtel IQ gather goes to /airtel/gather/.
    """
    content = ""
    if play_url:
        content = f"  <Play>{play_url}</Play>"
    elif say_text:
        content = f'  <Say language="hi-IN" voice="female">{_xml_safe(say_text[:800])}</Say>'

    gather_paths = {"airtel_iq": "/airtel/gather/", "plivo": "/plivo/gather/"}
    gather_path = gather_paths.get(provider, "/call/gather/")

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
{content}
  <Record action="{config.PUBLIC_URL}{gather_path}{call_sid}"
          method="POST"
          maxLength="15"
          timeout="5"
          playBeep="false"
          finishOnKey="#">
  </Record>
</Response>"""


def _save_audio(audio_bytes: bytes, prefix: str, call_sid: str) -> str:
    """
    Save audio bytes with the correct file extension based on format.
    Returns the public URL for Exotel <Play>.

    CRITICAL: Sarvam TTS returns WAV — must be saved as .wav and served as audio/wav.
    Saving WAV bytes as .mp3 causes Exotel to get corrupt audio → call drops.
    """
    ext, _ = audio_fmt(audio_bytes)
    path = UPLOAD_DIR / f"{prefix}_{call_sid}.{ext}"
    path.write_bytes(audio_bytes)
    return f"{config.PUBLIC_URL}/call/audio/{prefix}/{call_sid}"


def _cleanup_audio(call_sid: str):
    """Delete all audio files for a call (both .wav and .mp3 variants)."""
    for prefix in ["opening", "response"]:
        for ext in ["mp3", "wav"]:
            f = UPLOAD_DIR / f"{prefix}_{call_sid}.{ext}"
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass


def _serve_audio(prefix: str, call_sid: str) -> Response:
    """Find and serve audio file in either WAV or MP3 format."""
    for ext, mime in [("wav", "audio/wav"), ("mp3", "audio/mpeg")]:
        path = UPLOAD_DIR / f"{prefix}_{call_sid}.{ext}"
        if path.exists():
            return Response(content=path.read_bytes(), media_type=mime)
    return Response(status_code=404)


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
        print(f"[Audio] Downloaded {len(r.content)} bytes from Exotel")
        return r.content
    except Exception as e:
        print(f"[Audio] Download failed: {e}")
        return b""


async def _run(fn, *args, timeout: float = 12.0):
    """
    Run a blocking function in the thread pool with a timeout.
    Essential: keeps Exotel webhook response time under ~8s.
    Returns None on timeout or exception.
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


# ── EXOTEL WEBHOOKS ────────────────────────────────────────────────────────────

async def _get_params(request: Request) -> dict:
    """Merge GET query params + POST form body. Exotel may use either."""
    data = dict(request.query_params)
    try:
        form = await request.form()
        data.update({k: v for k, v in form.items()})
    except Exception:
        pass
    return data


@app.api_route("/call/incoming", methods=["GET", "POST"])
async def incoming_call(request: Request):
    """
    Exotel hits this when someone calls your Exophone.
    MUST respond within 8-10 seconds or Exotel disconnects.

    Flow: Start session → generate greeting TTS audio → return ExoML <Play> + <Record>
    """
    data     = await _get_params(request)
    call_sid = data.get("CallSid", "").strip()
    caller   = data.get("From", data.get("CallFrom", "")).strip()

    print(f"\n[Incoming] Call from {caller} | SID: {call_sid}")

    if not call_sid:
        return Response(content=_hangup_xml(), media_type="application/xml")

    start_call_session(call_sid, caller)

    session  = active_calls.get(call_sid)
    lead     = session.get("lead") if session else None
    greeting = get_opening_message(lead, is_inbound=True)

    # Log opening in conversation history so AI has context for first reply
    if session:
        session["conversation"].history.append({"role": "assistant", "content": greeting})

    print(f"[Incoming] Greeting → Say: {greeting[:80]}")
    return Response(
        content=_record_xml(call_sid, say_text=greeting),
        media_type="application/xml"
    )


@app.api_route("/call/handler", methods=["GET", "POST"])
async def outbound_call_handler(request: Request):
    """
    Exotel hits this when our outbound call connects.
    Same flow as incoming — greet + record.
    """
    data     = await _get_params(request)
    call_sid = data.get("CallSid", "").strip()
    called   = data.get("To", data.get("CallTo", "")).strip()
    lead_id  = data.get("CustomField", "").strip()

    print(f"\n[Outbound] Call to {called} | SID: {call_sid} | Lead: {lead_id}")

    if not call_sid:
        return Response(content=_hangup_xml(), media_type="application/xml")

    if call_sid not in active_calls:
        start_call_session(call_sid, called, lead_id=lead_id)

    session  = active_calls.get(call_sid)
    lead     = session.get("lead") if session else None
    greeting = get_opening_message(lead, is_inbound=False)

    # Log opening in conversation history so AI has context for first reply
    if session:
        session["conversation"].history.append({"role": "assistant", "content": greeting})

    print(f"[Outbound] Greeting → Say: {greeting[:80]}")
    return Response(
        content=_record_xml(call_sid, say_text=greeting),
        media_type="application/xml"
    )


@app.post("/call/gather/{call_sid}")
async def handle_gather(call_sid: str, request: Request):
    """
    Exotel POSTs here after <Record> captures customer speech.

    Steps:
    1. Download recording from Exotel (requires auth)
    2. Transcribe with Sarvam STT
    3. Get AI response from GPT-4o
    4. Generate TTS audio (Sarvam → WAV, or ElevenLabs → MP3)
    5. Save with correct extension, return ExoML <Play> + <Record>
    """
    data = await _get_params(request)

    recording_url = data.get("RecordingUrl", "").strip()
    speech_result = data.get("SpeechResult", "").strip()
    digits        = data.get("Digits", "").strip()

    print(f"[Gather] [{call_sid}] RecordingUrl={'yes' if recording_url else 'no'} "
          f"SpeechResult='{speech_result[:60]}' Digits='{digits}'")

    session = active_calls.get(call_sid)
    if not session:
        print(f"[Gather] [{call_sid}] No session — hanging up")
        return Response(content=_hangup_xml(), media_type="application/xml")

    # ── Transcribe customer input ─────────────────────────────────────────────
    customer_input = speech_result or digits

    if not customer_input and recording_url:
        audio_bytes = await _run(_download_recording, recording_url, timeout=6.0)
        if audio_bytes:
            stt_result = await _run(transcribe_audio, audio_bytes, "hi-IN", timeout=5.0)
            if stt_result:
                customer_input = stt_result.get("text", "").strip()
                detected_lang  = stt_result.get("language", "hinglish")
                print(f"[Gather] [{call_sid}] STT: '{customer_input[:120]}' ({detected_lang})")
                if customer_input:
                    session["language"] = detected_lang

    # ── Handle silence / no input ─────────────────────────────────────────────
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
            media_type="application/xml"
        )

    session["silence_count"] = 0
    session["turn_count"] = session.get("turn_count", 0) + 1
    print(f"[Gather] [{call_sid}] Customer (turn {session['turn_count']}): '{customer_input[:120]}'")

    # ── Get AI response (Groq primary, OpenAI fallback) ──────────────────────
    # Groq responds in 0.3-0.8s; OpenAI GPT-4o takes 3-5s.
    # Timeout of 5s is generous for Groq, safety net for OpenAI fallback.
    conv       = session["conversation"]
    voice_text = None

    ai_reply = await _run(conv.chat, customer_input, timeout=5.0)
    if ai_reply:
        # Strip JSON analysis blocks — those are for internal use only
        voice_text = re.sub(r'\{[\s\S]*?\}', '', ai_reply).strip()

    if not voice_text:
        voice_text = "Ji, main samajh rahi hoon. Kya aap thoda aur detail de sakte hain?"

    print(f"[Gather] [{call_sid}] Priya: {voice_text[:120]}")

    # ── Detect language for TTS ───────────────────────────────────────────────
    devanagari_count = sum(1 for c in customer_input if '\u0900' <= c <= '\u097F')
    if devanagari_count > len(customer_input) * 0.3:
        lang = "hindi"
    else:
        lang = session.get("language", "hinglish")
    session["language"] = lang

    # ── Generate TTS audio ─────────────────────────────────────────────────────
    # CRITICAL: audio_fmt() detects WAV vs MP3 — saved with correct extension
    audio_url = None
    # timeout=9s: must be > Sarvam's internal API timeout (8s).
    # With Groq AI now responding in 0.3-0.8s (vs GPT-4o's 3-5s),
    # total gather latency is now ~5-7s — within Exotel's 8-10s window.
    ai_audio  = await _run(synthesize_speech, voice_text, lang, timeout=9.0)
    if ai_audio:
        audio_url = _save_audio(ai_audio, "response", call_sid)
        ext, _ = audio_fmt(ai_audio)
        print(f"[Gather] [{call_sid}] TTS audio saved as .{ext} — URL: {audio_url}")

    # ── Return ExoML ──────────────────────────────────────────────────────────
    if audio_url:
        return Response(
            content=_record_xml(call_sid, play_url=audio_url),
            media_type="application/xml"
        )
    else:
        # Fallback: Exotel built-in TTS
        print(f"[Gather] [{call_sid}] TTS unavailable — using Say fallback")
        return Response(
            content=_record_xml(call_sid, say_text=voice_text),
            media_type="application/xml"
        )


@app.api_route("/call/status", methods=["GET", "POST"])
async def call_status(request: Request, background_tasks: BackgroundTasks):
    """
    Exotel hits this when call ends.
    Analyse conversation and update lead in background.
    """
    data     = await _get_params(request)
    call_sid = data.get("CallSid", "")
    status   = data.get("Status", "")
    duration = int(data.get("Duration", 0))

    print(f"\n[Status] Call {call_sid} ended | Status: {status} | Duration: {duration}s")

    background_tasks.add_task(end_call_session, call_sid, duration)
    _cleanup_audio(call_sid)

    return JSONResponse({"received": True})


# ── AUDIO FILE SERVING ─────────────────────────────────────────────────────────
# Exotel <Play> downloads audio from these URLs.
# We detect format automatically (WAV from Sarvam, MP3 from ElevenLabs).

@app.get("/call/audio/opening/{call_sid}")
async def serve_opening_audio(call_sid: str):
    resp = _serve_audio("opening", call_sid)
    if resp.status_code == 404:
        # Try to regenerate if session still active
        audio = await _run(get_opening_audio, call_sid, timeout=10.0)
        if audio:
            _save_audio(audio, "opening", call_sid)
            return _serve_audio("opening", call_sid)
    return resp


@app.get("/call/audio/response/{call_sid}")
async def serve_response_audio(call_sid: str):
    return _serve_audio("response", call_sid)


# ── ADMIN API ──────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
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
    data    = await request.json()
    lead_id = db.add_lead(data)
    return JSONResponse({"success": True, "lead_id": lead_id})


@app.post("/api/leads/import")
async def import_leads(file: UploadFile = File(...)):
    """Import leads from CSV or Excel file — no pandas required."""
    content = await file.read()
    ext     = Path(file.filename).suffix.lower()

    try:
        if ext == ".csv":
            leads = _parse_csv_leads(content)
        elif ext in (".xlsx", ".xls"):
            leads = _parse_excel_leads(content)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

        # Normalize column names
        col_map = {
            "phone": "mobile", "contact": "mobile", "number": "mobile",
            "customer_name": "name", "customer": "name",
            "model": "interested_model", "bike": "interested_model",
        }
        normalized = []
        for row in leads:
            normalized_row = {col_map.get(k, k): v for k, v in row.items() if v}
            normalized.append(normalized_row)

        ids = add_leads_from_import(normalized)
        return JSONResponse({
            "success": True,
            "imported": len(ids),
            "skipped": len(normalized) - len(ids)
        })
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def _parse_csv_leads(content: bytes) -> list:
    """Parse CSV file into list of dicts using built-in csv module."""
    text   = content.decode("utf-8-sig")  # Handle BOM
    reader = csv.DictReader(io.StringIO(text))
    rows   = []
    for row in reader:
        clean = {k.lower().strip().replace(" ", "_"): str(v).strip() for k, v in row.items() if v}
        rows.append(clean)
    return rows


def _parse_excel_leads(content: bytes) -> list:
    """Parse Excel file into list of dicts using openpyxl."""
    import openpyxl
    wb   = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws   = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []
    headers = [
        str(h).lower().strip().replace(" ", "_") if h is not None else f"col_{i}"
        for i, h in enumerate(rows[0])
    ]
    result = []
    for row in rows[1:]:
        record = {}
        for i, val in enumerate(row):
            if val is not None and str(val).strip():
                record[headers[i]] = str(val).strip()
        if record:
            result.append(record)
    wb.close()
    return result


def _make_outbound_call(to_number: str, lead_id: str = "") -> dict:
    """Route call through configured telephony provider."""
    if config.TELEPHONY_PROVIDER == "plivo":
        return _plivo.make_outbound_call(to_number, lead_id)
    if config.TELEPHONY_PROVIDER == "airtel_iq":
        return _airtel_iq.make_outbound_call(to_number, lead_id)
    return _exotel_make_call(to_number, lead_id)


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
    background_tasks.add_task(_make_outbound_call, mobile, lead_id)
    return JSONResponse({"success": True, "message": f"Calling {mobile}... (via {config.TELEPHONY_PROVIDER})"})


# ── AIRTEL IQ WEBHOOKS ──────────────────────────────────────────────────────────
# Set TELEPHONY_PROVIDER=airtel_iq in .env to use these instead of Exotel.
# Airtel IQ sends different parameter names than Exotel but the call flow is the same.
# Set your Airtel IQ dashboard callback URLs to:
#   Inbound:  {PUBLIC_URL}/airtel/incoming
#   Handler:  {PUBLIC_URL}/airtel/handler
#   Gather:   {PUBLIC_URL}/airtel/gather/{call_sid}
#   Status:   {PUBLIC_URL}/airtel/status

@app.api_route("/airtel/incoming", methods=["GET", "POST"])
async def airtel_incoming(request: Request):
    """
    Airtel IQ hits this for inbound calls.
    Parameter names differ from Exotel: CallId vs CallSid, CallerNumber vs From.
    Returns same ExoML/TwiML XML — Airtel IQ supports standard XML call control.
    """
    data     = await _get_params(request)
    # Airtel IQ uses CallId or callId
    call_sid = (data.get("CallId") or data.get("callId") or data.get("CallSid", "")).strip()
    caller   = (data.get("CallerNumber") or data.get("callerNumber") or
                data.get("From", "")).strip()

    print(f"\n[AirtelIQ Incoming] Call from {caller} | CallId: {call_sid}")

    if not call_sid:
        return Response(content=_hangup_xml(), media_type="application/xml")

    start_call_session(call_sid, caller)
    session  = active_calls.get(call_sid)
    lead     = session.get("lead") if session else None
    greeting = get_opening_message(lead, is_inbound=True)

    if session:
        session["conversation"].history.append({"role": "assistant", "content": greeting})

    return Response(
        content=_record_xml(call_sid, say_text=greeting, provider="airtel_iq"),
        media_type="application/xml"
    )


@app.api_route("/airtel/handler", methods=["GET", "POST"])
async def airtel_outbound_handler(request: Request):
    """Airtel IQ hits this when our outbound call connects."""
    data     = await _get_params(request)
    call_sid = (data.get("CallId") or data.get("callId") or data.get("CallSid", "")).strip()
    called   = (data.get("CalledNumber") or data.get("calledNumber") or
                data.get("To", "")).strip()
    lead_id  = (data.get("customData") or data.get("CustomField", "")).strip()

    print(f"\n[AirtelIQ Outbound] Call to {called} | CallId: {call_sid} | Lead: {lead_id}")

    if not call_sid:
        return Response(content=_hangup_xml(), media_type="application/xml")

    if call_sid not in active_calls:
        start_call_session(call_sid, called, lead_id=lead_id)

    session  = active_calls.get(call_sid)
    lead     = session.get("lead") if session else None
    greeting = get_opening_message(lead, is_inbound=False)

    if session:
        session["conversation"].history.append({"role": "assistant", "content": greeting})

    return Response(
        content=_record_xml(call_sid, say_text=greeting, provider="airtel_iq"),
        media_type="application/xml"
    )


@app.post("/airtel/gather/{call_sid}")
async def airtel_gather(call_sid: str, request: Request):
    """
    Airtel IQ posts here after recording ends.
    Same logic as Exotel gather — just different parameter names.
    RecordingUrl → recordingUrl, SpeechResult → speechResult, etc.
    """
    data = await _get_params(request)

    # Airtel IQ uses camelCase, Exotel uses PascalCase — handle both
    recording_url = (data.get("RecordingUrl") or data.get("recordingUrl") or "").strip()
    speech_result = (data.get("SpeechResult") or data.get("speechResult") or "").strip()
    digits        = (data.get("Digits") or data.get("digits") or "").strip()

    print(f"[AirtelIQ Gather] [{call_sid}] RecordingUrl={'yes' if recording_url else 'no'}")

    session = active_calls.get(call_sid)
    if not session:
        return Response(content=_hangup_xml(), media_type="application/xml")

    customer_input = speech_result or digits

    if not customer_input and recording_url:
        audio_bytes = await _run(_download_recording, recording_url, timeout=6.0)
        if audio_bytes:
            stt_result = await _run(transcribe_audio, audio_bytes, "hi-IN", timeout=5.0)
            if stt_result:
                customer_input = stt_result.get("text", "").strip()
                detected_lang  = stt_result.get("language", "hinglish")
                if customer_input:
                    session["language"] = detected_lang

    if not customer_input:
        silence_count = session.get("silence_count", 0) + 1
        session["silence_count"] = silence_count
        if silence_count >= 3:
            return Response(content=_hangup_xml(), media_type="application/xml")
        retry_text = "Ji? Kuch clearly suna nahi — thoda louder bol sakte hain?"
        return Response(
            content=_record_xml(call_sid, say_text=retry_text, provider="airtel_iq"),
            media_type="application/xml"
        )

    session["silence_count"] = 0
    session["turn_count"] = session.get("turn_count", 0) + 1

    conv       = session["conversation"]
    ai_reply   = await _run(conv.chat, customer_input, timeout=5.0)
    voice_text = re.sub(r'\{[\s\S]*?\}', '', ai_reply or "").strip()
    if not voice_text:
        voice_text = "Ji, main samajh rahi hoon. Kya aap thoda aur detail de sakte hain?"

    devanagari_count = sum(1 for c in customer_input if '\u0900' <= c <= '\u097F')
    lang = "hindi" if devanagari_count > len(customer_input) * 0.3 else session.get("language", "hinglish")
    session["language"] = lang

    audio_url = None
    ai_audio  = await _run(synthesize_speech, voice_text, lang, timeout=9.0)
    if ai_audio:
        audio_url = _save_audio(ai_audio, "response", call_sid)

    if audio_url:
        return Response(
            content=_record_xml(call_sid, play_url=audio_url, provider="airtel_iq"),
            media_type="application/xml"
        )
    return Response(
        content=_record_xml(call_sid, say_text=voice_text, provider="airtel_iq"),
        media_type="application/xml"
    )


@app.api_route("/airtel/status", methods=["GET", "POST"])
async def airtel_status(request: Request, background_tasks: BackgroundTasks):
    """Airtel IQ call-ended callback."""
    data     = await _get_params(request)
    call_sid = (data.get("CallId") or data.get("callId") or data.get("CallSid", ""))
    status   = (data.get("status") or data.get("Status", ""))
    duration = int(data.get("duration") or data.get("Duration") or 0)

    print(f"\n[AirtelIQ Status] Call {call_sid} ended | Status: {status} | Duration: {duration}s")

    background_tasks.add_task(end_call_session, call_sid, duration)
    _cleanup_audio(call_sid)
    return JSONResponse({"received": True})


# ── PLIVO WEBHOOKS ────────────────────────────────────────────────────────────
# Set TELEPHONY_PROVIDER=plivo in .env to use Plivo.
# In Plivo console → your number → set Answer URL and Hangup URL.
#
# Plivo parameter differences from Exotel:
#   Exotel CallSid     → Plivo CallUUID
#   Exotel RecordingUrl → Plivo RecordUrl
#   No CustomField (lead_id passed as query param in answer_url instead)

@app.api_route("/plivo/incoming", methods=["GET", "POST"])
async def plivo_incoming(request: Request):
    """
    Plivo calls this when a customer calls your Plivo DID number.
    Set this as the Answer URL in Plivo console for inbound calls.
    """
    data     = await _get_params(request)
    call_sid = data.get("CallUUID", data.get("CallSid", "")).strip()
    caller   = data.get("From", "").strip()

    print(f"\n[Plivo Incoming] Call from {caller} | UUID: {call_sid}")

    if not call_sid:
        return Response(content=_hangup_xml(), media_type="application/xml")

    start_call_session(call_sid, caller)
    session  = active_calls.get(call_sid)
    lead     = session.get("lead") if session else None
    greeting = get_opening_message(lead, is_inbound=True)

    if session:
        session["conversation"].history.append({"role": "assistant", "content": greeting})

    return Response(
        content=_record_xml(call_sid, say_text=greeting, provider="plivo"),
        media_type="application/xml"
    )


@app.api_route("/plivo/handler", methods=["GET", "POST"])
async def plivo_outbound_handler(request: Request):
    """
    Plivo calls this when an outbound call connects (answer_url).
    lead_id is passed as a query param in the answer_url we set when making the call.
    """
    data     = await _get_params(request)
    call_sid = data.get("CallUUID", data.get("CallSid", "")).strip()
    called   = data.get("To", "").strip()
    lead_id  = data.get("lead_id", "").strip()  # from query param in answer_url

    print(f"\n[Plivo Outbound] Call to {called} | UUID: {call_sid} | Lead: {lead_id}")

    if not call_sid:
        return Response(content=_hangup_xml(), media_type="application/xml")

    if call_sid not in active_calls:
        start_call_session(call_sid, called, lead_id=lead_id)

    session  = active_calls.get(call_sid)
    lead     = session.get("lead") if session else None
    greeting = get_opening_message(lead, is_inbound=False)

    if session:
        session["conversation"].history.append({"role": "assistant", "content": greeting})

    return Response(
        content=_record_xml(call_sid, say_text=greeting, provider="plivo"),
        media_type="application/xml"
    )


@app.post("/plivo/gather/{call_sid}")
async def plivo_gather(call_sid: str, request: Request):
    """
    Plivo posts here after <Record> finishes capturing customer speech.
    Key difference from Exotel: recording URL param is 'RecordUrl' not 'RecordingUrl'.
    """
    data = await _get_params(request)

    # Plivo uses RecordUrl; also accept RecordingUrl as fallback
    recording_url = (data.get("RecordUrl") or data.get("RecordingUrl") or "").strip()
    digits        = data.get("Digits", "").strip()

    print(f"[Plivo Gather] [{call_sid}] Recording={'yes' if recording_url else 'no'}")

    session = active_calls.get(call_sid)
    if not session:
        return Response(content=_hangup_xml(), media_type="application/xml")

    customer_input = digits

    if not customer_input and recording_url:
        audio_bytes = await _run(_download_recording, recording_url, timeout=6.0)
        if audio_bytes:
            stt_result = await _run(transcribe_audio, audio_bytes, "hi-IN", timeout=5.0)
            if stt_result:
                customer_input = stt_result.get("text", "").strip()
                if customer_input:
                    session["language"] = stt_result.get("language", "hinglish")

    if not customer_input:
        silence_count = session.get("silence_count", 0) + 1
        session["silence_count"] = silence_count
        if silence_count >= 3:
            return Response(content=_hangup_xml(), media_type="application/xml")
        retry_text = "Ji? Kuch clearly suna nahi — thoda louder bol sakte hain?"
        return Response(
            content=_record_xml(call_sid, say_text=retry_text, provider="plivo"),
            media_type="application/xml"
        )

    session["silence_count"] = 0
    session["turn_count"] = session.get("turn_count", 0) + 1

    conv     = session["conversation"]
    ai_reply = await _run(conv.chat, customer_input, timeout=5.0)
    voice_text = re.sub(r'\{[\s\S]*?\}', '', ai_reply or "").strip()
    if not voice_text:
        voice_text = "Ji, main samajh rahi hoon. Kya aap thoda aur detail de sakte hain?"

    print(f"[Plivo Gather] [{call_sid}] Priya: {voice_text[:120]}")

    devanagari_count = sum(1 for c in customer_input if '\u0900' <= c <= '\u097F')
    lang = "hindi" if devanagari_count > len(customer_input) * 0.3 else session.get("language", "hinglish")
    session["language"] = lang

    audio_url = None
    ai_audio  = await _run(synthesize_speech, voice_text, lang, timeout=9.0)
    if ai_audio:
        audio_url = _save_audio(ai_audio, "response", call_sid)

    if audio_url:
        return Response(
            content=_record_xml(call_sid, play_url=audio_url, provider="plivo"),
            media_type="application/xml"
        )
    return Response(
        content=_record_xml(call_sid, say_text=voice_text, provider="plivo"),
        media_type="application/xml"
    )


@app.api_route("/plivo/status", methods=["GET", "POST"])
async def plivo_status(request: Request, background_tasks: BackgroundTasks):
    """Plivo calls this when the call ends (hangup_url)."""
    data     = await _get_params(request)
    call_sid = data.get("CallUUID", data.get("CallSid", ""))
    status   = data.get("CallStatus", data.get("Status", ""))
    duration = int(data.get("Duration") or data.get("BillDuration") or 0)

    print(f"\n[Plivo Status] Call {call_sid} ended | Status: {status} | Duration: {duration}s")

    background_tasks.add_task(end_call_session, call_sid, duration)
    _cleanup_audio(call_sid)
    return JSONResponse({"received": True})


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


# ── DASHBOARD HTML ─────────────────────────────────────────────────────────────

def _render_dashboard(stats: dict, leads: list) -> str:
    badge = {
        "hot": "🔥", "warm": "🟡", "cold": "❄️",
        "dead": "☠️", "converted": "✅", "new": "🆕", "active": "📞"
    }
    rows = ""
    for l in leads:
        s  = l.get("status", "new")
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
</script>
</body>
</html>"""


# ── ENTRY POINT ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=config.PORT, reload=False)
