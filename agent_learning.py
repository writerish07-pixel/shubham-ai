"""
agent_learning.py — Self-learning AI sales agent with RAG and sales psychology.

🔥 SELF-LEARNING ADDED: Extends agent_optimized.py with:
- RAG injection: retrieves relevant past learnings before generating response
- Sales psychology: scarcity, urgency, social proof, SPIN selling
- Competitor handling: detects and counters competitor mentions in real-time
- Strict 30/70 talk ratio enforcement
- Learning from successful/failed sales techniques
- Document knowledge: uses pricing/offers from ingested PDFs/images

Architecture:
- build_system_prompt_learning() injects RAG context into system prompt
- ConversationManagerLearning extends ConversationManager with RAG
- All original agent_optimized.py functionality preserved
- Zero additional latency: RAG retrieval is ~5-20ms (FAISS in-memory)
"""
import json
import logging
import re
from datetime import datetime

from groq import Groq

import config_learning as config
from scraper import get_bike_catalog, format_catalog_for_ai
from sheets_manager import get_active_offers

log = logging.getLogger("shubham-ai.agent-learning")


# ── Singleton Groq client ────────────────────────────────────────────────────
_groq_client = None


def _get_groq_client() -> Groq:
    global _groq_client
    if _groq_client is None:
        if not config.GROQ_API_KEY:
            raise RuntimeError("GROQ_API_KEY is not configured")
        _groq_client = Groq(api_key=config.GROQ_API_KEY)
    return _groq_client


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Enhanced hybrid model router with competitor detection
# ══════════════════════════════════════════════════════════════════════════════

SIMPLE_PATTERNS = [
    r"^(namaste|hello|hi|hey|haan|ok|theek|accha|ji|bilkul|sahi)\b",
    r"^(kab|kahan|kitna|kitne|kya|kaun|kyun)\b",
    r"^(haan|nahi|no|yes|ha|na)\b",
    r"(price|daam|kimat|emi|loan|finance|test ride|address|timing|busy|baad)",
]
_simple_re = re.compile("|".join(SIMPLE_PATTERNS), re.IGNORECASE)


def classify_query_complexity(text: str) -> str:
    """
    Classify query complexity for hybrid model routing.
    Returns 'fast' or 'smart'.

    🔥 SELF-LEARNING ADDED: Also routes to 'smart' when competitor is mentioned
    (needs better persuasion and counter-arguments).
    """
    text_clean = text.strip().lower()

    if len(text_clean) < 30 and _simple_re.search(text_clean):
        return "fast"

    if len(text_clean) > 80:
        return "smart"

    # 🔥 SELF-LEARNING ADDED: Competitor mentions always need smart model
    # Non-brand indicators are safe for substring matching (no Hindi conflicts)
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

    # 🔥 FIX: Use word-boundary regex for brand names to avoid false positives
    # (e.g. "ola" in "bola", "jawa" in "jawab" — common Hindi words).
    from sales_intelligence import _COMPETITOR_BRAND_RE
    if _COMPETITOR_BRAND_RE.search(text_clean):
        return "smart"

    return "fast"


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Enhanced system prompt with RAG + sales psychology
# ══════════════════════════════════════════════════════════════════════════════

def build_system_prompt_learning(lead: dict = None, is_inbound: bool = True,
                                  rag_context: str = "") -> str:
    """
    Build system prompt with RAG context injection and sales psychology.

    🔥 SELF-LEARNING ADDED:
    - Injects relevant past learnings from vector DB
    - Adds sales psychology techniques (scarcity, urgency, social proof)
    - Adds competitor handling strategies
    - Enforces strict 30/70 talk ratio
    """
    catalog_text = format_catalog_for_ai(get_bike_catalog())
    offers = get_active_offers()
    offer_text = ""
    if offers:
        offer_text = "\n=== CURRENT OFFERS ===\n"
        for o in offers[:3]:
            offer_text += f"- {o.get('title', '')}: {o.get('description', '')}"
            if o.get("valid_till"):
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
            lead_context += (
                "FOLLOW-UP: Ask if they purchased. "
                "If yes from us->congrats. If no->continue sale.\n"
            )
            last_transcript = lead.get("last_transcript", "")
            if last_transcript:
                lead_context += f"Last call summary: {last_transcript[-200:]}\n"

    call_mode = ""
    if not is_inbound:
        call_mode = (
            "\nOUTBOUND MODE: You called them. Confirm they can talk. "
            "Be direct. Goal: showroom visit or callback time.\n"
        )

    # 🔥 SELF-LEARNING ADDED: RAG context block
    rag_block = ""
    if rag_context:
        rag_block = f"""
=== PAST LEARNINGS (use these to give better answers) ===
{rag_context}
"""

    # 🔥 SELF-LEARNING ADDED: Enhanced system prompt with sales psychology
    return f"""You are Priya — FEMALE sales rep at {config.BUSINESS_NAME}, Hero MotoCorp dealer, {config.BUSINESS_CITY}.

GENDER: Always use FEMALE Hindi grammar (karungi, bol rahi hoon, sakti hoon, bhejungi).

=== RESPONSE RULES (CRITICAL — NEVER BREAK) ===
- MAX 1-2 sentences, under 20 words
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


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Learning-enhanced ConversationManager
# ══════════════════════════════════════════════════════════════════════════════

class ConversationManagerLearning:
    """
    Enhanced conversation manager with self-learning capabilities.

    🔥 SELF-LEARNING ADDED:
    - RAG context injection before every response
    - Real-time competitor detection
    - Strict 30/70 talk ratio enforcement
    - Conversation history for post-call learning
    """

    def __init__(self, lead: dict = None, is_inbound: bool = True):
        self.lead = lead
        self.history: list[dict] = []
        self.ai_word_count = 0
        self.user_word_count = 0
        self.is_inbound = is_inbound
        # 🔥 SELF-LEARNING ADDED: Track competitor mentions for intelligence
        self.competitor_mentions: list[dict] = []
        # Build initial system prompt (without RAG — that comes per-turn)
        self._base_system_prompt = build_system_prompt_learning(
            lead, is_inbound=is_inbound
        )

    def add_exchange(self, user_text: str, ai_text: str):
        """Record a user/AI exchange in history AND word counts."""
        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": ai_text})
        self.user_word_count += len(user_text.split())
        self.ai_word_count += len(ai_text.split())

    def add_ai_message(self, ai_text: str):
        """Record an AI-only message with word count."""
        self.history.append({"role": "assistant", "content": ai_text})
        self.ai_word_count += len(ai_text.split())

    def chat(self, user_message: str) -> str:
        """
        🔥 SELF-LEARNING ADDED: Chat with RAG context injection.

        Before generating a response:
        1. Retrieves relevant past learnings from vector DB (~5-20ms)
        2. Detects competitor mentions for real-time intelligence
        3. Injects RAG context into system prompt
        4. Enforces strict 30/70 talk ratio
        """
        self.history.append({"role": "user", "content": user_message})
        self.user_word_count += len(user_message.split())
        history_len_before = len(self.history)

        # 🔥 SELF-LEARNING ADDED: Real-time competitor detection
        from sales_intelligence import detect_competitor_mention
        competitor = detect_competitor_mention(user_message)
        if competitor:
            self.competitor_mentions.append(competitor)
            log.info("Competitor detected: %s", competitor["brand"])

        # 🔥 SELF-LEARNING ADDED: RAG retrieval — fetch relevant past learnings
        rag_context = ""
        try:
            from memory_learning import get_relevant_context
            rag_context = get_relevant_context(user_message, max_chars=600)
            if rag_context:
                log.info("RAG context injected (%d chars)", len(rag_context))
        except Exception as e:
            log.warning("RAG retrieval failed (non-blocking): %s", e)

        # Build system prompt with RAG context
        system_prompt = self._base_system_prompt
        if rag_context:
            system_prompt = build_system_prompt_learning(
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

        # 🔥 SELF-LEARNING ADDED: Strict 30/70 enforcement
        if self.ai_word_count > 0 and self.user_word_count > 0:
            ai_ratio = self.ai_word_count / (self.ai_word_count + self.user_word_count)
            if ai_ratio > 0.35:
                max_tokens = min(max_tokens, 25)  # Force very short response
                log.info("Talk ratio high (%.0f%%) — forcing shorter response", ai_ratio * 100)

        try:
            client = _get_groq_client()
            trimmed_history = self.history[-6:] if len(self.history) > 6 else self.history

            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system_prompt}] + trimmed_history,
                temperature=0.6,
                max_tokens=max_tokens,
            )
            ai_reply = response.choices[0].message.content
        except Exception as exc:
            log.error("Groq chat failed: %s", exc)
            ai_reply = "Ji, main samajh rahi hoon. Thoda aur detail dein?"

        if len(self.history) == history_len_before:
            self.history.append({"role": "assistant", "content": ai_reply})
            self.ai_word_count += len(ai_reply.split())
        return ai_reply

    def chat_streaming(self, user_message: str):
        """
        🔥 SELF-LEARNING ADDED: Streaming chat with RAG context.
        Yields tokens as they arrive from Groq.
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
            system_prompt = build_system_prompt_learning(
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
                max_tokens = min(max_tokens, 25)

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
            log.error("Call analysis failed: %s", e)
            return {
                "temperature": "warm",
                "next_action": "followup_call",
                "notes": "Analysis failed",
            }


# ══════════════════════════════════════════════════════════════════════════════
# 🔥 SELF-LEARNING ADDED: Opening messages (same as optimized, kept for compat)
# ══════════════════════════════════════════════════════════════════════════════

def get_opening_message(lead: dict = None, is_inbound: bool = False) -> str:
    """Generate the first thing AI says when call connects."""
    if is_inbound:
        return "Namaste! Main Priya, Shubham Motors se. Kaise madad karoon?"

    name = lead.get("name", "") if lead else ""
    model = lead.get("interested_model", "") if lead else ""
    call_count = int(lead.get("call_count", 0)) if lead else 0

    if call_count >= 1:
        if name:
            return (
                f"Namaste {name} ji! Priya Shubham Motors se. "
                "Kya bike le li ya abhi soch rahe hain?"
            )
        return (
            "Namaste! Priya Shubham Motors se. "
            "Follow up tha — bike le li ya dekh rahe hain?"
        )

    if name and model:
        return (
            f"Namaste {name} ji! Priya Shubham Motors se — "
            f"{model} ke liye 1 min baat karein?"
        )
    elif name:
        return (
            f"Namaste {name} ji! Priya Shubham Motors se. "
            "Hero bike ke liye baat kar sakte hain?"
        )
    return (
        "Namaste! Priya Shubham Motors se. "
        "Bike enquiry ke liye call kar rahi thi — free hain?"
    )
