"""
exotel_client.py
All Exotel API calls: make outbound calls, get call status, send SMS.
Includes retry logic with exponential backoff and connection stability features.
"""
import time
import requests
import config

# ── CONNECTION STABILITY HELPERS ──────────────────────────────────────────────

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 2  # seconds; doubles each retry


def _request_with_retry(method: str, url: str, **kwargs) -> requests.Response:
    """
    Execute an HTTP request with exponential backoff retry on transient errors.
    Raises the last exception if all retries are exhausted.
    """
    last_exc = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = requests.request(method, url, **kwargs)
            resp.raise_for_status()
            return resp
        except (requests.ConnectionError, requests.Timeout) as exc:
            last_exc = exc
            wait = _RETRY_BACKOFF_BASE ** attempt
            print(f"[Exotel] Transient error (attempt {attempt + 1}/{_MAX_RETRIES}): {exc} — retrying in {wait}s")
            time.sleep(wait)
        except requests.HTTPError as exc:
            # 4xx errors are not transient — don't retry
            raise
    raise last_exc


def check_connection() -> bool:
    """
    Heartbeat check: verify Exotel API is reachable.
    Returns True if connection is healthy.
    """
    url = (
        f"https://{config.EXOTEL_API_KEY}:{config.EXOTEL_API_TOKEN}"
        f"@{config.EXOTEL_SUBDOMAIN}/v1/Accounts/{config.EXOTEL_ACCOUNT_SID}"
    )
    try:
        _request_with_retry("GET", url, timeout=10)
        return True
    except Exception as e:
        print(f"[Exotel] Heartbeat failed: {e}")
        return False


def make_outbound_call(to_number: str, lead_id: str = "") -> dict:
    """
    Initiate outbound call from Exophone to customer.
    Exotel will call the customer and bridge to our webhook for AI handling.
    Uses retry logic with exponential backoff for stable connections.
    """
    url = f"https://{config.EXOTEL_API_KEY}:{config.EXOTEL_API_TOKEN}@{config.EXOTEL_SUBDOMAIN}/v1/Accounts/{config.EXOTEL_ACCOUNT_SID}/Calls/connect"
    
    # Exotel passthru URL — our app handles the call logic via webhook
    call_handler_url = f"{config.PUBLIC_URL}/call/handler"
    
    payload = {
        "From": to_number,
        "To": config.EXOTEL_PHONE_NUMBER,
        "CallerId": config.EXOTEL_PHONE_NUMBER,
        "Url": call_handler_url,
        "Record": "true",
        "TimeLimit": 300,          # max 5 min call
        "TimeOut": 30,             # ring timeout
        "StatusCallback": f"{config.PUBLIC_URL}/call/status",
        "CustomField": lead_id,
    }
    
    try:
        r = _request_with_retry("POST", url, data=payload, timeout=15)
        data = r.json()
        call_sid = data.get("Call", {}).get("Sid", "")
        print(f"[Exotel] Outbound call initiated to {to_number} | SID: {call_sid}")
        return {"success": True, "call_sid": call_sid, "data": data}
    except Exception as e:
        print(f"[Exotel] Call failed to {to_number}: {e}")
        return {"success": False, "error": str(e)}


def send_sms(to_number: str, message: str) -> dict:
    """Send SMS via Exotel with retry on transient errors."""
    url = f"https://{config.EXOTEL_API_KEY}:{config.EXOTEL_API_TOKEN}@{config.EXOTEL_SUBDOMAIN}/v1/Accounts/{config.EXOTEL_ACCOUNT_SID}/Sms/send"
    
    payload = {
        "From": config.EXOTEL_PHONE_NUMBER,
        "To": to_number,
        "Body": message,
    }
    
    try:
        _request_with_retry("POST", url, data=payload, timeout=10)
        print(f"[Exotel] SMS sent to {to_number}")
        return {"success": True}
    except Exception as e:
        print(f"[Exotel] SMS failed to {to_number}: {e}")
        return {"success": False, "error": str(e)}


def get_call_details(call_sid: str) -> dict:
    """Fetch call details from Exotel."""
    url = f"https://{config.EXOTEL_API_KEY}:{config.EXOTEL_API_TOKEN}@{config.EXOTEL_SUBDOMAIN}/v1/Accounts/{config.EXOTEL_ACCOUNT_SID}/Calls/{call_sid}"
    try:
        r = _request_with_retry("GET", url, timeout=10)
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def notify_salesperson(salesperson: dict, lead: dict) -> bool:
    """
    Notify a salesperson via SMS when a lead is converted/hot.
    """
    lead_name    = lead.get("name", "Customer")
    lead_mobile  = lead.get("mobile", "")
    lead_model   = lead.get("interested_model", "Hero Bike")
    lead_notes   = lead.get("notes", "")
    
    message = (
        f"🔥 HOT LEAD ASSIGNED!\n"
        f"Hi {salesperson['name']},\n"
        f"Lead: {lead_name}\n"
        f"Mobile: {lead_mobile}\n"
        f"Interest: {lead_model}\n"
        f"Notes: {lead_notes[:100]}\n"
        f"Please call them ASAP!\n"
        f"- Shubham Motors AI"
    )
    
    result = send_sms(salesperson["mobile"], message)
    return result.get("success", False)