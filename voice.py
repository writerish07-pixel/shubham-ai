"""
voice.py
Handles Speech-to-Text (Sarvam + Deepgram fallback) and
Text-to-Speech (Sarvam primary + ElevenLabs fallback).

NOTE on audio formats:
  - Sarvam TTS returns base64-encoded WAV (RIFF) bytes
  - ElevenLabs TTS returns MP3 bytes
  - The caller (main.py) MUST detect format via _audio_fmt() and save/serve correctly
  - Serving WAV bytes as audio/mpeg to Exotel <Play> causes silent/garbled audio
"""

import io, base64, re
import requests
import config

SARVAM_STT_URL     = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL     = "https://api.sarvam.ai/text-to-speech"
ELEVENLABS_TTS_URL = f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}"


# ── AUDIO FORMAT DETECTION ────────────────────────────────────────────────────

def audio_fmt(data: bytes) -> tuple:
    """
    Detect audio format from magic bytes.
    Returns (extension, mime_type).
    Sarvam TTS → WAV → ("wav", "audio/wav")
    ElevenLabs → MP3 → ("mp3", "audio/mpeg")
    """
    if len(data) >= 4 and data[:4] == b'RIFF':
        return "wav", "audio/wav"
    return "mp3", "audio/mpeg"


# ── SPEECH TO TEXT ────────────────────────────────────────────────────────────

def transcribe_audio(audio_bytes: bytes, language_hint: str = "hi-IN") -> dict:
    """
    Convert audio bytes to text.
    Returns {"text": "...", "language": "hindi/english/hinglish", "confidence": 0.9}
    Tries Sarvam first (better for Hindi/Hinglish), falls back to Deepgram.
    """
    # Try Sarvam AI first
    if config.SARVAM_API_KEY and not config.SARVAM_API_KEY.startswith("YOUR_"):
        try:
            result = _sarvam_stt(audio_bytes, language_hint)
            if result.get("text"):
                return result
        except Exception as e:
            print(f"[Voice] Sarvam STT failed: {e}, trying Deepgram")

    # Fallback to Deepgram
    if config.DEEPGRAM_API_KEY and not config.DEEPGRAM_API_KEY.startswith("YOUR_"):
        try:
            return _deepgram_stt(audio_bytes)
        except Exception as e:
            print(f"[Voice] Deepgram STT failed: {e}")

    return {"text": "", "language": "hinglish", "confidence": 0.0}


def _detect_audio_mime(audio_bytes: bytes) -> str:
    """Detect audio MIME type from magic bytes."""
    if len(audio_bytes) >= 4 and audio_bytes[:4] == b'RIFF':
        return "audio/wav"
    if len(audio_bytes) >= 3 and audio_bytes[:3] == b'ID3':
        return "audio/mpeg"
    if len(audio_bytes) >= 2 and audio_bytes[:2] in (b'\xff\xfb', b'\xff\xfa', b'\xff\xf3', b'\xff\xf2'):
        return "audio/mpeg"
    return "audio/wav"


def _sarvam_stt(audio_bytes: bytes, language: str = "hi-IN") -> dict:
    mime = _detect_audio_mime(audio_bytes)
    ext  = "wav" if mime == "audio/wav" else "mp3"
    headers = {"api-subscription-key": config.SARVAM_API_KEY}
    files = {"file": (f"audio.{ext}", io.BytesIO(audio_bytes), mime)}
    data = {
        "model": "saarika:v2",
        "language_code": language,
        "with_timestamps": False,
    }
    r = requests.post(SARVAM_STT_URL, headers=headers, files=files, data=data, timeout=15)
    if r.status_code != 200:
        print(f"[Voice] Sarvam STT HTTP {r.status_code}: {r.text[:200]}")
    r.raise_for_status()
    result = r.json()
    transcript = result.get("transcript", "")
    lang_code  = result.get("language_code", "hi-IN")
    return {
        "text": transcript,
        "language": _normalize_lang(lang_code),
        "confidence": 0.9
    }


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
    lang    = data.get("results", {}).get("channels", [{}])[0].get("detected_language", "hi")
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
    Convert text to audio bytes.
    Returns WAV bytes when Sarvam is used, MP3 bytes when ElevenLabs is used.
    Caller must use audio_fmt() to detect format before saving/serving.

    Priority:
      1. Sarvam AI (primary — best for Hindi/Hinglish, free tier available)
      2. ElevenLabs (fallback — requires paid subscription)
    """
    # Clean text — strip markdown, JSON blocks, extra whitespace
    text = re.sub(r'\{[\s\S]*?\}', '', text)
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = text.strip()

    if not text:
        return b""

    # ── Sarvam TTS (Primary) ──────────────────────────────────────────────────
    sarvam_ready = bool(config.SARVAM_API_KEY and not config.SARVAM_API_KEY.startswith("YOUR_"))
    if sarvam_ready:
        print(f"[TTS] Trying Sarvam (key: ...{config.SARVAM_API_KEY[-6:]})")
        try:
            audio = _sarvam_tts(text)
            if audio:
                print(f"[TTS] Sarvam OK — {len(audio)} bytes WAV")
                return audio
        except Exception as e:
            print(f"[Voice] Sarvam TTS failed: {e}")

    # ── ElevenLabs TTS (Fallback) ─────────────────────────────────────────────
    elevenlabs_ready = bool(
        config.ELEVENLABS_API_KEY and
        not config.ELEVENLABS_API_KEY.startswith("YOUR_")
    )
    if not sarvam_ready and not elevenlabs_ready:
        print("[TTS] ERROR: No TTS provider configured. Set SARVAM_API_KEY in .env")
        return b""

    if elevenlabs_ready:
        print("[TTS] Trying ElevenLabs fallback")
        try:
            audio = _elevenlabs_tts(text)
            if audio:
                print(f"[TTS] ElevenLabs OK — {len(audio)} bytes MP3")
                return audio
        except Exception as e:
            print(f"[Voice] ElevenLabs TTS failed: {e}")

    return b""


def _sarvam_tts(text: str, language: str = "hi-IN") -> bytes:
    """
    Call Sarvam TTS API.
    Returns WAV bytes (RIFF format).
    The caller (main.py) MUST save as .wav and serve as audio/wav.
    """
    headers = {
        "api-subscription-key": config.SARVAM_API_KEY,
        "Content-Type": "application/json",
    }
    # Sarvam bulbul:v2 supports longer text — truncate at 1000 chars to be safe
    if len(text) > 1000:
        truncated = text[:1000]
        # Try to cut at a sentence boundary
        for sep in ['. ', '! ', '? ', ', ']:
            idx = truncated.rfind(sep)
            if idx > 500:
                truncated = truncated[:idx + 1]
                break
        text = truncated

    payload = {
        "inputs": [text],
        "target_language_code": language,
        "speaker": "neha",
        "model": "bulbul:v3",
        "output_audio_codec": "mp3",
    }
    r = requests.post(SARVAM_TTS_URL, headers=headers, json=payload, timeout=20)
    if r.status_code != 200:
        print(f"[Voice] Sarvam TTS HTTP {r.status_code}: {r.text[:300]}")
    r.raise_for_status()
    data = r.json()
    audio_b64 = data.get("audios", [""])[0]
    if not audio_b64:
        raise ValueError("Sarvam TTS returned empty audio")
    return base64.b64decode(audio_b64)  # WAV bytes


def _elevenlabs_tts(text: str) -> bytes:
    """Call ElevenLabs TTS. Returns MP3 bytes."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}"
    headers = {
        "xi-api-key": config.ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text[:2500],  # ElevenLabs char limit
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
            "style": 0.3,
            "use_speaker_boost": True
        }
    }
    r = requests.post(url, headers=headers, json=payload, timeout=20)
    if r.status_code != 200:
        print(f"[Voice] ElevenLabs TTS HTTP {r.status_code}: {r.text[:200]}")
    r.raise_for_status()
    return r.content  # MP3 bytes
