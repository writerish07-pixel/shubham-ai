"""
sheets_manager.py
Local JSON storage for Shubham Motors lead management.
Stores all data in local files — no Google Sheets needed.
Data is saved in: data/leads.json, data/calls.json, data/offers.json
"""
import json
import os
from datetime import datetime
from pathlib import Path

import config

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

LEADS_FILE  = DATA_DIR / "leads.json"
CALLS_FILE  = DATA_DIR / "calls.json"
OFFERS_FILE = DATA_DIR / "offers.json"


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _load(filepath: Path) -> list:
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save(filepath: Path, data: list):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ── LEADS ─────────────────────────────────────────────────────────────────────

def add_lead(lead: dict) -> str:
    leads = _load(LEADS_FILE)
    lead_id = f"L{int(datetime.now().timestamp())}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_lead = {
        "lead_id":          lead_id,
        "name":             lead.get("name", ""),
        "mobile":           lead.get("mobile", ""),
        "alternate_mobile": lead.get("alternate_mobile", ""),
        "city":             lead.get("city", config.BUSINESS_CITY),
        "area":             lead.get("area", ""),
        "interested_model": lead.get("interested_model", ""),
        "budget":           lead.get("budget", ""),
        "source":           lead.get("source", "manual"),
        "status":           "new",
        "temperature":      "warm",
        "assigned_to":      "",
        "assigned_mobile":  "",
        "call_count":       0,
        "last_called":      "",
        "next_followup":    "",
        "notes":            lead.get("notes", ""),
        "created_at":       now,
        "converted_at":     "",
        "tags":             lead.get("tags", ""),
    }
    leads.append(new_lead)
    _save(LEADS_FILE, leads)
    return lead_id

def get_all_leads() -> list:
    return _load(LEADS_FILE)

def get_lead_by_mobile(mobile: str) -> dict | None:
    clean = mobile.replace("+91", "").replace(" ", "").strip()
    for r in get_all_leads():
        if str(r.get("mobile", "")).replace("+91", "").replace(" ", "").strip() == clean:
            return r
    return None

def get_lead_by_id(lead_id: str) -> dict | None:
    for r in get_all_leads():
        if str(r.get("lead_id", "")) == lead_id:
            return r
    return None

def update_lead(lead_id: str, updates: dict) -> bool:
    leads = _load(LEADS_FILE)
    for lead in leads:
        if str(lead.get("lead_id", "")) == lead_id:
            lead.update(updates)
            _save(LEADS_FILE, leads)
            return True
    return False

def get_leads_due_for_followup() -> list:
    now = datetime.now()
    due = []
    for r in get_all_leads():
        if r.get("status") in ("dead", "converted"):
            continue
        nf = r.get("next_followup", "")
        if not nf:
            continue
        try:
            nf_dt = datetime.strptime(str(nf), "%Y-%m-%d %H:%M")
            if nf_dt <= now:
                due.append(r)
        except Exception:
            pass
    return due

def get_new_uncontacted_leads() -> list:
    return [r for r in get_all_leads() if r.get("status") == "new" and not r.get("last_called")]


# ── CALL LOG ──────────────────────────────────────────────────────────────────

def log_call(data: dict):
    calls = _load(CALLS_FILE)
    log_id = f"C{int(datetime.now().timestamp())}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    calls.append({
        "log_id":       log_id,
        "lead_id":      data.get("lead_id", ""),
        "mobile":       data.get("mobile", ""),
        "direction":    data.get("direction", "outbound"),
        "duration_sec": data.get("duration_sec", 0),
        "status":       data.get("status", ""),
        "transcript":   data.get("transcript", ""),
        "sentiment":    data.get("sentiment", "neutral"),
        "ai_summary":   data.get("ai_summary", ""),
        "next_action":  data.get("next_action", ""),
        "called_at":    now,
    })
    _save(CALLS_FILE, calls)
    return log_id


# ── OFFERS ────────────────────────────────────────────────────────────────────

def get_active_offers() -> list:
    offers = _load(OFFERS_FILE)
    today = datetime.now().date()
    active = []
    for r in offers:
        vt = r.get("valid_till", "")
        try:
            if datetime.strptime(str(vt), "%Y-%m-%d").date() >= today:
                active.append(r)
        except Exception:
            active.append(r)  # no date = always show
    return active

def add_offer(offer: dict) -> str:
    offers = _load(OFFERS_FILE)
    oid = f"O{int(datetime.now().timestamp())}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    offers.append({
        "offer_id":    oid,
        "title":       offer.get("title", ""),
        "description": offer.get("description", ""),
        "valid_till":  offer.get("valid_till", ""),
        "models":      offer.get("models", ""),
        "uploaded_at": now,
    })
    _save(OFFERS_FILE, offers)
    return oid


# ── SETTINGS ──────────────────────────────────────────────────────────────────

SETTINGS_FILE = DATA_DIR / "settings.json"

def get_setting(key: str, default="") -> str:
    settings = _load(SETTINGS_FILE) if SETTINGS_FILE.exists() else []
    for r in settings:
        if r.get("key") == key:
            return str(r.get("value", ""))
    return default

def set_setting(key: str, value: str):
    settings = _load(SETTINGS_FILE) if SETTINGS_FILE.exists() else []
    for r in settings:
        if r.get("key") == key:
            r["value"] = value
            _save(SETTINGS_FILE, settings)
            return
    settings.append({"key": key, "value": value})
    _save(SETTINGS_FILE, settings)