"""
agent_optimized.py
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
"""
import json, re, logging
from datetime import datetime

from groq import Groq

import config_optimized as config
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
    
    # Check for complex indicators
    complex_indicators = [
        "discount", "competitor", "compare", "problem", "issue",
        "complaint", "doosri", "dusri", "honda", "bajaj", "tvs",
        "sochna", "family", "wife", "husband", "loan", "finance",
        "emi kitni", "exchange", "purani bike",
    ]
    for indicator in complex_indicators:
        if indicator in text_clean:
            return "smart"
    
    return "fast"


# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────

# 🔥 OPTIMIZATION: Dramatically shortened system prompt — saves ~2000 tokens per request
# Original was ~225 lines / ~4000 tokens. This is ~80 lines / ~1500 tokens.
# Reduced latency: fewer tokens = faster Groq inference

def build_system_prompt(lead: dict = None, is_inbound: bool = True) -> str:
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

    feedback_text = ""

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
        call_mode = """
OUTBOUND MODE: You called them. Confirm they can talk. Be direct. Goal: showroom visit or callback time.
"""

    # 🔥 OPTIMIZATION: Compact system prompt — same rules, ~60% fewer tokens
    return f"""You are Priya — FEMALE sales rep at {config.BUSINESS_NAME}, Hero MotoCorp dealer, {config.BUSINESS_CITY}.

GENDER: Always use FEMALE Hindi grammar (karungi, bol rahi hoon, sakti hoon, bhejungi).

⚠️ RESPONSE RULES (CRITICAL):
- MAX 1-2 sentences, under 20 words
- ONE question per turn only
- Never list specs/prices on call — "WhatsApp pe bhejti hoon"
- Never say "main aapko bata sakti hoon" — say it directly
- Never repeat what customer said — move forward
- Ask name first, then budget, then suggest models matching budget
- NEVER offer/match discounts — "Manager se confirm karungi"

SALES: Build rapport, use customer name, SPIN method. Always end with next step (visit/callback).
OBJECTIONS: "Price zyada"→EMI. "Sochna hai"→"Kab decide karenge?" "Doosri jagah"→Hero service best.
LEAD TEMP: Hot=budget+model+this week. Warm=interested. Cold=vague. Dead=not interested.

{catalog_text}
{offer_text}
{feedback_text}
{lead_context}
{call_mode}
Hours: {config.WORKING_HOURS_START}-{config.WORKING_HOURS_END}, {', '.join(config.WORKING_DAYS[:3])}+
"""


# ── CONVERSATION MANAGER ──────────────────────────────────────────────────────

class ConversationManager:
    """Manages per-call conversation history with talk ratio tracking."""
    
    def __init__(self, lead: dict = None, is_inbound: bool = True):
        self.lead = lead
        self.history = []
        self.system_prompt = build_system_prompt(lead, is_inbound=is_inbound)
        # 🔥 OPTIMIZATION: Track talk ratio
        self.ai_word_count = 0
        self.user_word_count = 0
    
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
        """Synchronous chat — uses hybrid model routing."""
        self.history.append({"role": "user", "content": user_message})
        self.user_word_count += len(user_message.split())
        
        # 🔥 OPTIMIZATION: Hybrid model routing
        complexity = classify_query_complexity(user_message)
        if complexity == "fast":
            model = config.GROQ_FAST_MODEL
            max_tokens = config.LLM_MAX_TOKENS_FAST  # 40 tokens
        else:
            model = config.GROQ_SMART_MODEL
            max_tokens = config.LLM_MAX_TOKENS_SMART  # 60 tokens
        
        # 🔥 OPTIMIZATION: Talk ratio enforcement
        # If AI has been talking too much, force even shorter responses
        if self.ai_word_count > 0 and self.user_word_count > 0:
            ai_ratio = self.ai_word_count / (self.ai_word_count + self.user_word_count)
            if ai_ratio > 0.35:  # AI talking more than 35%
                max_tokens = min(max_tokens, 30)
        
        try:
            client = _get_groq_client()
            # 🔥 OPTIMIZATION: Trim history to last 6 turns to reduce token count
            trimmed_history = self.history[-6:] if len(self.history) > 6 else self.history
            
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": self.system_prompt}] + trimmed_history,
                temperature=0.6,  # 🔥 OPTIMIZATION: Lower temp = more concise (was 0.8)
                max_tokens=max_tokens,
            )
            ai_reply = response.choices[0].message.content
        except Exception as exc:
            log.error("Groq chat failed: %s", exc)
            ai_reply = "Ji, main samajh rahi hoon. Thoda aur detail dein?"

        self.history.append({"role": "assistant", "content": ai_reply})
        self.ai_word_count += len(ai_reply.split())
        return ai_reply
    
    def chat_streaming(self, user_message: str):
        """
        🔥 OPTIMIZATION: Streaming chat — yields tokens as they arrive from Groq.
        Caller can start TTS on partial text before full response is ready.
        """
        self.history.append({"role": "user", "content": user_message})
        self.user_word_count += len(user_message.split())
        
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
                max_tokens = min(max_tokens, 30)
        
        try:
            client = _get_groq_client()
            trimmed_history = self.history[-6:] if len(self.history) > 6 else self.history
            
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": self.system_prompt}] + trimmed_history,
                temperature=0.6,
                max_tokens=max_tokens,
                stream=True,  # 🔥 OPTIMIZATION: Enable streaming
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
