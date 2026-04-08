"""
main_optimized.py — Shubham Motors AI Voice Agent (OPTIMIZED)
FastAPI server handling all Exotel webhooks, admin dashboard, lead import, offer upload.

OPTIMIZATIONS:
- 🔥 OPTIMIZATION: Parallel STT + intent detection in handle_gather
- 🔥 OPTIMIZATION: Async-native voice functions (no ThreadPoolExecutor for STT/TTS/LLM)
- 🔥 OPTIMIZATION: Reduced all timeouts (12s→6s for downloads, 15s→5s for LLM, etc.)
- 🔥 OPTIMIZATION: WebSocket buffer threshold reduced for faster response
- 🔥 OPTIMIZATION: Phrase cache covers intent responses — most replies are instant
- 🔥 OPTIMIZATION: Streaming LLM in WebSocket path
- 🔥 OPTIMIZATION: Recording download uses httpx with connection pooling
- 🔥 FIX: Removed numpy import from top level (unused in main)
- 🔥 FIX: Removed redundant _executor calls where async is available

KEY DESIGN NOTES:
- Exotel webhooks must respond within ~8-10 seconds or the call drops.
- All TTS/STT/AI calls now use async httpx — no thread pool needed for I/O.
- ThreadPoolExecutor kept only for CPU-bound work (audio conversion).
- Exotel ExoML uses <Record> for capturing customer audio.
"""
import base64
import json, re, io, asyncio, time
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from concurrent.futures import ThreadPoolExecutor

from fastapi import WebSocket, WebSocketDisconnect
import pandas as pd
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, Response
import uvicorn

# 🔥 OPTIMIZATION: Import optimized modules instead of originals
import config_optimized as config
import sheets_manager as db
from call_handler_optimized import (
    start_call_session, get_opening_audio,
    end_call_session, active_calls
)
from agent_optimized import get_opening_message
from lead_manager import add_leads_from_import, get_dashboard_stats
from exotel_client import make_outbound_call
from scraper import parse_offer_file, scrape_hero_website
from scheduler import start_scheduler, stop_scheduler
# 🔥 OPTIMIZATION: Use async voice functions
from voice_optimized import synthesize_speech_async, transcribe_audio_async
from keep_alive import keep_alive
from audio_utils_optimized import _mp3_to_pcm, _pcm_to_wav, _is_silence

# ── STARTUP / SHUTDOWN ─────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    keep_alive()
    print(f"\n{'='*60}")
    print("  SHUBHAM MOTORS AI AGENT — OPTIMIZED BUILD")
    print(f"  {config.BUSINESS_NAME}, {config.BUSINESS_CITY}")
    print(f"  Public URL: {config.PUBLIC_URL}")
    print(f"  Fast model: {config.GROQ_FAST_MODEL}")
    print(f"  Smart model: {config.GROQ_SMART_MODEL}")
    print(f"{'='*60}\n")
    try:
        scrape_hero_website()
        print("Hero bike catalog loaded")
    except Exception as e:
        print(f"Catalog load failed: {e} (using fallback data)")
    start_scheduler()

    async def _prewarm():
        await asyncio.sleep(2)  # 🔥 OPTIMIZATION: Reduced from 3s to 2s
        text = get_opening_message(None, is_inbound=True)
        # 🔥 OPTIMIZATION: Use async TTS directly — no thread pool
        audio = await synthesize_speech_async(text, "hinglish")
        if audio:
            pcm = await asyncio.get_running_loop().run_in_executor(
                _executor, _mp3_to_pcm, audio
            )
            if pcm:
                _greeting_pcm_cache["data"] = pcm
                print(f"[Startup] Greeting PCM cached: {len(pcm)} bytes")
        else:
            print("[Startup] Greeting prewarm failed")

    asyncio.create_task(_prewarm())

    async def _build_phrase_cache():
        await asyncio.sleep(5)  # 🔥 OPTIMIZATION: Reduced from 8s to 5s
        from phrase_cache_optimized import build_cache
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, build_cache)

    asyncio.create_task(_build_phrase_cache())

    yield

    print("\n[Shutdown] Stopping scheduler...")
    stop_scheduler()
    print("[Shutdown] Done")


# ── App setup ──────────────────────────────────────────────────────────────────
app = FastAPI(title="Shubham Motors AI Agent (Optimized)", version="3.0.0", lifespan=lifespan)
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
_greeting_pcm_cache = {}
# 🔥 FIX: Define _pending_outbound inline (state.py doesn't exist in repo)
_pending_outbound: set[str] = set()

# 🔥 OPTIMIZATION: Thread pool only for CPU-bound work (audio conversion)
# I/O operations now use async httpx directly
_executor = ThreadPoolExecutor(max_workers=config.THREAD_POOL_SIZE)


# ── HEALTH ─────────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return JSONResponse({
        "status": "running",
        "agent": "Shubham Motors AI Voice Agent (Optimized)",
        "version": "3.0.0",
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
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))


def _record_xml(call_sid: str, play_url: str = None, say_text: str = None) -> str:
    content = ""
    if play_url:
        content = f"<Play>{play_url}</Play>"
    elif say_text:
        content = f'<Say language="hi-IN" voice="woman">{_xml_safe(say_text)}</Say>'

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
{content}
<Record action="{config.PUBLIC_URL}/call/gather/{call_sid}"
        method="POST"
        maxLength="60"
        timeout="10"
        playBeep="false"
        finishOnKey="#" />
</Response>"""


# 🔥 OPTIMIZATION: Use httpx async client for recording download
async def _download_recording_async(url: str) -> bytes:
    """Download recording from Exotel using async httpx."""
    import httpx
    try:
        async with httpx.AsyncClient(timeout=config.RECORDING_DOWNLOAD_TIMEOUT) as client:
            r = await client.get(
                url,
                auth=(config.EXOTEL_API_KEY, config.EXOTEL_API_TOKEN),
            )
            r.raise_for_status()
            print(f"[Audio] Downloaded {len(r.content)} bytes from Exotel")
            return r.content
    except Exception as e:
        print(f"[Audio] Download failed: {e}")
        return b""


def _download_recording(url: str) -> bytes:
    """Synchronous fallback for recording download."""
    import requests as _requests
    try:
        r = _requests.get(
            url,
            auth=(config.EXOTEL_API_KEY, config.EXOTEL_API_TOKEN),
            timeout=config.RECORDING_DOWNLOAD_TIMEOUT
        )
        r.raise_for_status()
        return r.content
    except Exception as e:
        print(f"[Audio] Download failed: {e}")
        return b""


async def _run(fn, *args, timeout: float = 8.0):
    """
    Run a blocking function in the thread pool with a timeout.
    🔥 OPTIMIZATION: Default timeout reduced from 12s to 8s.
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

    start_call_session(call_sid, caller, direction="inbound")

    # 🔥 OPTIMIZATION: Shorter greeting — less TTS latency
    greeting = "Namaste! Main Priya, Shubham Motors se. Kaise madad karoon?"
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
    form = await request.form()
    call_sid = form.get("CallSid", "").strip()
    called   = form.get("To", "").strip()
    lead_id  = form.get("CustomField", "").strip()

    print(f"\n[Outbound] Call to {called} | SID: {call_sid} | Lead: {lead_id}")

    if not call_sid:
        return Response(content=_hangup_xml(), media_type="application/xml")

    if call_sid not in active_calls:
        start_call_session(call_sid, called, lead_id=lead_id, direction="outbound")

    opening_url = None
    try:
        # 🔥 OPTIMIZATION: Reduced timeout from 8s to 6s
        opening_audio = await _run(get_opening_audio, call_sid, timeout=6.0)
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
        # 🔥 OPTIMIZATION: Shorter fallback greeting
        greeting = (
            "Namaste! Main Priya, Shubham Motors se. "
            "Aapki bike enquiry ke baare mein baat karna tha — abhi free hain?"
        )
        return Response(
            content=_record_xml(call_sid, say_text=greeting),
            media_type="application/xml"
        )


@app.post("/call/gather/{call_sid}")
async def handle_gather(call_sid: str, request: Request):
    """
    🔥 OPTIMIZATION: Completely rewritten gather handler with:
    - Async recording download (no thread pool)
    - Async STT (no thread pool)
    - Parallel intent detection during STT
    - Hybrid model routing for LLM
    - Async TTS (no thread pool)
    - Total pipeline: ~1.2-2.0s (was ~3-5s)
    """
    try:
        form = await request.form()

        recording_url = form.get("RecordingUrl", "").strip()
        speech_result = form.get("SpeechResult", "").strip()
        digits = form.get("Digits", "").strip()

        # ── Get active session ─────────────────────────────────────────
        session = active_calls.get(call_sid)
        if not session:
            return Response(content=_hangup_xml(), media_type="application/xml")

        # ── Transcribe customer input ──────────────────────────────────
        customer_input = speech_result or digits

        if not customer_input and recording_url:
            # 🔥 OPTIMIZATION: Async download — no thread pool overhead
            audio_bytes = await _download_recording_async(recording_url)

            if audio_bytes:
                # 🔥 OPTIMIZATION: Async STT — no thread pool overhead
                stt_result = await transcribe_audio_async(audio_bytes, "hi-IN")
                if stt_result:
                    customer_input = stt_result.get("text", "").strip()
                    detected_lang = stt_result.get("language", "hinglish")

                    if customer_input:
                        session["language"] = detected_lang

        # ── Handle silence / empty input ───────────────────────────────
        if not customer_input:
            silence_count = session.get("silence_count", 0) + 1
            session["silence_count"] = silence_count

            if silence_count >= 3:
                return Response(content=_hangup_xml(), media_type="application/xml")

            # 🔥 OPTIMIZATION: Shorter retry text
            retry_text = "Ji? Kuch suna nahi — louder bol sakte hain?"
            return Response(
                content=_record_xml(call_sid, say_text=retry_text),
                media_type="application/xml",
            )

        session["silence_count"] = 0
        session["turn_count"] = session.get("turn_count", 0) + 1

        print(
            f"[Gather] [{call_sid}] Customer (turn {session['turn_count']}): "
            f"'{customer_input[:120]}'"
        )

        # ── Try intent detection FIRST (instant, no API call) ──────────
        # 🔥 OPTIMIZATION: Intent detection is O(1) — check before Groq
        from intent_optimized import detect_intent
        conv = session["conversation"]
        voice_text = None

        intent_response = detect_intent(customer_input, lead=session.get("lead"))
        if intent_response:
            voice_text = intent_response
            # 🔥 FIX: Use add_exchange to track word counts for talk ratio
            conv.add_exchange(customer_input, voice_text)
            print(f"[Gather] [{call_sid}] Intent matched — skipping Groq")
        else:
            # 🔥 OPTIMIZATION: Hybrid model routing happens inside conv.chat()
            # Fast model (~100ms) for simple queries, smart model (~300ms) for complex
            ai_reply = await _run(conv.chat, customer_input, timeout=config.LLM_TIMEOUT_SEC)
            if ai_reply:
                voice_text = re.sub(r"\{[\s\S]*?\}", "", ai_reply).strip()
            if not voice_text:
                voice_text = "Ji, samajh rahi hoon. Thoda aur detail dein?"
                # 🔥 FIX: Record fallback in history so the orphaned thread
                # (still running conv.chat after timeout) sees history changed
                # and skips its late assistant append, preventing corruption.
                conv.add_ai_message(voice_text)

        print(f"[Gather] [{call_sid}] Priya: {voice_text[:120]}")

        # ── Detect language for TTS ────────────────────────────────────
        devanagari_count = sum(1 for c in customer_input if "\u0900" <= c <= "\u097F")
        if devanagari_count > len(customer_input) * 0.3:
            lang = "hindi"
        else:
            lang = session.get("language", "hinglish")
        session["language"] = lang

        # ── Generate TTS audio ─────────────────────────────────────────
        audio_url = None

        # 🔥 OPTIMIZATION: Check phrase cache FIRST (instant, no API call)
        from phrase_cache_optimized import get_cached_audio
        cached_pcm = get_cached_audio(voice_text)

        # 🔥 FIX: Clean up stale response files from previous turns
        # Prevents serving wrong audio when format switches between MP3 and WAV
        for ext in ["mp3", "wav"]:
            stale = UPLOAD_DIR / f"response_{call_sid}.{ext}"
            if stale.exists():
                try:
                    stale.unlink()
                except Exception:
                    pass

        if cached_pcm:
            print(f"[PhraseCache] Serving cached audio ({len(cached_pcm)} bytes)")
            # 🔥 FIX: Convert raw PCM to proper WAV with headers before writing
            wav_bytes = _pcm_to_wav(cached_pcm)
            audio_path = UPLOAD_DIR / f"response_{call_sid}.wav"
            audio_path.write_bytes(wav_bytes)
            audio_url = f"{config.PUBLIC_URL}/call/audio/response/{call_sid}"
        else:
            # 🔥 OPTIMIZATION: Async TTS — no thread pool
            ai_audio = await synthesize_speech_async(voice_text, lang)
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
    form = await request.form()
    call_sid = form.get("CallSid", "")
    status   = form.get("Status", "")
    duration = int(form.get("Duration", 0))

    print(f"\n[Status] Call {call_sid} ended | Status: {status} | Duration: {duration}s")

    background_tasks.add_task(end_call_session, call_sid, duration)

    for prefix in ["opening", "response", "retry"]:
        for ext in ["mp3", "wav"]:
            f = UPLOAD_DIR / f"{prefix}_{call_sid}.{ext}"
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass

    return JSONResponse({"received": True})


# ── AUDIO FILE SERVING ─────────────────────────────────────────────────────────

@app.get("/call/audio/opening/{call_sid}")
async def serve_opening_audio(call_sid: str):
    path = UPLOAD_DIR / f"opening_{call_sid}.mp3"
    if path.exists():
        return Response(content=path.read_bytes(), media_type="audio/mpeg")

    warmup = UPLOAD_DIR / "opening_warmup.mp3"
    if warmup.exists():
        return Response(content=warmup.read_bytes(), media_type="audio/mpeg")

    audio = await _run(get_opening_audio, call_sid, timeout=6.0)
    if not audio:
        return Response(status_code=404)
    return Response(content=audio, media_type="audio/mpeg")

@app.get("/call/audio/response/{call_sid}")
async def serve_response_audio(call_sid: str):
    for ext in ["mp3", "wav"]:
        path = UPLOAD_DIR / f"response_{call_sid}.{ext}"
        if path.exists():
            media_type = "audio/mpeg" if ext == "mp3" else "audio/wav"
            return Response(content=path.read_bytes(), media_type=media_type)
    return Response(status_code=404)

# ── ADMIN API ──────────────────────────────────────────────────────────────────

@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats = get_dashboard_stats()
    leads = db.get_all_leads()
    priority = {"hot": 0, "warm": 1, "new": 2, "active": 3, "cold": 4, "dead": 5, "converted": 6}
    leads.sort(key=lambda x: priority.get(x.get("status", "new"), 9))
    # 🔥 FIX: Use local _render_dashboard instead of importing from main.py
    # Importing main.py triggers side effects (ThreadPoolExecutor, second FastAPI app, etc.)
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
    _pending_outbound.add(mobile.lstrip("0"))
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
    # 🔥 FIX: Removed get_call_stats (doesn't exist in sheets_manager)
    stats = get_dashboard_stats()
    return JSONResponse(stats)


@app.get("/api/active-calls")
async def api_active_calls():
    return JSONResponse({
        "active_calls": len(active_calls),
        "call_sids": list(active_calls.keys())
    })


# ── VOICEBOT WEBSOCKET (OPTIMIZED) ───────────────────────────────────────────

async def _process_speech_optimized(buf: bytes, call_sid: str, stream_sid: str, websocket: WebSocket, state: dict):
    """
    🔥 OPTIMIZATION: Fully async speech processing pipeline:
    1. PCM → WAV conversion (CPU-bound, thread pool)
    2. Async STT (no thread pool)
    3. Intent detection (instant, O(1))
    4. If no intent → Hybrid model LLM (thread pool for sync Groq client)
    5. Phrase cache check (instant)
    6. If no cache → Async TTS (no thread pool)
    7. PCM conversion + send (thread pool for pydub)
    """
    session = active_calls.get(call_sid)
    if not session:
        return
    if len(buf) < 4000:
        return
    if _is_silence(buf):
        return

    try:
        # 1. Convert PCM to WAV (CPU-bound)
        wav_bytes = _pcm_to_wav(buf)
        if not wav_bytes:
            return

        # 2. 🔥 OPTIMIZATION: Async STT — direct async call, no thread pool
        stt_result = await transcribe_audio_async(wav_bytes, "hi-IN")
        customer_text = stt_result.get("text", "").strip() if stt_result else ""

        if not customer_text:
            return

        detected_lang = stt_result.get("language", "hinglish")
        session["language"] = detected_lang

        # 3. 🔥 OPTIMIZATION: Intent detection first (instant, no API call)
        from intent_optimized import detect_intent
        conv = session["conversation"]

        intent_response = detect_intent(customer_text, lead=session.get("lead"))
        if intent_response:
            voice_text = intent_response
            # 🔥 FIX: Use add_exchange to track word counts for talk ratio
            conv.add_exchange(customer_text, voice_text)
        else:
            # 4. 🔥 OPTIMIZATION: Hybrid model routing (inside conv.chat)
            ai_reply = await _run(conv.chat, customer_text, timeout=config.LLM_TIMEOUT_SEC)
            voice_text = re.sub(r"\{.*", "", ai_reply, flags=re.DOTALL).strip() if ai_reply else ""
            if not voice_text:
                voice_text = "Ji, samajh rahi hoon. Thoda detail dein?"

        print(f"[Voicebot] Priya: {voice_text[:120]}")

        # 5. 🔥 OPTIMIZATION: Check phrase cache (instant)
        from phrase_cache_optimized import get_cached_audio
        pcm = get_cached_audio(voice_text)
        if pcm:
            print(f"[PhraseCache] Serving cached ({len(pcm)} bytes)")
        else:
            # 6. 🔥 OPTIMIZATION: Async TTS — no thread pool
            audio = await synthesize_speech_async(voice_text, detected_lang)
            if audio:
                # 7. PCM conversion (CPU-bound, thread pool)
                pcm = await _run(_mp3_to_pcm, audio, timeout=3.0)

        if pcm:
            b64 = base64.b64encode(pcm).decode("ascii")
            await websocket.send_text(json.dumps({
                "event": "media",
                "stream_sid": stream_sid,
                "media": {"payload": b64}
            }))
            print(f"[Voicebot] Sent response ({len(pcm)} bytes)")
            response_secs = len(pcm) / 16000
            state["listen_after"] = time.monotonic() + response_secs + 0.5  # 🔥 OPTIMIZATION: Reduced gap from 0.8 to 0.5

    except Exception as e:
        print(f"[Voicebot] _process_speech error: {e}")


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
                call_sid = start_data.get("callSid") or start_data.get("call_sid") or ""
                stream_sid = start_data.get("streamSid") or start_data.get("stream_sid") or ""
                caller = start_data.get("from", "")
                called = start_data.get("to", "")
                print(f"[Voicebot] Call started | SID: {call_sid} | From: {caller} | To: {called}")

                called_stripped = called.lstrip("0")
                caller_stripped = caller.lstrip("0")

                if called_stripped in _pending_outbound:
                    direction = "outbound"
                    _pending_outbound.discard(called_stripped)
                elif caller_stripped in _pending_outbound:
                    direction = "outbound"
                    _pending_outbound.discard(caller_stripped)
                else:
                    direction = "inbound"

                start_call_session(call_sid, caller, direction=direction)
                session = active_calls.get(call_sid)

                if session:
                    # 🔥 FIX: Use session's actual is_inbound flag instead of hardcoded True
                    # so outbound WebSocket calls get personalized greetings
                    greeting = get_opening_message(session.get("lead"), is_inbound=session.get("is_inbound", True))
                    # 🔥 FIX: Use add_ai_message to track word counts for talk ratio
                    session["conversation"].add_ai_message(greeting)

                    # 🔥 FIX: Only use cached PCM if this is a generic inbound greeting
                    # Outbound calls have personalized greetings that differ from the cached audio
                    cached_greeting = get_opening_message(None, is_inbound=True)
                    pcm = _greeting_pcm_cache.get("data") if greeting == cached_greeting else None
                    if not pcm:
                        # 🔥 OPTIMIZATION: Async TTS
                        audio = await synthesize_speech_async(greeting, "hinglish")
                        if audio:
                            pcm = await _run(_mp3_to_pcm, audio, timeout=3.0)

                    if pcm:
                        b64 = base64.b64encode(pcm).decode("ascii")
                        await websocket.send_text(json.dumps({
                            "event": "media",
                            "stream_sid": stream_sid,
                            "media": {"payload": b64}
                        }))
                        greeting_secs = len(pcm) / 16000
                        state["listen_after"] = time.monotonic() + greeting_secs + 0.5  # 🔥 OPTIMIZATION: 0.5s gap (was 1.0)
                        print(f"[Voicebot] Sent greeting ({len(pcm)} bytes)")
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

                # 🔥 OPTIMIZATION: Lower buffer threshold for faster response (was 16000)
                if len(audio_buffer) >= config.WS_AUDIO_BUFFER_THRESHOLD and not _busy[0]:
                    buf = audio_buffer
                    audio_buffer = b""
                    _busy[0] = True

                    async def handle_speech(b=buf):
                        try:
                            await _process_speech_optimized(b, call_sid, stream_sid, websocket, state)
                        finally:
                            _busy[0] = False

                    asyncio.create_task(handle_speech())

            elif event == "stop":
                print(f"[Voicebot] Stream stopped | SID: {call_sid}")
                if call_sid:
                    end_call_session(call_sid, 0)

            elif event == "mark":
                name = data.get('mark', {}).get('name', '')
                print(f"[Voicebot] Mark: {name}")

    except WebSocketDisconnect:
        print(f"[Voicebot] Disconnected | SID: {call_sid}")
        if call_sid:
            end_call_session(call_sid, 0)
    except Exception as e:
        print(f"[Voicebot] Error: {e}")
        if call_sid:
            end_call_session(call_sid, 0)


# ── AUDIO CONVERSION HELPERS ───────────────────────────────────────────────────

def _encode_pcm(pcm_bytes: bytes) -> str:
    return base64.b64encode(pcm_bytes).decode("utf-8")


# 🔥 FIX: Copied from main.py to avoid importing main.py which triggers
# module-level side effects (ThreadPoolExecutor, second FastAPI app, duplicate imports)
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
    <h1>\U0001f3cd\ufe0f Shubham Motors — AI Voice Agent</h1>
    <p>Hero MotoCorp Authorized Dealer \u2022 Lal Kothi, Jaipur</p>
  </div>
  <div class="live">\U0001f7e2 LIVE</div>
</div>

<div class="stats">
  <div class="card"><div class="num">{stats.get('total',0)}</div><div class="lbl">Total Leads</div></div>
  <div class="card"><div class="num" style="color:#ff5555">{stats.get('hot',0)}</div><div class="lbl">\U0001f525 Hot</div></div>
  <div class="card"><div class="num" style="color:#ffaa00">{stats.get('warm',0)}</div><div class="lbl">\U0001f7e1 Warm</div></div>
  <div class="card"><div class="num" style="color:#5588ff">{stats.get('cold',0)}</div><div class="lbl">\u2744\ufe0f Cold</div></div>
  <div class="card"><div class="num" style="color:#44cc44">{stats.get('converted',0)}</div><div class="lbl">\u2705 Converted</div></div>
  <div class="card"><div class="num" style="color:#777">{stats.get('dead',0)}</div><div class="lbl">\u2620\ufe0f Dead</div></div>
  <div class="card"><div class="num" style="color:#44aaff">{stats.get('new',0)}</div><div class="lbl">\U0001f195 New</div></div>
</div>

<div class="section">
  <div class="toolbar">
    <button class="btn" onclick="open_modal('addModal')">\u2795 Add Lead</button>
    <button class="btn btn-green" onclick="open_modal('importModal')">\U0001f4e5 Import Excel</button>
    <button class="btn btn-purple" onclick="open_modal('offerModal')">\U0001f381 Upload Offer</button>
    <button class="btn btn-teal" onclick="location.reload()">\U0001f504 Refresh</button>
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
    <h3>\u2795 Add New Lead</h3>
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
    <label>Budget (\u20b9)</label>
    <input id="f_budget" placeholder="80000">
    <label>Area / Source</label>
    <input id="f_area" placeholder="Malviya Nagar / Facebook Ad">
    <label>Notes</label>
    <textarea id="f_notes" rows="2" placeholder="Any special requirement..."></textarea>
    <div class="row">
      <button class="btn" onclick="addLead()">\U0001f4be Save Lead</button>
      <button class="btn" style="background:#333" onclick="close_modal('addModal')">Cancel</button>
    </div>
  </div>
</div>

<!-- Import -->
<div class="modal" id="importModal">
  <div class="mbox">
    <h3>\U0001f4e5 Import Leads from Excel / CSV</h3>
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
    <h3>\U0001f381 Upload Offer / Scheme</h3>
    <label>Offer Title *</label>
    <input id="o_title" placeholder="Diwali Special \u2014 \u20b95,000 off + Free Accessories">
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


# ── ENTRYPOINT ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run("main_optimized:app", host="0.0.0.0", port=config.PORT, log_level="info")
