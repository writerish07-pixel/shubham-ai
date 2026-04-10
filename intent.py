"""
intent.py
Fast intent detection — bypasses Groq for simple/common customer inputs.

Covers ~25 intents with exact + fuzzy matching to handle STT errors.
Reduces LLM calls by ~60-70% by catching common patterns locally.
"""
from difflib import SequenceMatcher

INTENTS = {
    "yes_visit": {
        "patterns": frozenset([
            "aa jaunga", "aa jaungi", "aaonga", "aaunga", "aa sakta",
            "aa sakti", "aata hoon", "aati hoon", "visit karunga", "aaugi",
            "aa jaugi", "showroom aaunga", "showroom aaugi",
            "आ जाऊँगा", "आ जाऊँगी", "आ सकता", "आ सकती",
            "आता हूँ", "आती हूँ", "आ जाऊंगा", "आ जाऊंगी",
            "शोरूम आऊँगा", "शोरूम आऊँगी", "आऊँगा", "आऊँगी",
            "aa jata hoon", "aa raha hoon", "aa rahe hain",
            "aata hu", "aati hu", "aa jayenge", "aa jayega",
        ]),
        "response": "Bahut accha! Aap kab aa rahe hain — aaj ya kal?"
    },
    "busy": {
        "patterns": frozenset([
            "busy", "baad mein", "baad me", "abhi nahi", "abhi mat",
            "baad mein call", "later", "free nahi", "time nahi",
            "व्यस्त", "बाद में", "अभी नहीं", "बाद में कॉल", "फ्री नहीं",
            "टाइम नहीं", "अभी मत", "meeting mein", "driving",
            "abhi busy", "kaam pe", "office mein", "kaam mein",
        ]),
        "response": "Koi baat nahi! Kab call karoon — aapko kab free rahega?"
    },
    "not_interested": {
        "patterns": frozenset([
            "nahi chahiye", "interest nahi", "mat karo call", "band karo",
            "hata lo number", "nahi lena", "no thanks", "नहीं चाहिए", "इंटरेस्ट नहीं",
            "मत करो कॉल", "बंद करो", "हटा लो नंबर", "नहीं लेना", "कोई जरूरत नहीं",
            "zaroorat nahi", "जरूरत नहीं", "don't call", "mat call karo",
            "le liya", "already le liya", "kharid liya", "kahi aur se",
        ]),
        "response": "Koi baat nahi ji! Zaroorat ho toh call karein. Dhanyavaad!"
    },
    "callback": {
        "patterns": frozenset([
            "call karo", "call karna", "phone karo", "phone karna",
            "baad mein baat", "call back", "कॉल करो", "कॉल करना",
            "फोन करो", "फोन करना", "बाद में बात", "कॉल बैक", "बाद में कॉल करो",
            "kal call karna", "shaam ko call", "subah call",
        ]),
        "response": "Bilkul! Kab call karoon — subah ya shaam?"
    },
    "price": {
        "patterns": frozenset([
            "price", "price kya hai", "kitne ka hai", "kitne ki hai",
            "kya price hai", "cost", "rate", "daam", "kimat", "kitna hai",
            "कीमत", "दाम", "कितने का", "कितने की", "रेट", "प्राइस",
            "price batao", "price bataiye", "kitna lagega", "kitna padega",
            "on road price", "on road", "ex showroom", "showroom price",
            "price range", "budget range", "kitne mein milegi",
            "kitne mein aayegi", "total cost", "total kitna",
        ]),
        "response": "Sir, konsi bike mein interest hai? Model bataaiye, main best price WhatsApp pe bhej deti hoon."
    },
    "mileage": {
        "patterns": frozenset([
            "mileage", "kitna deti hai", "kitna chalti hai", "average",
            "fuel economy", "petrol", "kitna mileage", "mileage kitna",
            "माइलेज", "कितना देती", "कितना चलती", "एवरेज", "पेट्रोल",
            "kitna degi", "average kitna", "mileage kaisa",
        ]),
        "response": "Hero bikes ka mileage sabse best hai — 50 se 80 kmpl tak! Konsi bike dekh rahe hain?"
    },
    "availability": {
        "patterns": frozenset([
            "available", "stock mein", "available hai", "mil jayegi",
            "ready hai", "delivery kab", "kab milegi", "stock",
            "उपलब्ध", "स्टॉक", "मिल जाएगी", "डिलीवरी कब", "कब मिलेगी",
            "ready stock", "abhi mil jayegi", "turant milegi",
        ]),
        "response": "Ji bilkul, ready stock hai showroom mein! Aap kab aa sakte hain dekhne?"
    },
    "color": {
        "patterns": frozenset([
            "colour", "color", "rang", "kaunsa rang", "kaunsa color",
            "konsa colour", "konsa color", "kaun kaun se color",
            "रंग", "कौनसा रंग", "कलर",
            "red wali", "black wali", "blue wali", "white wali",
            "lal wali", "kala wali", "neela wali", "safed wali",
        ]),
        "response": "Bahut saare colors available hain! Konsi bike ka color dekhna hai? Showroom mein sab dikha doongi."
    },
    "exchange": {
        "patterns": frozenset([
            "exchange", "purani bike", "old bike", "purana", "exchange offer",
            "trade in", "bechni hai", "purani wali", "पुरानी बाइक",
            "एक्सचेंज", "पुरानी वाली", "बेचनी है",
            "exchange value", "kitna milega purani", "purani deke",
        ]),
        "response": "Exchange offer available hai ji! Purani bike ka best price denge. Konsi bike hai aapki abhi?"
    },
    "downpayment": {
        "patterns": frozenset([
            "downpayment", "down payment", "booking amount", "kitna dena padega",
            "advance", "booking", "book", "reserve", "token",
            "डाउनपेमेंट", "बुकिंग", "एडवांस", "टोकन",
            "booking kaise", "book kaise", "kitna advance",
        ]),
        "response": "Sirf 1,000 rupaye se booking ho jaati hai, wo bhi refundable! Kab book karein?"
    },
    "acknowledgement": {
        "patterns": frozenset([
            "haan", "han", "haa", "ok", "okay", "theek", "theek hai",
            "ji haan", "bilkul", "sahi", "accha", "acha", "hmm", "hm",
            "हाँ", "हां", "ठीक है", "ठीक", "जी", "जी हाँ", "बिल्कुल",
            "सही", "अच्छा", "हम्म",
        ]),
        "response": "Accha ji! Kab showroom aa sakte hain test ride ke liye?"
    },
    "address": {
        "patterns": frozenset([
            "address", "kahan hai", "kahan he", "location", "showroom kahan",
            "jagah", "kidhar", "kahaan", "showroom ka", "showroom ki",
            "एड्रेस", "पता", "कहाँ है", "कहाँ", "कहां है", "कहां",
            "लोकेशन", "जगह", "किधर", "शोरूम कहाँ", "शोरूम का पता",
            "map", "google map",
        ]),
        "response": "Lal Kothi Tonk Road, Jaipur. Subah 9 se shaam 7 baje tak khula hai."
    },
    "timing": {
        "patterns": frozenset([
            "timing", "kitne baje", "kab khulta", "band kab", "working hours",
            "khula", "showroom ka time", "showroom ki timing", "टाइम", "समय",
            "कितने बजे", "कब खुलता", "बंद कब", "वर्किंग आवर्स", "खुला रहेगा",
            "sunday khula", "sunday open", "ravivar",
        ]),
        "response": "Monday se Saturday, subah 9 se shaam 7 baje tak. Aap kab aana chahenge?"
    },
    "test_ride": {
        "patterns": frozenset([
            "test ride", "test drive", "chalana", "try", "chalake dekhna",
            "drive karna", "ride karna", "टेस्ट राइड", "टेस्ट ड्राइव", "चलाना",
            "चला के देखना", "ड्राइव करना", "राइड करना", "चलाकर देखना",
            "chala ke dekh", "ride karni hai",
        ]),
        "response": "Test ride bilkul free hai! Aap kab aa sakte hain showroom?"
    },
    "thanks": {
        "patterns": frozenset([
            "dhanyavaad", "thank you", "thanks", "shukriya", "धन्यवाद",
            "शुक्रिया", "thanku", "thnx", "bahut shukriya",
        ]),
        "response": "Dhanyavaad ji! Kuch aur madad chahiye toh bataaiye."
    },
    "emi": {
        "patterns": frozenset([
            "emi", "installment", "monthly", "loan", "finance",
            "किस्त", "ईएमआई", "mahina", "per month",
            "emi kitni", "monthly kitna", "loan milega",
            "finance available", "emi pe", "kist",
        ]),
        "response": "EMI sirf 1,800 se shuru hai! Aapka budget bataaiye, best plan WhatsApp pe bhejungi."
    },
    "whatsapp": {
        "patterns": frozenset([
            "whatsapp", "whatsapp pe bhejo", "whatsapp karo",
            "message karo", "details bhejo", "brochure bhejo",
            "व्हाट्सएप", "मैसेज करो", "डिटेल्स भेजो",
            "whatsapp number", "photo bhejo", "video bhejo",
        ]),
        "response": "Bilkul! Aapka WhatsApp number ye hi hai kya? Main abhi details bhej deti hoon."
    },
    "greeting": {
        "patterns": frozenset([
            "namaste", "namaskar", "hello", "hi", "hey",
            "नमस्ते", "नमस्कार", "हैलो",
            "good morning", "good afternoon", "good evening",
        ]),
        "response": "Namaste ji! Main Priya, Shubham Motors se. Kaise madad kar sakti hoon aapki?"
    },
    # Need discovery intents — capture customer situation without LLM
    "usage_query": {
        "patterns": frozenset([
            "office ke liye", "daily use", "commute", "office jaana",
            "college ke liye", "school ke liye", "family ke liye",
            "ghar ke liye", "sheher mein", "city mein", "highway",
            "lambi doori", "long distance", "village", "gaon",
        ]),
        "response": "Accha ji! Aapka budget kitna hai? Best matching model suggest karti hoon."
    },
    "budget_query": {
        "patterns": frozenset([
            "budget", "kitna kharcha", "kitna lagega total",
            "50 hazaar", "60 hazaar", "70 hazaar", "80 hazaar",
            "90 hazaar", "1 lakh", "ek lakh", "1.5 lakh",
            "kam budget", "sasta", "cheapest", "sabse sasta",
            "budget kam hai", "jyada nahi", "limited budget",
        ]),
        "response": "Ji bilkul! Is budget mein achhe options hain. Showroom aayiye, sab dikhati hoon!"
    },
    "service_query": {
        "patterns": frozenset([
            "service", "servicing", "free service", "service center",
            "service kab", "service kitni", "warranty", "guarantee",
            "सर्विस", "सर्विसिंग", "वारंटी", "गारंटी",
            "service cost", "service charge", "maintenance",
        ]),
        "response": "Hero ki service sabse sasti hai aur 5 free services milti hain! Aur kuch jaanna hai?"
    },
    "insurance_query": {
        "patterns": frozenset([
            "insurance", "bima", "insure", "insurance kitna",
            "इंश्योरेंस", "बीमा", "insurance cost", "insurance included",
        ]),
        "response": "Insurance bilkul arrange ho jayega. Best rate milega humse! Kab aana chahenge?"
    },
    "comparison": {
        "patterns": frozenset([
            "compare", "comparison", "konsi better", "konsi acchi",
            "kya farak", "difference", "dono mein", "vs",
            "splendor ya passion", "glamour ya xtreme",
            "konsi loon", "suggest karo", "recommend",
        ]),
        "response": "Dono achhi hain! Aap bike kahan use karenge — daily office ya family rides?"
    },
    "offer_query": {
        "patterns": frozenset([
            "offer", "discount", "scheme", "deal", "cashback",
            "ऑफर", "डिस्काउंट", "स्कीम", "कैशबैक",
            "koi offer", "kya offer", "special offer", "festival offer",
            "kuch offer", "best deal", "sasta karo",
        ]),
        "response": "Haan ji, is mahine special offer chal raha hai! Showroom aayiye, full details deti hoon."
    },
}

# Pre-build flattened pattern list for fuzzy matching
_ALL_PATTERNS = []
for _intent_name, _data in INTENTS.items():
    for _pattern in _data["patterns"]:
        _ALL_PATTERNS.append((_pattern, _intent_name))

# Fuzzy match threshold — minimum similarity ratio for a match
FUZZY_THRESHOLD = 0.78  # Slightly lower to catch more STT errors


def detect_intent(text: str, lead: dict = None) -> str | None:
    """
    Fast intent matching with fuzzy fallback.
    
    Pipeline:
    1. Exact/substring match (O(1) per pattern) — instant
    2. Fuzzy match via SequenceMatcher — still <1ms for ~300 patterns
    
    Returns response string if matched, None otherwise.
    """
    text_lower = text.lower().strip()
    if len(text_lower) < 2:
        return None
    
    has_name = lead and lead.get("name", "").strip()
    words = set(text_lower.split())
    
    # ── Pass 1: Exact/substring match (instant) ──────────────────────
    for intent_name, data in INTENTS.items():
        for pattern in data["patterns"]:
            # Single-word patterns use exact word match to avoid false positives
            if ' ' not in pattern:
                matched = pattern in words
            else:
                matched = pattern in text_lower
            if matched:
                if intent_name == "acknowledgement" and not has_name:
                    break  # Skip acknowledgement without name
                print(f"[Intent] Exact match '{intent_name}' for: '{text[:50]}'")
                return data["response"]
    
    # ── Pass 2: Fuzzy match for near-misses (handles STT errors/typos) ──
    # Only for inputs longer than 4 chars to avoid false positives on short words
    if len(text_lower) > 4:
        best_ratio = 0.0
        best_intent = None
        
        for pattern, intent_name in _ALL_PATTERNS:
            # Only fuzzy-match patterns of similar length (±50% chars)
            if abs(len(pattern) - len(text_lower)) > max(len(pattern), len(text_lower)) * 0.5:
                continue
            
            ratio = SequenceMatcher(None, text_lower, pattern).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_intent = intent_name
        
        if best_ratio >= FUZZY_THRESHOLD and best_intent:
            # Skip acknowledgement without name (same guard as exact match)
            if best_intent == "acknowledgement" and not has_name:
                return None
            print(f"[Intent] Fuzzy match '{best_intent}' ({best_ratio:.2f}) for: '{text[:50]}'")
            return INTENTS[best_intent]["response"]
    
    return None
