"""
sheets_manager.py
Local JSON storage for Shubham Motors lead management.
Stores all data in local files — no Google Sheets needed.
Data is saved in: data/leads.json, data/calls.json, data/offers.json
"""
import json
import logging
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path

import config

log = logging.getLogger("shubham-ai.storage")

# File lock to prevent concurrent JSON corruption
_file_lock = threading.Lock()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

LEADS_FILE  = DATA_DIR / "leads.json"
CALLS_FILE  = DATA_DIR / "calls.json"
OFFERS_FILE = DATA_DIR / "offers.json"


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _load_unlocked(filepath: Path) -> list:
    """Load a JSON list file (caller MUST hold _file_lock)."""
    if not filepath.exists():
        return []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            log.warning("Expected list in %s, got %s", filepath, type(data).__name__)
            return []
        return data
    except (json.JSONDecodeError, OSError) as exc:
        log.error("Failed to load %s: %s", filepath, exc)
        return []


def _save_unlocked(filepath: Path, data: list):
    """Save a JSON list file atomically (caller MUST hold _file_lock)."""
    tmp = filepath.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(filepath)
    except OSError as exc:
        log.error("Failed to save %s: %s", filepath, exc)
        if tmp.exists():
            tmp.unlink()


def _load(filepath: Path) -> list:
    """Thread-safe load of a JSON list file."""
    with _file_lock:
        return _load_unlocked(filepath)


def _save(filepath: Path, data: list):
    """Thread-safe save of a JSON list file."""
    with _file_lock:
        _save_unlocked(filepath, data)


# ── LEADS ─────────────────────────────────────────────────────────────────────

def add_lead(lead: dict) -> str:
    with _file_lock:
        leads = _load_unlocked(LEADS_FILE)
        lead_id = f"L{uuid.uuid4().hex[:10]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        new_lead = {
            "lead_id":          lead_id,
            "name":             lead.get("name", ""),
            "mobile":           lead.get("mobile", ""),
            "alternate_mobile": lead.get("alternate_mobile", ""),
            "whatsapp":         lead.get("whatsapp", ""),
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
            # Family profiling fields for future sales
            "occupation":       lead.get("occupation", ""),
            "family_members":   lead.get("family_members", ""),
            "spouse_name":      lead.get("spouse_name", ""),
            "spouse_interest":  lead.get("spouse_interest", ""),
            "children_count":   lead.get("children_count", 0),
            "children_ages":    lead.get("children_ages", ""),
            "family_upsell":    lead.get("family_upsell", ""),
            "age_estimate":     lead.get("age_estimate", ""),
        }
        leads.append(new_lead)
        _save_unlocked(LEADS_FILE, leads)
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
    with _file_lock:
        leads = _load_unlocked(LEADS_FILE)
        for lead in leads:
            if str(lead.get("lead_id", "")) == lead_id:
                lead.update(updates)
                _save_unlocked(LEADS_FILE, leads)
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
    with _file_lock:
        calls = _load_unlocked(CALLS_FILE)
        log_id = f"C{uuid.uuid4().hex[:10]}"
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
        _save_unlocked(CALLS_FILE, calls)
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
    with _file_lock:
        offers = _load_unlocked(OFFERS_FILE)
        oid = f"O{uuid.uuid4().hex[:10]}"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        offers.append({
            "offer_id":    oid,
            "title":       offer.get("title", ""),
            "description": offer.get("description", ""),
            "valid_till":  offer.get("valid_till", ""),
            "models":      offer.get("models", ""),
            "uploaded_at": now,
        })
        _save_unlocked(OFFERS_FILE, offers)
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
    with _file_lock:
        settings = _load_unlocked(SETTINGS_FILE) if SETTINGS_FILE.exists() else []
        for r in settings:
            if r.get("key") == key:
                r["value"] = value
                _save_unlocked(SETTINGS_FILE, settings)
                return
        settings.append({"key": key, "value": value})
        _save_unlocked(SETTINGS_FILE, settings)
