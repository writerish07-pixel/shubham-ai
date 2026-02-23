"""
voice.py
Handles Speech-to-Text (Deepgram + Sarvam) and Text-to-Speech (ElevenLabs + Sarvam).
Detects language and routes to best provider.
"""
import io, base64, requests
import httpx
import config

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
ELEVENLABS_TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}"


# ── SPEECH TO TEXT ────────────────────────────────────────────────────────────

def transcribe_audio(audio_bytes: bytes, language_hint: str = "hi-IN") -> dict:
    """
    Convert audio bytes to text. 
    Returns {"text": "...", "language": "hi/en/hinglish", "confidence": 0.95}
    Tries Sarvam first (better for Hindi/Hinglish), falls back to Deepgram.
    """
    # Try Sarvam AI first for Hindi/Hinglish
    try:
        result = _sarvam_stt(audio_bytes, language_hint)
        if result.get("text"):
            return result
    except Exception as e:
        print(f"[Voice] Sarvam STT failed: {e}, trying Deepgram")
    
    # Fallback to Deepgram
    try:
        return _deepgram_stt(audio_bytes)
    except Exception as e:
        print(f"[Voice] Deepgram STT failed: {e}")
        return {"text": "", "language": "unknown", "confidence": 0.0}


def _sarvam_stt(audio_bytes: bytes, language: str = "hi-IN") -> dict:
    if not config.SARVAM_API_KEY:
        raise ValueError("SARVAM_API_KEY not configured")
    mime = _detect_audio_mime(audio_bytes)
    ext  = "wav" if mime == "audio/wav" else "mp3"
    headers = {"api-subscription-key": config.SARVAM_API_KEY}
    files = {"file": (f"audio.{ext}", io.BytesIO(audio_bytes), mime)}
    data = {
        "model": "saarika:v2",
        "language_code": language,
        "with_timestamps": "false",
    }
    r = requests.post(SARVAM_STT_URL, headers=headers, files=files, data=data, timeout=15)
    r.raise_for_status()
    result = r.json()
    transcript = result.get("transcript", "")
    lang_code = result.get("language_code", "hi-IN")
    return {
        "text": transcript,
        "language": _normalize_lang(lang_code),
        "confidence": 0.9
    }


def _detect_audio_mime(audio_bytes: bytes) -> str:
    """Detect audio MIME type from magic bytes. Exotel recordings can be WAV or MP3."""
    if len(audio_bytes) >= 4 and audio_bytes[:4] == b'RIFF':
        return "audio/wav"
    if len(audio_bytes) >= 3 and audio_bytes[:3] == b'ID3':
        return "audio/mpeg"
    if len(audio_bytes) >= 2 and audio_bytes[:2] in (b'\xff\xfb', b'\xff\xfa', b'\xff\xf3', b'\xff\xf2'):
        return "audio/mpeg"
    return "audio/wav"  # safe default


def _deepgram_stt(audio_bytes: bytes) -> dict:
    mime_type = _detect_audio_mime(audio_bytes)
    headers = {
        "Authorization": f"Token {config.DEEPGRAM_API_KEY}",
        "Content-Type": mime_type,
    }
    params = {
        "model": "nova-2",
        "language": "hi",
        "detect_language": "true",
        "smart_format": "true",
        "punctuate": "true",
    }
    r = requests.post(
        "https://api.deepgram.com/v1/listen",
        headers=headers, params=params,
        data=audio_bytes, timeout=15
    )
    r.raise_for_status()
    data = r.json()
    results = data.get("results", {}).get("channels", [{}])[0].get("alternatives", [{}])[0]
    lang = data.get("results", {}).get("channels", [{}])[0].get("detected_language", "hi")
    return {
        "text": results.get("transcript", ""),
        "language": _normalize_lang(lang),
        "confidence": results.get("confidence", 0.8)
    }


def _normalize_lang(code: str) -> str:
    code = code.lower()
    if "en" in code: return "english"
    if "hi" in code: return "hindi"
    if "raj" in code: return "rajasthani"
    return "hinglish"


# ── TEXT TO SPEECH ────────────────────────────────────────────────────────────

def synthesize_speech(text: str, language: str = "hinglish") -> bytes:
    """
    Convert text to audio bytes (WAV/MP3).
    Uses Sarvam as primary TTS (better for Hindi/Hinglish), ElevenLabs as fallback.
    """
    # Clean text — remove markdown, JSON blocks
    import re
    text = re.sub(r'\{[^}]+\}', '', text, flags=re.DOTALL)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = text.strip()

    if not text:
        return b""

    # Sarvam first — works for Hindi, Hinglish, and English
    if config.SARVAM_API_KEY:
        print(f"[TTS] Using Sarvam (key set: {config.SARVAM_API_KEY[:8]}...)")
        try:
            return _sarvam_tts(text, "hi-IN")
        except Exception as e:
            print(f"[Voice] Sarvam TTS failed: {e}, trying ElevenLabs")

    # ElevenLabs fallback
    if not config.SARVAM_API_KEY:
        print("[TTS] WARNING: SARVAM_API_KEY not set — using ElevenLabs (may fail if quota exceeded)")
    try:
        return _elevenlabs_tts(text)
    except Exception as e:
        print(f"[Voice] ElevenLabs TTS failed: {e}")
        return b""


def _elevenlabs_tts(text: str) -> bytes:
    headers = {
        "xi-api-key": config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True
        }
    }
    r = requests.post(ELEVENLABS_TTS_URL, headers=headers, json=payload, timeout=20)
    r.raise_for_status()
    return r.content  # MP3 bytes


def _sarvam_tts(text: str, language: str = "hi-IN") -> bytes:
    headers = {
        "api-subscription-key": config.SARVAM_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "inputs": [text],
        "target_language_code": language,
        "speaker": "meera",
        "model": "bulbul:v1",
        "pitch": 0,
        "pace": 1.1,
        "loudness": 1.2,
        "enable_preprocessing": True,
    }
    r = requests.post(SARVAM_TTS_URL, headers=headers, json=payload, timeout=20)
    r.raise_for_status()
    data = r.json()
    audio_b64 = data.get("audios", [""])[0]
    return base64.b64decode(audio_b64)