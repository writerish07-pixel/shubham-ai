"""
scheduler.py
Auto follow-up engine using APScheduler.
- Every 5 min: check leads due for follow-up → make outbound call
- Every 24h: re-scrape Hero website for updated prices
- Every morning 9AM: call all new uncontacted leads
"""
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz
import config
import sheets_manager as db
import exotel_client as _exotel
import airtel_iq_client as _airtel_iq
import plivo_client as _plivo
import ozonetel_client as _ozonetel
from scraper import scrape_hero_website


def make_outbound_call(to_number: str, lead_id: str = "") -> dict:
    """Route through configured telephony provider."""
    if config.TELEPHONY_PROVIDER == "plivo":
        return _plivo.make_outbound_call(to_number, lead_id)
    if config.TELEPHONY_PROVIDER == "ozonetel":
        return _ozonetel.make_outbound_call(to_number, lead_id)
    if config.TELEPHONY_PROVIDER == "airtel_iq":
        return _airtel_iq.make_outbound_call(to_number, lead_id)
    return _exotel.make_outbound_call(to_number, lead_id)

IST = pytz.timezone("Asia/Kolkata")
scheduler = BackgroundScheduler(timezone=IST)


def _is_working_hours() -> bool:
    now = datetime.now(IST)
    day_name = now.strftime("%A")
    hour = now.hour
    return (
        day_name in config.WORKING_DAYS and
        config.WORKING_HOURS_START <= hour < config.WORKING_HOURS_END
    )


def check_and_call_followups():
    """Check leads due for follow-up and make calls."""
    if not _is_working_hours():
        return
    
    due_leads = db.get_leads_due_for_followup()
    print(f"[Scheduler] Follow-up check: {len(due_leads)} leads due")
    
    for lead in due_leads:
        mobile = lead.get("mobile", "")
        lead_id = lead.get("lead_id", "")
        call_count = int(lead.get("call_count", 0))
        
        if not mobile:
            continue
        if call_count >= config.MAX_FOLLOWUP_ATTEMPTS:
            db.update_lead(lead_id, {"status": "dead", "next_followup": ""})
            print(f"[Scheduler] Lead {lead_id} marked DEAD (max attempts reached)")
            continue
        
        print(f"[Scheduler] Calling {lead.get('name','?')} ({mobile}) | Lead: {lead_id}")
        result = make_outbound_call(mobile, lead_id)
        
        if result.get("success"):
            db.update_lead(lead_id, {
                "last_called": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "next_followup": "",  # will be re-set after call ends
            })
        else:
            print(f"[Scheduler] Call failed for {lead_id}: {result.get('error')}")


def call_new_leads():
    """Morning run: call all new leads that have never been contacted."""
    if not _is_working_hours():
        return
    
    new_leads = db.get_new_uncontacted_leads()
    print(f"[Scheduler] New leads to contact: {len(new_leads)}")
    
    import time
    for lead in new_leads[:10]:  # max 10 at a time to avoid flooding
        mobile = lead.get("mobile", "")
        lead_id = lead.get("lead_id", "")
        if mobile:
            make_outbound_call(mobile, lead_id)
            time.sleep(5)  # 5 sec between calls


def refresh_bike_catalog():
    """Refresh Hero bike catalog from website."""
    print("[Scheduler] Refreshing Hero bike catalog...")
    scrape_hero_website()
    print("[Scheduler] Catalog refreshed")


def start_scheduler():
    """Start all scheduled jobs."""
    # Every 5 minutes: follow-up calls
    scheduler.add_job(
        check_and_call_followups,
        "interval", minutes=5,
        id="followup_calls",
        replace_existing=True
    )
    
    # Every morning at 9:30 AM: call new uncontacted leads
    scheduler.add_job(
        call_new_leads,
        CronTrigger(hour=9, minute=30, timezone=IST),
        id="morning_calls",
        replace_existing=True
    )
    
    # Every day at midnight: refresh bike catalog
    scheduler.add_job(
        refresh_bike_catalog,
        CronTrigger(hour=0, minute=5, timezone=IST),
        id="catalog_refresh",
        replace_existing=True
    )
    
    scheduler.start()
    print("[Scheduler] ✅ Started — follow-ups every 5 min, morning calls at 9:30 AM IST")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()