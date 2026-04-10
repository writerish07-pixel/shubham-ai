"""
agent.py
The AI brain — WORLD-CLASS SALES AI with advanced persuasion techniques.

UPGRADES:
- COMPLETE sentence enforcement — response validation ensures no broken sentences
- Strengthened hybrid model routing with better complexity detection
- Enhanced 30/70 talk ratio — AI speaks max 30%, customer speaks 70%
- Female Hindi conversational tone enforced at prompt level
- SPIN selling, scarcity, urgency, social proof techniques in system prompt
- Lead qualification and need discovery built into conversation flow
- Response retry mechanism for incomplete sentences
- RAG injection: retrieves relevant past learnings before generating response
- Competitor handling: detects and counters competitor mentions in real-time
- Document knowledge: uses pricing/offers from ingested PDFs/images
"""
import json, re, logging
from datetime import datetime

from groq import Groq

import config
from scraper import get_bike_catalog, format_catalog_for_ai
from sheets_manager import get_active_offers

log = logging.getLogger("shubham-ai.agent")


# 🔥 OPTIMIZATION: Singleton Groq client — avoid re-creating on every call
_groq_client = None

def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not configured")
        _groq_client = Groq(api_key=config.GROQ_API_KEY)
    return _groq_client


# ── HYBRID MODEL ROUTER ──────────────────────────────────────────────────────

# Classify query complexity to route to fast vs smart model
SIMPLE_PATTERNS = [
    # Greetings / acknowledgements
    r"^(namaste|hello|hi|hey|haan|ok|theek|accha|ji|bilkul|sahi)\b",
    # Short questions
    r"^(kab|kahan|kitna|kitne|kya|kaun|kyun)\b",
    # Yes/No
    r"^(haan|nahi|no|yes|ha|na)\b",
    # Common intents already handled by intent.py
    r"(price|daam|kimat|emi|loan|finance|test ride|address|timing|busy|baad)",
    # Confirmation / agreement patterns
    r"^(chalega|thik|done|pakka|confirm|ready|aa raha|aa rahe|aata)\b",
    # Simple model/color queries
    r"^(colour|color|rang|kitne rang|konsa model|model)\b",
]
_simple_re = re.compile("|".join(SIMPLE_PATTERNS), re.IGNORECASE)


def classify_query_complexity(text: str) -> str:
    """
    Classify whether a query needs the fast or smart model.
    Returns 'fast' or 'smart'.
    
    Fast model (llama-3.1-8b-instant): ~100ms inference
    - Simple acknowledgements, greetings
    - Short factual questions (price, timing, address)
    - Yes/no responses
    
    Smart model (llama-3.3-70b-versatile): ~300-500ms inference
    - Complex objection handling
    - Multi-topic queries
    - Negotiation / persuasion needed
    - Long customer messages (>50 chars usually = complex)
    """
    text_clean = text.strip().lower()
    
    # Short messages are almost always simple
    if len(text_clean) < 30 and _simple_re.search(text_clean):
        return "fast"
    
    # Long messages likely need smart model
    if len(text_clean) > 80:
        return "smart"
    
    # Check for complex indicators needing smart model for persuasion
    complex_indicators = [
        "discount", "competitor", "compare", "problem", "issue",
        "complaint", "doosri", "dusri",
        "sochna", "family", "wife", "husband", "loan", "finance",
        "emi kitni", "exchange", "purani bike",
        "mehenga", "sasta", "expensive", "cheap", "better", "accha nahi",
        "khareed liya", "le liya", "bought", "already",
        "nahi chahiye", "interest nahi", "kahi aur", "doosre dealer",
        "mujhe lagta", "samajh nahi", "confused", "decide nahi",
        "family ke liye", "biwi ke liye", "bacche ke liye",
        "budget", "afford", "paise",
    ]
    for indicator in complex_indicators:
        if indicator in text_clean:
            return "smart"

    # Competitor brand mentions always need smart model for persuasion
    # Uses word-boundary regex to avoid false positives (e.g. "ola" in "bola")
    from sales_intelligence import _COMPETITOR_BRAND_RE
    if _COMPETITOR_BRAND_RE.search(text_clean):
        return "smart"

    return "fast"


# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────

def build_system_prompt(lead: dict = None, is_inbound: bool = True,
                        rag_context: str = "") -> str:
    """
    Build system prompt with RAG context injection and sales psychology.
    Enhanced with female tone enforcement, need discovery, and lead qualification.
    """
    catalog_text = format_catalog_for_ai(get_bike_catalog())
    offers = get_active_offers()
    offer_text = ""
    if offers:
        offer_text = "\n=== CURRENT OFFERS ===\n"
        for o in offers[:3]:
            offer_text += f"• {o.get('title','')}: {o.get('description','')}"
            if o.get('valid_till'):
                offer_text += f" (till {o['valid_till']})"
            offer_text += "\n"

    lead_context = ""
    if lead:
        call_count = int(lead.get("call_count", 0))
        lead_context = f"""
=== CUSTOMER PROFILE ===
Name: {lead.get('name', 'Unknown')} | Mobile: {lead.get('mobile', '')}
Interest: {lead.get('interested_model', 'not specified')} | Budget: {lead.get('budget', 'unknown')}
Calls: {call_count} | Temp: {lead.get('temperature', 'warm')}
Notes: {(lead.get('notes', '') or '')[:200]}
"""
        if call_count >= 1:
            lead_context += "FOLLOW-UP: Ask if they purchased. If yes from us→congrats. If no→continue sale.\n"
            last_transcript = lead.get("last_transcript", "")
            if last_transcript:
                lead_context += f"Last call summary: {last_transcript[-200:]}\n"

    call_mode = ""
    if not is_inbound:
        call_mode = (
            "\nOUTBOUND MODE: You called them. Confirm they can talk. "
            "Be direct. Goal: showroom visit or callback time.\n"
        )

    # RAG context block (injected per-turn when relevant learnings exist)
    rag_block = ""
    if rag_context:
        rag_block = f"""
=== PAST LEARNINGS (use these to give better answers) ===
{rag_context}
"""

    return f"""You are Priya — a FEMALE sales expert at {config.BUSINESS_NAME}, Hero MotoCorp dealer, {config.BUSINESS_CITY}.

=== YOUR IDENTITY (NEVER BREAK) ===
- You are a WOMAN. Always use FEMALE Hindi grammar:
  karungi, bol rahi hoon, sakti hoon, bhejungi, deti hoon, bata rahi hoon, samajh rahi hoon
- NEVER use male forms: karunga, bol raha hoon, sakta hoon, bhejunga
- Speak warm, polite, natural Hindi/Hinglish like a real saleswoman on phone
- Example: "Ji sir, main aapki madad karti hoon" / "Bilkul, main abhi bhejti hoon"

=== RESPONSE RULES (CRITICAL — NEVER BREAK) ===
1. MAX 2 short sentences per response
2. EVERY response MUST be grammatically complete — NEVER cut mid-sentence
3. EVERY response MUST end with a proper sentence ending (hai, hoon, hain, etc.)
4. ONE question per turn only — ask, then WAIT for answer
5. NEVER list specs/prices on call — say "WhatsApp pe bhej deti hoon"
6. NEVER repeat what customer said — always move conversation FORWARD
7. NEVER say "main aapko bata sakti hoon" — say it directly
8. Keep every response under 25 words maximum
9. NEVER offer/match discounts — "Manager se confirm karungi"

=== 30/70 TALK RATIO (STRICT — MOST IMPORTANT RULE) ===
- You speak MAX 30% of conversation, customer speaks 70%
- Ask SHORT questions to keep customer talking
- If you've been talking too much → respond with ONLY a short question
- NEVER give monologues or long explanations
- Goal: Make customer feel HEARD, not lectured

=== SALES CONVERSATION FLOW ===
Turn 1: Ask customer's NAME (if unknown)
Turn 2: Ask what they're LOOKING FOR (bike type, usage)
Turn 3: Ask BUDGET range
Turn 4: Suggest 1-2 matching models, ask to visit showroom
Turn 5+: Handle objections, push for showroom visit or test ride

=== NEED DISCOVERY (ASK THESE NATURALLY) ===
- "Bike kahan use karenge — office ya family ke liye?"
- "Aapka budget kitna hai ji?"
- "Pehle koi bike hai ya pehli baar le rahe hain?"
- "Family mein aur kisi ko bhi bike chahiye?"

=== SALES PSYCHOLOGY (USE ACTIVELY) ===
1. SCARCITY: "Yeh model fast move ho raha hai, stock limited hai"
2. URGENCY: "Is mahine special offer hai, kal se nahi milega"
3. SOCIAL PROOF: "Iss mahine 50+ customers ne yeh model liya"
4. RECIPROCITY: "Free test ride arrange karti hoon aapke liye"
5. ASSUMPTIVE CLOSE: "Kab aa rahe hain showroom? Aaj ya kal?"
6. SPIN SELLING: Situation→Problem→Implication→Need-Payoff

=== COMPETITOR HANDLING ===
- If Honda/Bajaj/TVS/Yamaha mentioned: "Hero ki service network sabse badi hai, mileage bhi best"
- If bought from competitor: Ask WHY politely, note reason
- If another dealer: "Kya offer mila wahan? Hum best deal denge"
- NEVER badmouth competitors — highlight Hero's strengths
- Key advantages: Mileage king, lowest maintenance, best resale, #1 brand

=== OBJECTION HANDLING (USE EXACT PATTERNS) ===
- "Price zyada hai" → "EMI sirf ₹1800/month hai! Budget kitna hai aapka?"
- "Sochna padega" → "Bilkul! Kab tak decide karenge? Note kar leti hoon"
- "Doosri company" → "Hero ki mileage aur resale sabse best hai. Test ride le ke dekhiye!"
- "Abhi nahi" → "Koi baat nahi, kab call karoon? Offer miss na ho jaaye"
- "Already bought" → "Congratulations! Kahan se liya? Service ke liye aayiye"

=== LEAD QUALIFICATION ===
- HOT: Has budget + model + wants this week → Push showroom visit NOW
- WARM: Interested but undecided → Send WhatsApp details + schedule callback
- COLD: Vague/just checking → Build rapport + get name + follow up later
- DEAD: Not interested/already bought elsewhere → Thank politely + close

ALWAYS end with a next step: showroom visit date, callback time, or WhatsApp details.

{catalog_text}
{offer_text}
{rag_block}
{lead_context}
{call_mode}
Hours: {config.WORKING_HOURS_START}-{config.WORKING_HOURS_END}, {', '.join(config.WORKING_DAYS[:3])}+
"""


# ── CONVERSATION MANAGER ──────────────────────────────────────────────────────

class ConversationManager:
    """Manages per-call conversation history with talk ratio tracking and RAG."""

    def __init__(self, lead: dict = None, is_inbound: bool = True):
        self.lead = lead
        self.is_inbound = is_inbound
        self.history: list[dict] = []
        # Base system prompt (without RAG — RAG context injected per-turn)
        self._base_system_prompt = build_system_prompt(lead, is_inbound=is_inbound)
        # Keep .system_prompt for backward compat (streaming path uses it)
        self.system_prompt = self._base_system_prompt
        # Track talk ratio
        self.ai_word_count = 0
        self.user_word_count = 0
        # Track competitor mentions for sales intelligence
        self.competitor_mentions: list[dict] = []
    
    def add_exchange(self, user_text: str, ai_text: str):
        """Record a user/AI exchange in history AND word counts."""
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": ai_text})
        self.user_word_count += len(user_text.split())
        self.ai_word_count += len(ai_text.split())

    def add_ai_message(self, ai_text: str):
        """Record an AI-only message (e.g. opening greeting) with word count."""
        self.history.append({"role": "assistant", "content": ai_text})
        self.ai_word_count += len(ai_text.split())

    def chat(self, user_message: str) -> str:
        """
        Synchronous chat with RAG context injection.

        Pipeline:
        1. Detects competitor mentions for sales intelligence
        2. Retrieves relevant past learnings from vector DB (~5-20ms)
        3. Injects RAG context into system prompt
        4. Enforces strict 30/70 talk ratio
        5. Validates response completeness (retries if broken)
        """
        self.history.append({"role": "user", "content": user_message})
        self.user_word_count += len(user_message.split())
        history_len_before = len(self.history)

        # Real-time competitor detection
        try:
            from sales_intelligence import detect_competitor_mention
            competitor = detect_competitor_mention(user_message)
            if competitor:
                self.competitor_mentions.append(competitor)
                log.info("Competitor detected: %s", competitor["brand"])
        except Exception:
            pass

        # RAG retrieval — fetch relevant past learnings (~5-20ms)
        rag_context = ""
        try:
            from memory_learning import get_relevant_context
            rag_context = get_relevant_context(user_message, max_chars=600)
            if rag_context:
                log.info("RAG context injected (%d chars)", len(rag_context))
        except Exception as e:
            log.warning("RAG retrieval failed (non-blocking): %s", e)

        # Build system prompt with RAG context (or use base if no RAG)
        system_prompt = self._base_system_prompt
        if rag_context:
            system_prompt = build_system_prompt(
                self.lead, is_inbound=self.is_inbound, rag_context=rag_context
            )

        # Hybrid model routing
        complexity = classify_query_complexity(user_message)
        if complexity == "fast":
            model = config.GROQ_FAST_MODEL
            max_tokens = config.LLM_MAX_TOKENS_FAST
        else:
            model = config.GROQ_SMART_MODEL
            max_tokens = config.LLM_MAX_TOKENS_SMART

        # Strict 30/70 talk ratio enforcement
        if self.ai_word_count > 0 and self.user_word_count > 0:
            ai_ratio = self.ai_word_count / (self.ai_word_count + self.user_word_count)
            if ai_ratio > config.TALK_RATIO_HARD_LIMIT:
                # Force very short response — just a question
                max_tokens = config.LLM_MIN_TOKENS_FLOOR
                log.info("Talk ratio HIGH (%.0f%%) — forcing question-only response", ai_ratio * 100)
            elif ai_ratio > config.TALK_RATIO_TARGET:
                max_tokens = min(max_tokens, config.LLM_MIN_TOKENS_FLOOR)
                log.info("Talk ratio above target (%.0f%%) — shorter response", ai_ratio * 100)

        ai_reply = None
        retries = 0
        max_retries = config.MAX_RESPONSE_RETRIES

        while retries <= max_retries:
            try:
                client = _get_groq_client()
                trimmed_history = self.history[-8:] if len(self.history) > 8 else self.history

                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "system", "content": system_prompt}] + trimmed_history,
                    temperature=0.7,
                    max_tokens=max_tokens,
                )
                ai_reply = response.choices[0].message.content

                # Validate response completeness
                validated = self._validate_response(ai_reply)

                # If validation changed response significantly and we have retries left
                if validated != ai_reply and retries < max_retries:
                    log.info("Response incomplete, retrying with more tokens (attempt %d)", retries + 1)
                    max_tokens = min(max_tokens + 50, 200)
                    retries += 1
                    ai_reply = validated
                    continue

                ai_reply = validated
                break

            except Exception as exc:
                log.error("Groq chat failed: %s", exc)
                ai_reply = "Ji, main samajh rahi hoon. Aap bataaiye?"
                break

        # Only append if history hasn't been modified by timeout fallback
        if len(self.history) == history_len_before:
            self.history.append({"role": "assistant", "content": ai_reply})
            self.ai_word_count += len(ai_reply.split())
        return ai_reply
    
    @staticmethod
    def _validate_response(text: str) -> str:
        """
        Response validator — ensures AI never sends incomplete sentences.
        
        Checks:
        1. Not empty
        2. No trailing JSON fragments or markdown artifacts
        3. Enforces female Hindi grammar (male→female corrections)
        4. Sentence ends with proper Hindi/Hinglish ending
        5. If incomplete → appends natural continuation
        """
        if not text or not text.strip():
            return "Ji, main samajh rahi hoon. Aap bataaiye?"
        
        text = text.strip()
        
        # Remove any trailing incomplete JSON blocks
        text = re.sub(r'\{[^}]*$', '', text).strip()
        
        # Remove markdown artifacts
        text = re.sub(r'\*+', '', text).strip()
        
        # Remove any stray quotes or brackets
        text = re.sub(r'[\[\]{}]', '', text).strip()
        
        # If text became empty after cleanup, return fallback
        if not text:
            return "Ji, main samajh rahi hoon. Aap bataaiye?"
        
        # Enforce female grammar — fix common male forms
        male_to_female = {
            r'\bkarunga\b': 'karungi',
            r'\bsakta hoon\b': 'sakti hoon',
            r'\bbol raha hoon\b': 'bol rahi hoon',
            r'\bbhejunga\b': 'bhejungi',
            r'\bdunga\b': 'doongi',
            r'\bsamajh raha hoon\b': 'samajh rahi hoon',
            r'\bbata raha hoon\b': 'bata rahi hoon',
            r'\bkar raha hoon\b': 'kar rahi hoon',
            r'\bjaunga\b': 'jaungi',
            r'\blunga\b': 'lungi',
            r'\bdekhta hoon\b': 'dekhti hoon',
            r'\bkarta hoon\b': 'karti hoon',
        }
        for pattern, replacement in male_to_female.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Check if response ends with proper sentence ending
        sentence_enders = (
            '?', '!', '.', '।',
            'hai', 'hain', 'hoon', 'ho',
            'ga', 'gi', 'ge', 'gaa', 'gii',
            'ye', 'lo', 'do', 'na', 'le',
            'karein', 'kariye', 'bataaiye', 'dijiye',
            'sakte', 'sakti', 'sakta',
            'hogi', 'hoga',
            'dein', 'lein', 'rahega', 'rahegi',
            'karungi', 'deti', 'doongi', 'bhejungi',
            'dhanyavaad', 'shukriya',
            'lijiye', 'aayiye', 'dekhiye',
            'milegi', 'milega', 'jayega', 'jayegi',
            'chahiye', 'padega', 'padegi',
            'rahi', 'raha',
        )
        
        last_word = text.rstrip('?.!।').split()[-1].lower() if text.split() else ''
        ends_properly = (
            text[-1] in '?.!।'
            or last_word in sentence_enders
            or len(text.split()) >= 10  # 10+ words is likely a complete thought
        )
        
        if not ends_properly:
            # Response doesn't end properly — append natural continuation
            text = text + " — aap bataaiye?"
        
        return text
    
    def chat_streaming(self, user_message: str):
        """
        Streaming chat with RAG context — yields tokens as they arrive.
        Validates complete response and enforces female grammar.
        """
        self.history.append({"role": "user", "content": user_message})
        self.user_word_count += len(user_message.split())

        # RAG retrieval
        rag_context = ""
        try:
            from memory_learning import get_relevant_context
            rag_context = get_relevant_context(user_message, max_chars=600)
        except Exception:
            pass

        system_prompt = self._base_system_prompt
        if rag_context:
            system_prompt = build_system_prompt(
                self.lead, is_inbound=self.is_inbound, rag_context=rag_context
            )

        complexity = classify_query_complexity(user_message)
        if complexity == "fast":
            model = config.GROQ_FAST_MODEL
            max_tokens = config.LLM_MAX_TOKENS_FAST
        else:
            model = config.GROQ_SMART_MODEL
            max_tokens = config.LLM_MAX_TOKENS_SMART

        if self.ai_word_count > 0 and self.user_word_count > 0:
            ai_ratio = self.ai_word_count / (self.ai_word_count + self.user_word_count)
            if ai_ratio > config.TALK_RATIO_HARD_LIMIT:
                max_tokens = config.LLM_MIN_TOKENS_FLOOR
            elif ai_ratio > config.TALK_RATIO_TARGET:
                max_tokens = min(max_tokens, config.LLM_MIN_TOKENS_FLOOR)

        try:
            client = _get_groq_client()
            trimmed_history = self.history[-8:] if len(self.history) > 8 else self.history

            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}] + trimmed_history,
                temperature=0.7,
                max_tokens=max_tokens,
                stream=True,
            )

            full_reply = ""
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_reply += delta.content
                    yield delta.content

            # Validate the complete response
            validated = self._validate_response(full_reply)
            if validated != full_reply:
                # Only yield suffix if validation APPENDED text (not mid-text edits)
                # Mid-text changes (grammar fixes, markdown removal) are stored in
                # history but not re-streamed to avoid garbled output
                if validated.startswith(full_reply):
                    suffix = validated[len(full_reply):]
                    if suffix:
                        yield suffix
                full_reply = validated

            self.history.append({"role": "assistant", "content": full_reply})
            self.ai_word_count += len(full_reply.split())

        except Exception as exc:
            log.error("Groq streaming failed: %s", exc)
            fallback = "Ji, samajh rahi hoon. Aap bataaiye?"
            self.history.append({"role": "assistant", "content": fallback})
            yield fallback
    
    def get_full_transcript(self) -> str:
        lines = []
        for msg in self.history:
            role = "Priya (AI)" if msg["role"] == "assistant" else "Customer"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)
    
    def get_talk_ratio(self) -> dict:
        """Return current talk ratio stats."""
        total = self.ai_word_count + self.user_word_count
        if total == 0:
            return {"ai_ratio": 0, "user_ratio": 0}
        return {
            "ai_ratio": round(self.ai_word_count / total, 2),
            "user_ratio": round(self.user_word_count / total, 2),
        }
    
    def analyze_call(self) -> dict:
        """Ask Groq to analyze full conversation and extract structured data."""
        transcript = self.get_full_transcript()
        if not transcript.strip():
            return {}
        
        today = datetime.now().strftime("%Y-%m-%d %A")

        prompt = f"""Analyze this sales call from {config.BUSINESS_NAME}. TODAY: {today}

TRANSCRIPT:
{transcript}

Return ONLY valid JSON:
{{
  "customer_name": "",
  "whatsapp_number": "",
  "interested_model": "",
  "budget_range": "",
  "temperature": "hot/warm/cold/dead",
  "objection": "",
  "next_followup_date": "YYYY-MM-DD HH:MM or null (use 10:00 default, never 00:00)",
  "next_action": "schedule_visit/send_whatsapp/followup_call/transfer_agent/close_dead",
  "convert_to_sale": false,
  "assign_to_salesperson": false,
  "sentiment": "positive/neutral/negative",
  "call_outcome": "interested/not_interested/callback_requested/converted/no_answer/dead",
  "family_upsell_note": "",
  "notes": "brief summary",
  "purchase_outcome": "converted/lost_to_codealer/lost_to_competitor/not_purchased/unknown",
  "competitor_brand": "",
  "loss_reason": "",
  "feedback_notes": ""
}}"""
        
        try:
            client = _get_groq_client()
            r = client.chat.completions.create(
                model=config.GROQ_FAST_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=400,
            )
            raw = r.choices[0].message.content.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            return json.loads(raw)
        except Exception as e:
            print(f"[Agent] Call analysis failed: {e}")
            return {"temperature": "warm", "next_action": "followup_call", "notes": "Analysis failed"}


def get_opening_message(lead: dict = None, is_inbound: bool = False) -> str:
    """Generate the first thing AI says when call connects."""
    if is_inbound:
        return "Namaste! Main Priya, Shubham Motors se. Kaise madad karoon?"
    
    name = lead.get("name", "") if lead else ""
    model = lead.get("interested_model", "") if lead else ""
    call_count = int(lead.get("call_count", 0)) if lead else 0

    if call_count >= 1:
        if name:
            return f"Namaste {name} ji! Priya Shubham Motors se. Kya bike le li ya abhi soch rahe hain?"
        return "Namaste! Priya Shubham Motors se. Follow up tha — bike le li ya dekh rahe hain?"

    if name and model:
        return f"Namaste {name} ji! Priya Shubham Motors se — {model} ke liye 1 min baat karein?"
    elif name:
        return f"Namaste {name} ji! Priya Shubham Motors se. Hero bike ke liye baat kar sakte hain?"
    return "Namaste! Priya Shubham Motors se. Bike enquiry ke liye call kar rahi thi — free hain?"
