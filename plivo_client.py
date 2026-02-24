"""
plivo_client.py
Plivo telephony integration — Indian DID numbers, competitive pricing.

WHY PLIVO instead of Airtel IQ:
  • Self-service signup at https://console.plivo.com (no enterprise approval needed)
  • Indian phone numbers (DID) available instantly
  • REST API almost identical to Twilio/Exotel — minimal code changes
  • PHML (Plivo XML) is nearly identical to ExoML — our <Record> XML works as-is
  • Pricing: ~₹0.8-1.2/min for Indian calls (comparable to Exotel)
  • No per-call connection fee, only per-minute billing

SETUP (5 minutes):
  1. Sign up at https://console.plivo.com (free trial credit included)
  2. Buy a virtual number: Numbers → Buy Number → India → Search → Buy
  3. Get Auth ID + Auth Token from the main console dashboard
  4. In .env, set:
       TELEPHONY_PROVIDER=plivo
       PLIVO_AUTH_ID=MAXXXXXXXXXXXXXXXXXX
       PLIVO_AUTH_TOKEN=your_token_here
       PLIVO_PHONE_NUMBER=+91XXXXXXXXXX
  5. In Plivo console → Numbers → your number → set:
       App Type: XML
       Answer URL: {PUBLIC_URL}/plivo/incoming
       Answer Method: POST
       Hangup URL: {PUBLIC_URL}/plivo/status
       Hangup Method: POST
  6. Restart the server

Plivo webhook parameters (differ from Exotel — mapping documented below):
  Exotel → Plivo
  CallSid → CallUUID
  From    → From (same)
  To      → To (same)
  RecordingUrl → RecordUrl
  CustomField  → (not standard — use call_url parameter or database lookup)
"""

import requests
from requests.auth import HTTPBasicAuth
import config

_BASE = "https://api.plivo.com/v1"


def _auth():
    return HTTPBasicAuth(config.PLIVO_AUTH_ID, config.PLIVO_AUTH_TOKEN)


def make_outbound_call(to_number: str, lead_id: str = "") -> dict:
    """
    Initiate outbound call via Plivo.

    Plivo calls the customer. When answered, Plivo hits answer_url for XML
    call control. We respond with <Speak>/<Play> + <Record> to start the AI flow.
    """
    if not config.PLIVO_AUTH_ID:
        print("[Plivo] ERROR: PLIVO_AUTH_ID not configured in .env")
        return {"success": False, "error": "Plivo not configured"}

    url = f"{_BASE}/Account/{config.PLIVO_AUTH_ID}/Call/"

    # answer_url is the webhook Plivo calls when the outbound call connects
    # We append lead_id as query param since Plivo has no CustomField equivalent
    answer_url = f"{config.PUBLIC_URL}/plivo/handler?lead_id={lead_id}"

    payload = {
        "from": config.PLIVO_PHONE_NUMBER,
        "to":   to_number,
        "answer_url":    answer_url,
        "answer_method": "POST",
        "hangup_url":    f"{config.PUBLIC_URL}/plivo/status",
        "hangup_method": "POST",
        "record":        "true",
        "time_limit":    300,     # 5 min max
        "ring_timeout":  30,
    }

    try:
        r = requests.post(url, auth=_auth(), data=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        call_uuid = data.get("request_uuid", "")
        print(f"[Plivo] Outbound call to {to_number} | UUID: {call_uuid}")
        return {"success": True, "call_sid": call_uuid, "data": data}
    except Exception as e:
        print(f"[Plivo] Call failed to {to_number}: {e}")
        return {"success": False, "error": str(e)}


def send_sms(to_number: str, message: str) -> dict:
    """Send SMS via Plivo."""
    if not config.PLIVO_AUTH_ID:
        return {"success": False, "error": "Plivo not configured"}

    url = f"{_BASE}/Account/{config.PLIVO_AUTH_ID}/Message/"
    payload = {
        "src": config.PLIVO_PHONE_NUMBER,
        "dst": to_number,
        "text": message,
    }
    try:
        r = requests.post(url, auth=_auth(), data=payload, timeout=10)
        r.raise_for_status()
        print(f"[Plivo] SMS sent to {to_number}")
        return {"success": True}
    except Exception as e:
        print(f"[Plivo] SMS failed to {to_number}: {e}")
        return {"success": False, "error": str(e)}


def notify_salesperson(salesperson: dict, lead: dict) -> bool:
    """Notify salesperson via SMS when a hot lead is assigned."""
    lead_name   = lead.get("name", "Customer")
    lead_mobile = lead.get("mobile", "")
    lead_model  = lead.get("interested_model", "Hero Bike")
    lead_notes  = lead.get("notes", "")

    message = (
        f"HOT LEAD ASSIGNED!\n"
        f"Hi {salesperson['name']},\n"
        f"Lead: {lead_name}\n"
        f"Mobile: {lead_mobile}\n"
        f"Interest: {lead_model}\n"
        f"Notes: {lead_notes[:100]}\n"
        f"Please call ASAP!\n"
        f"- Shubham Motors AI"
    )
    result = send_sms(salesperson["mobile"], message)
    return result.get("success", False)
