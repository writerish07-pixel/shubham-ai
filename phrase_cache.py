"""
phrase_cache.py
Pre-generates TTS audio for common Priya phrases at startup.

OPTIMIZATIONS:
- 🔥 OPTIMIZATION: Added intent response phrases to cache (covers ~80% of responses)
- 🔥 OPTIMIZATION: Normalized text comparison for better cache hits
- 🔥 FIX: Raised similarity threshold to 0.92 to prevent wrong audio for similar phrases
- 🔥 OPTIMIZATION: Hash-based exact match before fuzzy matching
"""
import logging
from difflib import SequenceMatcher
from voice import synthesize_speech
from audio_utils import _mp3_to_pcm

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("shubham-ai.phrase_cache")

# 🔥 FIX: Extended cache with ALL intent responses (including new intents) + common AI phrases
CACHED_PHRASES = [
    # Intent responses (from intent.py — must match exactly)
    "Bahut accha! Aap kab aa rahe hain — aaj ya kal?",
    "Accha ji! Kab showroom aa sakte hain test ride ke liye?",
    "Koi baat nahi! Kab call karoon — aapko kab free rahega?",
    "Lal Kothi Tonk Road, Jaipur. Subah 9 se shaam 7 baje tak khula hai.",
    "Monday se Saturday, subah 9 se shaam 7 baje tak. Aap kab aana chahenge?",
    "Test ride bilkul free hai! Aap kab aa sakte hain showroom?",
    "Koi baat nahi ji! Zaroorat ho toh call karein. Dhanyavaad!",
    "Bilkul! Kab call karoon — subah ya shaam?",
    "Dhanyavaad ji! Kuch aur madad chahiye toh bataaiye.",
    "EMI sirf 1,800 se shuru hai! Aapka budget bataaiye, best plan WhatsApp pe bhejungi.",
    # 🔥 FIX: New intent responses (price, mileage, availability, color, exchange, downpayment, whatsapp, greeting)
    "Sir, konsi bike mein interest hai? Model bataaiye, main best price WhatsApp pe bhej deti hoon.",
    "Hero bikes ka mileage sabse best hai — 50 se 80 kmpl tak! Konsi bike dekh rahe hain?",
    "Ji bilkul, ready stock hai showroom mein! Aap kab aa sakte hain dekhne?",
    "Bahut saare colors available hain! Konsi bike ka color dekhna hai? Showroom mein sab dikha doongi.",
    "Exchange offer available hai ji! Purani bike ka best price denge. Konsi bike hai aapki abhi?",
    "Sirf 1,000 rupaye se booking ho jaati hai, wo bhi refundable! Kab book karein?",
    "Bilkul! Aapka WhatsApp number ye hi hai kya? Main abhi details bhej deti hoon.",
    "Namaste ji! Main Priya, Shubham Motors se. Kaise madad kar sakti hoon aapki?",
    # Common AI fallback phrases
    "Ji, samajh rahi hoon. Thoda detail dein?",
    "Ji, main samajh rahi hoon. Aap bataaiye?",
    "Ji? Phir se bol sakte hain?",
    "Main manager se confirm karke bata deti hoon.",
    "WhatsApp pe details bhej deti hoon.",
    "Aapka budget kitna hai ji?",
    "Ji? Kuch suna nahi — louder bol sakte hain?",
    # Opening greetings
    "Namaste! Main Priya, Shubham Motors se. Kaise madad karoon?",
    "Namaste! Priya Shubham Motors se. Follow up tha — bike le li ya dekh rahe hain?",
]

_cache: dict[str, bytes] = {}
# 🔥 FIX: Raised threshold from 0.78 to 0.92 to prevent serving wrong
# cached audio when LLM-generated text is similar but semantically different
SIMILARITY_THRESHOLD = 0.92

# 🔥 OPTIMIZATION: Normalized exact match index for O(1) lookup
_exact_index: dict[str, bytes] = {}


def build_cache() -> None:
    """Generate PCM audio for all cached phrases. Call at startup."""
    success = 0
    for phrase in CACHED_PHRASES:
        try:
            audio = synthesize_speech(phrase, "hinglish")
            if audio:
                pcm = _mp3_to_pcm(audio)
                if pcm:
                    _cache[phrase] = pcm
                    # 🔥 OPTIMIZATION: Build normalized index for fast exact matching
                    _exact_index[phrase.strip().lower()] = pcm
                    success += 1
                    log.info(f"[PhraseCache] Cached: '{phrase[:50]}' ({len(pcm)} bytes)")
        except Exception as e:
            log.warning(f"[PhraseCache] Failed: '{phrase[:40]}': {e}")
    log.info(f"[PhraseCache] Built {success}/{len(CACHED_PHRASES)} phrases")


def get_cached_audio(text: str) -> bytes | None:
    """
    Return cached PCM if text matches a cached phrase.
    🔥 OPTIMIZATION: Hash-based exact match first (O(1)), then fuzzy.
    """
    text_clean = text.strip().lower()

    # 1. Hash-based exact match (O(1) — instant)
    if text_clean in _exact_index:
        log.info(f"[PhraseCache] Exact hit: '{text[:50]}'")
        return _exact_index[text_clean]

    # 2. Fuzzy match (only if cache is populated)
    if not _cache:
        return None

    best_ratio = 0.0
    best_pcm = None
    for phrase, pcm in _cache.items():
        ratio = SequenceMatcher(None, text_clean, phrase.lower()).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_pcm = pcm

    if best_ratio >= SIMILARITY_THRESHOLD:
        log.info(f"[PhraseCache] Fuzzy hit ({best_ratio:.2f}): '{text[:50]}'")
        return best_pcm

    return None
