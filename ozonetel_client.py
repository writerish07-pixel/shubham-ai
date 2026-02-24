"""
ozonetel_client.py
Ozonetel KooKoo telephony — Indian virtual numbers, self-service signup.

WHY OZONETEL KOOKOO:
  • Indian company, Indian +91 DID numbers
  • Self-service signup at https://kookoo.in — no enterprise approval
  • REST API for outbound calls, webhook-based IVR
  • Good developer documentation
  • Pricing: ~₹0.3-0.6/min for Indian calls

SETUP (10 minutes):
  1. Sign up at https://kookoo.in (free trial balance included)
  2. Verify mobile + complete basic KYC (Aadhaar/PAN — required for all Indian providers)
  3. Get API Key from: Dashboard → Settings → API Key
  4. Buy a virtual number: Numbers → Buy Number
  5. In .env, set:
       TELEPHONY_PROVIDER=ozonetel
       OZONETEL_API_KEY=your_api_key
       OZONETEL_PHONE_NUMBER=+91XXXXXXXXXX   (your KooKoo virtual number)
  6. In KooKoo dashboard → your number → set:
       Inbound call URL: {PUBLIC_URL}/ozonetel/incoming
       Method: POST
  7. Restart server

Webhook parameters KooKoo sends to your endpoint:
  Called        — your KooKoo number
  CalledFrom    — customer's number
  CallSid       — unique call identifier
  DialCallStatus — call status (ringing/answered/completed/etc.)

KooKoo XML response format (similar to ExoML but uses different tags):
  <response>
    <say>Text to speak</say>
    <play>audio_url</play>
    <record action="URL" method="POST" />
    <hangup/>
  </response>

Recording webhook params (posted to record action URL):
  CallSid, RecordingUrl, CalledFrom, Called
"""

import requests
import config

_OUTBOUND_URL = "https://kookoo.in/outbound/calls/"
_SMS_URL      = "https://kookoo.in/api/sms/"


def make_outbound_call(to_number: str, lead_id: str = "") -> dict:
    """
    Initiate outbound call via KooKoo.
    KooKoo calls the customer. When answered, it hits xml_url for call control.
    We reuse the same /ozonetel/handler webhook — lead_id passed as query param.
    """
    if not config.OZONETEL_API_KEY:
        print("[Ozonetel] ERROR: OZONETEL_API_KEY not configured in .env")
        return {"success": False, "error": "Ozonetel not configured"}

    # Normalize number — KooKoo expects 10-digit without country code OR E.164
    caller_no = to_number.lstrip("+").lstrip("91") if to_number.startswith("+91") else to_number
    our_no    = config.OZONETEL_PHONE_NUMBER.lstrip("+").lstrip("91")

    answer_url = f"{config.PUBLIC_URL}/ozonetel/handler?lead_id={lead_id}"

    payload = {
        "phone_no_a":  caller_no,         # customer to dial
        "phone_no_b":  our_no,            # our KooKoo number (shown as caller ID)
        "api_key":     config.OZONETEL_API_KEY,
        "xml_url":     answer_url,        # webhook called when customer picks up
        "caller_id":   our_no,
        "time_limit":  300,               # max 5 min
        "custom":      lead_id,           # passed back in webhook as CustomField
    }

    try:
        r = requests.post(_OUTBOUND_URL, data=payload, timeout=15)
        # KooKoo returns plain text: "ID:<call_id>" on success, "FAILED:<reason>" on error
        text = r.text.strip()
        if text.startswith("ID:"):
            call_id = text.split(":", 1)[1]
            print(f"[Ozonetel] Outbound call to {to_number} | CallId: {call_id}")
            return {"success": True, "call_sid": call_id, "data": {"id": call_id}}
        else:
            print(f"[Ozonetel] Call failed: {text}")
            return {"success": False, "error": text}
    except Exception as e:
        print(f"[Ozonetel] Call exception to {to_number}: {e}")
        return {"success": False, "error": str(e)}


def send_sms(to_number: str, message: str) -> dict:
    """Send SMS via KooKoo/Ozonetel."""
    if not config.OZONETEL_API_KEY:
        return {"success": False, "error": "Ozonetel not configured"}

    payload = {
        "api_key": config.OZONETEL_API_KEY,
        "to":      to_number.lstrip("+"),
        "from":    config.OZONETEL_PHONE_NUMBER.lstrip("+"),
        "message": message,
    }
    try:
        r = requests.post(_SMS_URL, data=payload, timeout=10)
        print(f"[Ozonetel] SMS sent to {to_number}")
        return {"success": True}
    except Exception as e:
        print(f"[Ozonetel] SMS failed to {to_number}: {e}")
        return {"success": False, "error": str(e)}


def notify_salesperson(salesperson: dict, lead: dict) -> bool:
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
        f"Please call ASAP!\n- Shubham Motors AI"
    )
    return send_sms(salesperson["mobile"], message).get("success", False)


def kookoo_record_xml(call_sid: str, play_url: str = None, say_text: str = None) -> str:
    """
    KooKoo XML for call control.
    Format is different from ExoML — uses <response>, <say>, <record> tags.
    """
    content = ""
    if play_url:
        content = f"  <play>{play_url}</play>"
    elif say_text:
        # Escape XML special characters
        safe = (say_text[:800]
                .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        content = f"  <say>hi-IN:{safe}</say>"

    gather_url = f"{config.PUBLIC_URL}/ozonetel/gather/{call_sid}"

    return (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<response>\n'
        f'{content}\n'
        f'  <record action="{gather_url}" method="POST" '
        f'maxLength="15" timeout="5" playBeep="false" />\n'
        f'</response>'
    )


def kookoo_hangup_xml() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n<response><hangup/></response>'
