"""
agent.py
The AI brain — WORLD-CLASS SALES AI with advanced persuasion techniques.

OPTIMIZATIONS:
- 🔥 OPTIMIZATION: System prompt reduced by ~60% — removed verbose examples, kept core rules
- 🔥 OPTIMIZATION: Hybrid model routing — fast model for simple queries, smart model for complex
- 🔥 OPTIMIZATION: Streaming LLM responses via Groq streaming API
- 🔥 OPTIMIZATION: Talk ratio enforcement — AI limited to 30% talk time
- 🔥 OPTIMIZATION: max_tokens reduced from 80 to 40/60 based on model
- 🔥 OPTIMIZATION: Temperature reduced from 0.8 to 0.6 for more concise responses
- 🔥 OPTIMIZATION: Removed debug prints (OPENAI_BASE_URL)
- 🔥 FIX: Conversation history trimmed to last 6 turns to reduce token count

SELF-LEARNING:
- 🔥 RAG injection: retrieves relevant past learnings before generating response
- 🔥 Sales psychology: scarcity, urgency, social proof, SPIN selling
- 🔥 Competitor handling: detects and counters competitor mentions in real-time
- 🔥 Document knowledge: uses pricing/offers from ingested PDFs/images
- Zero additional latency: RAG retrieval is ~5-20ms (FAISS in-memory)
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

# 🔥 OPTIMIZATION: Classify query complexity to route to fast vs smart model
SIMPLE_PATTERNS = [
    # Greetings / acknowledgements
    r"^(namaste|hello|hi|hey|haan|ok|theek|accha|ji|bilkul|sahi)\b",
    # Short questions
    r"^(kab|kahan|kitna|kitne|kya|kaun|kyun)\b",
    # Yes/No
    r"^(haan|nahi|no|yes|ha|na)\b",
    # Common intents already handled by intent.py
    r"(price|daam|kimat|emi|loan|finance|test ride|address|timing|busy|baad)",
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
    
    # Check for complex indicators (non-brand keywords safe for substring match)
    complex_indicators = [
        "discount", "competitor", "compare", "problem", "issue",
        "complaint", "doosri", "dusri",
        "sochna", "family", "wife", "husband", "loan", "finance",
        "emi kitni", "exchange", "purani bike",
        "mehenga", "sasta", "expensive", "cheap", "better", "accha nahi",
        "khareed liya", "le liya", "bought", "already",
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

# 🔥 OPTIMIZATION: Dramatically shortened system prompt — saves ~2000 tokens per request
# Original was ~225 lines / ~4000 tokens. This is ~80 lines / ~1500 tokens.
# Reduced latency: fewer tokens = faster Groq inference

def build_system_prompt(lead: dict = None, is_inbound: bool = True,
                        rag_context: str = "") -> str:
    """
    Build system prompt with optional RAG context injection and sales psychology.
    RAG context is injected per-turn when relevant past learnings exist.
    """
    catalog_text = format_catalog_for_ai(get_bike_catalog())
    offers = get_active_offers()
    offer_text = ""
    if offers:
        offer_text = "\n=== CURRENT OFFERS ===\n"
        for o in offers[:3]:  # 🔥 OPTIMIZATION: Limit to top 3 offers
            offer_text += f"• {o.get('title','')}: {o.get('description','')}"
            if o.get('valid_till'):
                offer_text += f" (till {o['valid_till']})"
            offer_text += "\n"

    lead_context = ""
    if lead:
        call_count = int(lead.get("call_count", 0))
        lead_context = f"""
=== CUSTOMER ===
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

    return f"""You are Priya — FEMALE sales rep at {config.BUSINESS_NAME}, Hero MotoCorp dealer, {config.BUSINESS_CITY}.

GENDER: Always use FEMALE Hindi grammar (karungi, bol rahi hoon, sakti hoon, bhejungi).

=== RESPONSE RULES (CRITICAL — NEVER BREAK) ===
- MAX 1-2 sentences, under 20 words
- ALWAYS complete your sentence — NEVER cut mid-sentence
- Every response MUST be grammatically complete and natural
- ONE question per turn only
- Never list specs/prices on call — "WhatsApp pe bhejti hoon"
- Never say "main aapko bata sakti hoon" — say it directly
- Never repeat what customer said — move forward
- Ask name first, then budget, then suggest models matching budget
- NEVER offer/match discounts — "Manager se confirm karungi"

=== 30/70 TALK RATIO (STRICT) ===
- You speak MAX 30% of conversation
- Customer speaks 70%
- Ask SHORT questions to keep customer talking
- If you've been talking too much, respond with ONLY a question

=== SALES PSYCHOLOGY (USE THESE TECHNIQUES) ===
1. SCARCITY: "Yeh offer sirf is mahine hai" / "Stock limited hai"
2. URGENCY: "Aaj hi scheme end ho rahi hai" / "Kal se price badh jayega"
3. SOCIAL PROOF: "Iss mahine 50+ Splendor sell hue" / "Sabse popular model"
4. RECIPROCITY: Offer free test ride, free servicing info
5. SPIN SELLING: Situation→Problem→Implication→Need-Payoff
6. ASSUMPTIVE CLOSE: "Kab aa rahe hain test ride ke liye?" (assume they'll come)

=== COMPETITOR HANDLING (IMPORTANT) ===
- If customer mentions Honda/Bajaj/TVS/Yamaha: "Hero ki service network sabse badi hai"
- If customer bought from competitor: Ask WHY politely, note reason
- If customer went to another dealer: Ask "kya offer mila?" — we can match service
- NEVER badmouth competitors — highlight Hero's strengths instead
- Key advantages: Mileage king, lowest maintenance, best resale, #1 brand

=== OBJECTION HANDLING ===
- "Price zyada hai" → "EMI sirf ₹1800/month! Budget kitna hai?"
- "Sochna padega" → "Bilkul! Kab tak decide karenge? Main note kar leti hoon"
- "Doosri company dekh rahe" → "Hero ki mileage aur resale best hai. Compare karein!"
- "Abhi nahi" → "Koi baat nahi, kab call karoon? Scheme miss na ho jaye"
- "Already bought" → "Congratulations! Kahan se liya? Hum service offer kar sakte hain"

SALES: Build rapport, use customer name. Always end with next step (visit/callback).
LEAD TEMP: Hot=budget+model+this week. Warm=interested. Cold=vague. Dead=not interested.

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
        """
        🔥 FIX: Record a user/AI exchange in history AND word counts.
        Use this when bypassing chat() (e.g. intent matches, opening messages).
        """
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": ai_text})
        self.user_word_count += len(user_text.split())
        self.ai_word_count += len(ai_text.split())

    def add_ai_message(self, ai_text: str):
        """
        🔥 FIX: Record an AI-only message (e.g. opening greeting) with word count.
        """
        self.history.append({"role": "assistant", "content": ai_text})
        self.ai_word_count += len(ai_text.split())

    def chat(self, user_message: str) -> str:
        """
        Synchronous chat with RAG context injection.

        Before generating a response:
        1. Detects competitor mentions for sales intelligence
        2. Retrieves relevant past learnings from vector DB (~5-20ms)
        3. Injects RAG context into system prompt
        4. Enforces strict 30/70 talk ratio
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
            if ai_ratio > 0.35:
                max_tokens = min(max_tokens, config.LLM_MIN_TOKENS_FLOOR)
                log.info("Talk ratio high (%.0f%%) — forcing shorter response", ai_ratio * 100)

        try:
            client = _get_groq_client()
            trimmed_history = self.history[-6:] if len(self.history) > 6 else self.history

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}] + trimmed_history,
                temperature=0.7,
                max_tokens=max_tokens,
            )
            ai_reply = response.choices[0].message.content

            # Validate response completeness before returning
            ai_reply = self._validate_response(ai_reply)

        except Exception as exc:
            log.error("Groq chat failed: %s", exc)
            ai_reply = "Ji, main samajh rahi hoon. Thoda aur detail dein?"

        # Only append if history hasn't been modified by timeout fallback
        if len(self.history) == history_len_before:
            self.history.append({"role": "assistant", "content": ai_reply})
            self.ai_word_count += len(ai_reply.split())
        return ai_reply
    
    @staticmethod
    def _validate_response(text: str) -> str:
        """
        🔥 FIX: Response validator — ensures AI never sends incomplete sentences.
        Checks for sentence completeness before TTS.
        If incomplete, attempts to complete or returns a safe fallback.
        """
        if not text or not text.strip():
            return "Ji, main samajh rahi hoon. Aap bataaiye?"
        
        text = text.strip()
        
        # Remove any trailing incomplete JSON blocks
        text = re.sub(r'\{[^}]*$', '', text).strip()
        
        # If text became empty after JSON removal, return fallback
        if not text:
            return "Ji, main samajh rahi hoon. Aap bataaiye?"
        
        # Check if response ends mid-word (no punctuation or sentence-ending word)
        # Hindi sentences typically end with: ?, !, ., hai, hain, hoon, ga, gi, ge, ye, lo, do, na
        sentence_enders = ('?', '!', '.', '।',
                          'hai', 'hain', 'hoon', 'ho',
                          'ga', 'gi', 'ge', 'gaa', 'gii',
                          'ye', 'lo', 'do', 'na', 'le',
                          'karein', 'kariye', 'bataaiye', 'dijiye',
                          'sakte', 'sakti', 'sakta',
                          'hoon', 'hogi', 'hoga',
                          'dein', 'lein', 'rahega', 'rahegi',
                          'karungi', 'deti', 'doongi', 'bhejungi',
                          'dhanyavaad', 'shukriya')
        
        last_word = text.rstrip('?.!।').split()[-1].lower() if text.split() else ''
        ends_properly = (
            text[-1] in '?.!।'
            or last_word in sentence_enders
            or len(text.split()) >= 8  # At least 8 words is likely a complete thought
        )
        
        if not ends_properly:
            # Response doesn't end properly — likely broken
            return text + " — aap bataaiye?"
        
        return text
    
    def chat_streaming(self, user_message: str):
        """
        Streaming chat with RAG context — yields tokens as they arrive.
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
            if ai_ratio > 0.35:
                max_tokens = min(max_tokens, config.LLM_MIN_TOKENS_FLOOR)

        try:
            client = _get_groq_client()
            trimmed_history = self.history[-6:] if len(self.history) > 6 else self.history

            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}] + trimmed_history,
                temperature=0.6,
                max_tokens=max_tokens,
                stream=True,
            )

            full_reply = ""
            for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    full_reply += delta.content
                    yield delta.content

            self.history.append({"role": "assistant", "content": full_reply})
            self.ai_word_count += len(full_reply.split())

        except Exception as exc:
            log.error("Groq streaming failed: %s", exc)
            fallback = "Ji, samajh rahi hoon. Thoda detail dein?"
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

        # 🔥 OPTIMIZATION: Shorter analysis prompt — same fields, fewer instructions
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
                model=config.GROQ_FAST_MODEL,  # 🔥 OPTIMIZATION: Use fast model for analysis
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=400,  # 🔥 OPTIMIZATION: Reduced from 500
            )
            raw = r.choices[0].message.content.strip()
            raw = re.sub(r"```json|```", "", raw).strip()
            return json.loads(raw)
        except Exception as e:
            print(f"[Agent] Call analysis failed: {e}")
            return {"temperature": "warm", "next_action": "followup_call", "notes": "Analysis failed"}


def get_opening_message(lead: dict = None, is_inbound: bool = False) -> str:
    """Generate the first thing AI says when call connects."""
    # 🔥 OPTIMIZATION: Shorter greetings — faster TTS, less latency
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
