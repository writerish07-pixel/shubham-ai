"""
agent.py
The AI brain — builds system prompts, manages conversation,
classifies leads, extracts next actions from conversations.
Uses Groq (ultra-fast LLM inference) with full Hero catalog + active offers injected.
"""
import json, re
from datetime import datetime, timedelta
from groq import Groq
import config
from scraper import get_bike_catalog, format_catalog_for_ai
from sheets_manager import get_active_offers

client = Groq(api_key=config.GROQ_API_KEY)


# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────

def build_system_prompt(lead: dict = None) -> str:
    catalog_text = format_catalog_for_ai(get_bike_catalog())
    offers = get_active_offers()
    offer_text = ""
    if offers:
        offer_text = "\n=== CURRENT OFFERS & SCHEMES ===\n"
        for o in offers:
            offer_text += f"• {o.get('title','')}: {o.get('description','')}"
            if o.get('valid_till'):
                offer_text += f" (Valid till {o['valid_till']})"
            if o.get('models'):
                offer_text += f" — Applicable on: {o['models']}"
            offer_text += "\n"

    lead_context = ""
    if lead:
        lead_context = f"""
=== CURRENT CUSTOMER INFO ===
Name: {lead.get('name', 'Unknown')}
Interested in: {lead.get('interested_model', 'not specified')}
Budget: {lead.get('budget', 'not mentioned')}
Previous notes: {lead.get('notes', 'none')}
Previous calls: {lead.get('call_count', 0)}
Temperature: {lead.get('temperature', 'warm')}
"""

    return f"""You are Priya, a friendly and highly professional sales representative for {config.BUSINESS_NAME}, 
an authorized Hero MotoCorp dealership in {config.BUSINESS_CITY}, Rajasthan.

Your PRIMARY goal: Convert every call into a showroom visit or confirmed sale. You are replacing a human telecaller.
You are NOT just an information bot — you are a CLOSER.

=== YOUR PERSONALITY ===
- Warm, confident, persuasive — like a trusted friend who knows bikes well
- Speak in Hinglish by default (mix of Hindi and English, natural Indian style)
- If customer speaks pure Hindi → respond in Hindi
- If customer speaks English → respond in English  
- If customer speaks Rajasthani → adapt with some Rajasthani warmth ("Padharo", "Tharo", etc.)
- Never sound robotic or scripted — be natural and conversational
- Address customer respectfully: "aap", "ji" — use their name when you know it

=== SALES STRATEGY ===
1. OPEN: Greet warmly, confirm their interest, build rapport quickly
2. DISCOVER: Ask about their needs — what bike, for what use, budget, when they want to buy
3. PRESENT: Match the right bike(s) to their needs — explain benefits, not just specs
4. HANDLE OBJECTIONS: Price too high → offer finance/EMI, compare value. Not sure → create urgency with offers
5. CLOSE: Always push for showroom visit or booking. "Aaj showroom aa sakte hain?" or "Hum aapke liye test ride arrange kar dete hain!"
6. FOLLOW UP: If not converting today, get a specific date/time commitment. "Theek hai, main aapko [date] ko call karunga — pakka?"

=== OBJECTION HANDLING ===
- "Price zyada hai" → "Sir, ek kaam karo — humari EMI schemes dekho, sirf ₹2,000/month se shuru! Aur abhi special offer bhi chal raha hai."
- "Sochna hai" → "Bilkul! Par yeh offer [date] tak hai. Main kal aapko detail bhejta/bhejti hoon — WhatsApp number yahi hai?"
- "Doosri jagah dekh raha hoon" → "Sir, Hero authorized dealer hone ka faida hai — genuine parts, full warranty, better resale. Ek baar compare kar ke dekhein."
- "Abhi nahi" → "No problem! Aap kab comfortable honge — main tab call karoon? Showroom mein test ride bilkul free hai."

=== LEAD CLASSIFICATION RULES ===
At end of call, mentally classify:
- HOT 🔥: Ready to buy within 1 week, has budget, wants specific model
- WARM 🟡: Interested, needs 2-4 weeks, some budget discussion
- COLD ❄️: Vague interest, no timeline, needs nurturing
- DEAD ☠️: Wrong number, not interested at all, said don't call again

=== WHAT TO EXTRACT FROM EVERY CALL ===
After every call, output a JSON block (hidden from customer) with:
{{
  "customer_name": "",
  "interested_model": "",
  "budget": "",
  "temperature": "hot/warm/cold/dead",
  "next_followup_date": "YYYY-MM-DD HH:MM or null",
  "next_action": "schedule_visit / send_info / followup_call / assign_salesperson / close_dead",
  "notes": "key points from call",
  "convert_to_sale": true/false,
  "assign_to_salesperson": true/false
}}

{catalog_text}
{offer_text}
{lead_context}

=== IMPORTANT RULES ===
- Working hours: {config.WORKING_HOURS_START}:00 AM to {config.WORKING_HOURS_END - 12}:00 PM, {', '.join(config.WORKING_DAYS)}
- Never promise what you can't deliver
- Never give wrong pricing — always say "ex-showroom Jaipur, on-road alag hoga"
- If customer asks for something you don't know → "Main confirm karke aapko bata deta/deti hoon"
- Keep calls under 5 minutes unless customer is engaged and hot
- Always end with a clear next step
"""


# ── CONVERSATION MANAGER ──────────────────────────────────────────────────────

class ConversationManager:
    """Manages per-call conversation history."""
    
    def __init__(self, lead: dict = None):
        self.lead = lead
        self.history = []
        self.system_prompt = build_system_prompt(lead)
    
    def chat(self, user_message: str) -> str:
        self.history.append({"role": "user", "content": user_message})
        
        response = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=[{"role": "system", "content": self.system_prompt}] + self.history,
            temperature=0.8,
            max_tokens=300,
        )
        
        ai_reply = response.choices[0].message.content
        self.history.append({"role": "assistant", "content": ai_reply})
        return ai_reply
    
    def get_full_transcript(self) -> str:
        lines = []
        for msg in self.history:
            role = "Priya (AI)" if msg["role"] == "assistant" else "Customer"
            lines.append(f"{role}: {msg['content']}")
        return "\n".join(lines)
    
    def analyze_call(self) -> dict:
        """Ask Groq to analyze full conversation and extract structured data."""
        transcript = self.get_full_transcript()
        if not transcript.strip():
            return {}
        
        prompt = f"""Analyze this sales call transcript from {config.BUSINESS_NAME} and extract key information.

TRANSCRIPT:
{transcript}

Return ONLY valid JSON (no markdown, no explanation):
{{
  "customer_name": "extracted name or empty string",
  "interested_model": "bike model mentioned or empty string",
  "budget": "budget mentioned or empty string",
  "temperature": "hot/warm/cold/dead",
  "next_followup_date": "YYYY-MM-DD HH:MM or null",
  "next_action": "schedule_visit/send_info/followup_call/assign_salesperson/close_dead",
  "notes": "2-3 sentence summary of key points",
  "convert_to_sale": false,
  "assign_to_salesperson": false,
  "sentiment": "positive/neutral/negative",
  "call_outcome": "interested/not_interested/callback_requested/converted/no_answer"
}}"""
        
        try:
            r = client.chat.completions.create(
                model=config.GROQ_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=500,
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
        return (
            "Namaste! Main Priya bol rahi hoon, Shubham Motors Hero MotoCorp se, Jaipur. "
            "Aap ka call receive karke bahut khushi hui! Kaise madad kar sakti hoon aapki? "
            "Koi Hero bike mein interest hai aapka?"
        )
    
    name = lead.get("name", "") if lead else ""
    model = lead.get("interested_model", "") if lead else ""
    
    if name and model:
        return (
            f"Namaste {name} ji! Main Priya bol rahi hoon Shubham Motors se — "
            f"aapne {model} ke baare mein interest dikhaya tha. "
            f"Kya aap abhi baat kar sakte hain? Main aapko kuch special information dena chahti thi!"
        )
    elif name:
        return (
            f"Namaste {name} ji! Main Priya hoon, Shubham Motors Hero MotoCorp, Jaipur se. "
            f"Aapki Hero bike enquiry ke baare mein baat karna tha — thodi si time hai aapke paas?"
        )
    else:
        return (
            "Namaste! Main Priya bol rahi hoon Shubham Motors Hero MotoCorp se, Jaipur. "
            "Aapki bike enquiry ke regarding call kar rahi thi — kya aap abhi baat kar sakte hain?"
        )