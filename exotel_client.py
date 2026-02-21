"""
exotel_client.py
All Exotel API calls: make outbound calls, get call status, send SMS.
"""
import requests
import config


def make_outbound_call(to_number: str, lead_id: str = "") -> dict:
    """
    Initiate outbound call from Exophone to customer.
    Exotel will call the customer and bridge to our webhook for AI handling.
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
        r = requests.post(url, data=payload, timeout=15)
        r.raise_for_status()
        data = r.json()
        call_sid = data.get("Call", {}).get("Sid", "")
        print(f"[Exotel] Outbound call initiated to {to_number} | SID: {call_sid}")
        return {"success": True, "call_sid": call_sid, "data": data}
    except Exception as e:
        print(f"[Exotel] Call failed to {to_number}: {e}")
        return {"success": False, "error": str(e)}


def send_sms(to_number: str, message: str) -> dict:
    """Send SMS via Exotel."""
    url = f"https://{config.EXOTEL_API_KEY}:{config.EXOTEL_API_TOKEN}@{config.EXOTEL_SUBDOMAIN}/v1/Accounts/{config.EXOTEL_ACCOUNT_SID}/Sms/send"
    
    payload = {
        "From": config.EXOTEL_PHONE_NUMBER,
        "To": to_number,
        "Body": message,
    }
    
    try:
        r = requests.post(url, data=payload, timeout=10)
        r.raise_for_status()
        print(f"[Exotel] SMS sent to {to_number}")
        return {"success": True}
    except Exception as e:
        print(f"[Exotel] SMS failed to {to_number}: {e}")
        return {"success": False, "error": str(e)}


def get_call_details(call_sid: str) -> dict:
    """Fetch call details from Exotel."""
    url = f"https://{config.EXOTEL_API_KEY}:{config.EXOTEL_API_TOKEN}@{config.EXOTEL_SUBDOMAIN}/v1/Accounts/{config.EXOTEL_ACCOUNT_SID}/Calls/{call_sid}"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
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