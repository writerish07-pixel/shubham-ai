"""
phrase_cache.py
Pre-generates TTS audio for common Priya phrases at startup.

Covers all intent responses + common AI fallback phrases.
Hash-based exact match (O(1)) with fuzzy fallback.
"""
import logging
from difflib import SequenceMatcher
from voice import synthesize_speech
from audio_utils import _mp3_to_pcm

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("shubham-ai.phrase_cache")

CACHED_PHRASES = [
    # Intent responses (must match intent.py exactly)
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
    "Sir, konsi bike mein interest hai? Model bataaiye, main best price WhatsApp pe bhej deti hoon.",
    "Hero bikes ka mileage sabse best hai — 50 se 80 kmpl tak! Konsi bike dekh rahe hain?",
    "Ji bilkul, ready stock hai showroom mein! Aap kab aa sakte hain dekhne?",
    "Bahut saare colors available hain! Konsi bike ka color dekhna hai? Showroom mein sab dikha doongi.",
    "Exchange offer available hai ji! Purani bike ka best price denge. Konsi bike hai aapki abhi?",
    "Sirf 1,000 rupaye se booking ho jaati hai, wo bhi refundable! Kab book karein?",
    "Bilkul! Aapka WhatsApp number ye hi hai kya? Main abhi details bhej deti hoon.",
    "Namaste ji! Main Priya, Shubham Motors se. Kaise madad kar sakti hoon aapki?",
    # New intent responses (usage, budget, service, insurance, comparison, offer)
    "Accha ji! Aapka budget kitna hai? Best matching model suggest karti hoon.",
    "Ji bilkul! Is budget mein achhe options hain. Showroom aayiye, sab dikhati hoon!",
    "Hero ki service sabse sasti hai aur 5 free services milti hain! Aur kuch jaanna hai?",
    "Insurance bilkul arrange ho jayega. Best rate milega humse! Kab aana chahenge?",
    "Dono achhi hain! Aap bike kahan use karenge — daily office ya family rides?",
    "Haan ji, is mahine special offer chal raha hai! Showroom aayiye, full details deti hoon.",
    # Common AI fallback phrases
    "Ji, samajh rahi hoon. Aap bataaiye?",
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
SIMILARITY_THRESHOLD = 0.92
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
                    _exact_index[phrase.strip().lower()] = pcm
                    success += 1
                    log.info(f"[PhraseCache] Cached: '{phrase[:50]}' ({len(pcm)} bytes)")
        except Exception as e:
            log.warning(f"[PhraseCache] Failed: '{phrase[:40]}': {e}")
    log.info(f"[PhraseCache] Built {success}/{len(CACHED_PHRASES)} phrases")


def get_cached_audio(text: str) -> bytes | None:
    """Return cached PCM if text matches a cached phrase (O(1) exact, then fuzzy)."""
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
