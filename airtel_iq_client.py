"""
airtel_iq_client.py
Airtel IQ telephony integration — Indian numbers, competitive pricing.

Setup steps:
1. Sign up at https://iq.airtel.in/developer (or contact Airtel enterprise sales)
2. Get API Key, API Secret, Account ID from the developer dashboard
3. Get a virtual number (DID) assigned to your account
4. Configure in .env:
   TELEPHONY_PROVIDER=airtel_iq
   AIRTEL_IQ_API_KEY=your_key
   AIRTEL_IQ_API_SECRET=your_secret
   AIRTEL_IQ_ACCOUNT_ID=your_account_id
   AIRTEL_IQ_PHONE_NUMBER=+91XXXXXXXXXX

Airtel IQ OBD (Outbound Dialer) API docs:
https://developer.airtel.in/iq/voice

Webhook format Airtel IQ sends to your endpoint:
  CallId, CallerNumber, CalledNumber, Status, RecordingUrl, Duration

Airtel IQ call control:
  Returns JSON (not XML) — {"action": "play", "url": "..."} etc.
  OR standard TwiML-compatible XML (depends on account configuration).
  Contact Airtel IQ support to confirm which format your account uses.
"""

import requests
import config

# Airtel IQ API base URL (confirm with Airtel IQ support if this changes)
_BASE_URL = f"https://{config.AIRTEL_IQ_SUBDOMAIN}"


def _get_headers() -> dict:
    """Build auth headers for Airtel IQ API."""
    return {
        "X-API-KEY": config.AIRTEL_IQ_API_KEY,
        "X-API-SECRET": config.AIRTEL_IQ_API_SECRET,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def make_outbound_call(to_number: str, lead_id: str = "") -> dict:
    """
    Initiate outbound call via Airtel IQ OBD API.

    Airtel IQ connects to the customer, then bridges to your webhook
    URL for AI call handling. The webhook receives a CallId and caller
    details — respond with call control (play audio / record / hangup).

    NOTE: The exact API endpoint and payload format may vary based on
    your Airtel IQ plan. This is based on standard Airtel IQ OBD API.
    Contact Airtel IQ support for your account-specific endpoint.
    """
    if not config.AIRTEL_IQ_API_KEY:
        print("[AirtelIQ] ERROR: AIRTEL_IQ_API_KEY not configured in .env")
        return {"success": False, "error": "Airtel IQ not configured"}

    url = f"{_BASE_URL}/iq/voice/v1/calls/outbound"

    payload = {
        "from": config.AIRTEL_IQ_PHONE_NUMBER,
        "to": to_number,
        "callbackUrl": f"{config.PUBLIC_URL}/airtel/handler",
        "statusCallbackUrl": f"{config.PUBLIC_URL}/airtel/status",
        "maxDuration": 300,         # 5 minutes max
        "recordingEnabled": True,
        "customData": lead_id,      # Passed back in webhook
    }

    try:
        r = requests.post(url, headers=_get_headers(), json=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        call_id = data.get("callId", data.get("call_id", ""))
        print(f"[AirtelIQ] Outbound call to {to_number} | CallId: {call_id}")
        return {"success": True, "call_sid": call_id, "data": data}
    except Exception as e:
        print(f"[AirtelIQ] Call failed to {to_number}: {e}")
        return {"success": False, "error": str(e)}


def send_sms(to_number: str, message: str) -> dict:
    """Send SMS via Airtel IQ."""
    if not config.AIRTEL_IQ_API_KEY:
        return {"success": False, "error": "Airtel IQ not configured"}

    url = f"{_BASE_URL}/iq/sms/v1/send"
    payload = {
        "from": config.AIRTEL_IQ_PHONE_NUMBER,
        "to": to_number,
        "message": message,
    }
    try:
        r = requests.post(url, headers=_get_headers(), json=payload, timeout=10)
        r.raise_for_status()
        print(f"[AirtelIQ] SMS sent to {to_number}")
        return {"success": True}
    except Exception as e:
        print(f"[AirtelIQ] SMS failed to {to_number}: {e}")
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
