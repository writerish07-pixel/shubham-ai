"""
Automated test suite for Shubham Motors AI Voice Agent.
Tests cover: API endpoints, storage layer, lead management,
call handling, and configuration validation.
"""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Set minimal env vars before importing app modules
os.environ.setdefault("EXOTEL_API_KEY", "test_key")
os.environ.setdefault("EXOTEL_API_TOKEN", "test_token")
os.environ.setdefault("GROQ_API_KEY", "test_groq_key")
os.environ.setdefault("SARVAM_API_KEY", "test_sarvam_key")
os.environ.setdefault("DEEPGRAM_API_KEY", "test_deepgram_key")
os.environ.setdefault("PUBLIC_URL", "http://localhost:5000")

import config
import sheets_manager as db


# -- CONFIG TESTS --------------------------------------------------------------

class TestConfig:
    def test_validate_config_returns_list(self):
        warnings = config.validate_config()
        assert isinstance(warnings, list)

    def test_sales_team_is_list(self):
        assert isinstance(config.SALES_TEAM, list)

    def test_working_days_parsed(self):
        assert isinstance(config.WORKING_DAYS, list)
        assert len(config.WORKING_DAYS) > 0

    def test_working_hours_valid(self):
        assert 0 <= config.WORKING_HOURS_START < 24
        assert 0 < config.WORKING_HOURS_END <= 24
        assert config.WORKING_HOURS_START < config.WORKING_HOURS_END

    def test_max_followup_attempts_positive(self):
        assert config.MAX_FOLLOWUP_ATTEMPTS > 0


# -- STORAGE TESTS -------------------------------------------------------------

class TestSheetsManager:
    """Tests for thread-safe JSON storage layer."""

    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig_data_dir = db.DATA_DIR
        db.DATA_DIR = Path(self._tmpdir)
        db.LEADS_FILE = db.DATA_DIR / "leads.json"
        db.CALLS_FILE = db.DATA_DIR / "calls.json"
        db.OFFERS_FILE = db.DATA_DIR / "offers.json"

    def teardown_method(self):
        db.DATA_DIR = self._orig_data_dir
        db.LEADS_FILE = db.DATA_DIR / "leads.json"
        db.CALLS_FILE = db.DATA_DIR / "calls.json"
        db.OFFERS_FILE = db.DATA_DIR / "offers.json"

    def test_add_and_get_lead(self):
        lead_id = db.add_lead({"name": "Test User", "mobile": "+919999999999"})
        assert lead_id.startswith("L")
        leads = db.get_all_leads()
        assert len(leads) == 1
        assert leads[0]["name"] == "Test User"

    def test_get_lead_by_id(self):
        lead_id = db.add_lead({"name": "Lookup User", "mobile": "+918888888888"})
        found = db.get_lead_by_id(lead_id)
        assert found is not None
        assert found["name"] == "Lookup User"

    def test_get_lead_by_mobile(self):
        db.add_lead({"name": "Mobile User", "mobile": "+917777777777"})
        found = db.get_lead_by_mobile("+917777777777")
        assert found is not None
        assert found["name"] == "Mobile User"

    def test_update_lead(self):
        lead_id = db.add_lead({"name": "Update Me", "mobile": "+916666666666"})
        db.update_lead(lead_id, {"status": "hot"})
        updated = db.get_lead_by_id(lead_id)
        assert updated["status"] == "hot"

    def test_log_call(self):
        log_id = db.log_call({
            "call_sid": "TEST123",
            "mobile": "+915555555555",
            "duration_sec": 30,
        })
        assert log_id.startswith("C")

    def test_add_offer(self):
        offer_id = db.add_offer({
            "title": "Diwali Sale",
            "description": "20% off on all bikes",
        })
        assert offer_id.startswith("O")

    def test_get_active_offers(self):
        db.add_offer({"title": "Offer 1"})
        db.add_offer({"title": "Offer 2"})
        offers = db.get_active_offers()
        assert len(offers) == 2

    def test_uuid_uniqueness(self):
        """IDs should never collide (UUID-based)."""
        ids = set()
        for i in range(100):
            lid = db.add_lead({"name": f"User {i}", "mobile": f"+9100000000{i:02d}"})
            ids.add(lid)
        assert len(ids) == 100

    def test_concurrent_writes(self):
        """Multiple threads writing simultaneously should not corrupt data."""
        errors = []

        def writer(n):
            try:
                for i in range(10):
                    db.add_lead({"name": f"Thread-{n}-{i}", "mobile": f"+91{n:05d}{i:05d}"})
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        leads = db.get_all_leads()
        assert len(leads) == 50

    def test_load_empty_file(self):
        leads = db.get_all_leads()
        assert leads == []

    def test_followup_leads(self):
        db.add_lead({
            "name": "Followup User",
            "mobile": "+914444444444",
            "next_followup": "2020-01-01 10:00",
            "status": "warm",
        })
        # The add_lead function sets status to "new", not "warm"
        # We need to update it after creation
        leads = db.get_all_leads()
        lead_id = leads[0]["lead_id"]
        db.update_lead(lead_id, {
            "next_followup": "2020-01-01 10:00",
            "status": "warm",
        })
        due = db.get_leads_due_for_followup()
        assert len(due) >= 1


# -- LEAD MANAGER TESTS -------------------------------------------------------

class TestLeadManager:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig_data_dir = db.DATA_DIR
        db.DATA_DIR = Path(self._tmpdir)
        db.LEADS_FILE = db.DATA_DIR / "leads.json"
        db.CALLS_FILE = db.DATA_DIR / "calls.json"
        db.OFFERS_FILE = db.DATA_DIR / "offers.json"

    def teardown_method(self):
        db.DATA_DIR = self._orig_data_dir
        db.LEADS_FILE = db.DATA_DIR / "leads.json"
        db.CALLS_FILE = db.DATA_DIR / "calls.json"
        db.OFFERS_FILE = db.DATA_DIR / "offers.json"

    def test_add_leads_from_import(self):
        from lead_manager import add_leads_from_import
        leads = [
            {"name": "Import1", "mobile": "+913333333333"},
            {"name": "Import2", "mobile": "+912222222222"},
        ]
        ids = add_leads_from_import(leads)
        assert len(ids) == 2

    def test_import_skips_duplicates(self):
        from lead_manager import add_leads_from_import
        leads = [{"name": "Dup", "mobile": "+911111111111"}]
        add_leads_from_import(leads)
        ids2 = add_leads_from_import(leads)
        assert len(ids2) == 0

    def test_import_skips_empty_mobile(self):
        from lead_manager import add_leads_from_import
        leads = [{"name": "NoMobile"}]
        ids = add_leads_from_import(leads)
        assert len(ids) == 0

    def test_get_dashboard_stats(self):
        from lead_manager import get_dashboard_stats
        stats = get_dashboard_stats()
        assert "total" in stats


# -- CALL HANDLER TESTS -------------------------------------------------------

class TestCallHandler:
    def setup_method(self):
        self._tmpdir = tempfile.mkdtemp()
        self._orig_data_dir = db.DATA_DIR
        db.DATA_DIR = Path(self._tmpdir)
        db.LEADS_FILE = db.DATA_DIR / "leads.json"
        db.CALLS_FILE = db.DATA_DIR / "calls.json"
        db.OFFERS_FILE = db.DATA_DIR / "offers.json"

    def teardown_method(self):
        db.DATA_DIR = self._orig_data_dir
        db.LEADS_FILE = db.DATA_DIR / "leads.json"
        db.CALLS_FILE = db.DATA_DIR / "calls.json"
        db.OFFERS_FILE = db.DATA_DIR / "offers.json"

    def test_start_and_end_session(self):
        from call_handler import start_call_session, active_calls
        start_call_session("SID_TEST_101", "+919876543210", lead_id="")
        assert "SID_TEST_101" in active_calls
        session = active_calls["SID_TEST_101"]
        assert session["caller"] == "+919876543210"

    def test_start_session_without_lead(self):
        from call_handler import start_call_session, active_calls
        start_call_session("SID_TEST_102", "+919876543211")
        assert "SID_TEST_102" in active_calls


# -- FASTAPI ENDPOINT TESTS ---------------------------------------------------

class TestAPIEndpoints:
    """Test FastAPI endpoints using TestClient."""

    @pytest.fixture(autouse=True)
    def setup_client(self, tmp_path):
        db.DATA_DIR = tmp_path
        db.LEADS_FILE = tmp_path / "leads.json"
        db.CALLS_FILE = tmp_path / "calls.json"
        db.OFFERS_FILE = tmp_path / "offers.json"

        with patch("main.start_scheduler"), \
             patch("main.stop_scheduler"), \
             patch("main.scrape_hero_website"):
            from fastapi.testclient import TestClient
            from main import app
            self.client = TestClient(app)
            yield

    def test_health(self):
        r = self.client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"

    def test_root_returns_json(self):
        r = self.client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "running"

    def test_get_leads_empty(self):
        r = self.client.get("/api/leads")
        assert r.status_code == 200
        assert r.json() == []

    def test_add_lead(self):
        r = self.client.post("/api/leads/add", json={
            "name": "API Test Lead",
            "mobile": "+919000000001",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["success"] is True
        assert "lead_id" in data

    def test_get_stats(self):
        r = self.client.get("/api/stats")
        assert r.status_code == 200
        data = r.json()
        assert "total" in data

    def test_active_calls(self):
        r = self.client.get("/api/active-calls")
        assert r.status_code == 200
        data = r.json()
        assert "active_calls" in data

    def test_incoming_call_webhook(self):
        r = self.client.post("/call/incoming", data={
            "CallSid": "INCOMING_TEST_001",
            "From": "+919876543210",
        })
        assert r.status_code == 200
        assert "application/xml" in r.headers.get("content-type", "")

    def test_incoming_call_missing_sid(self):
        r = self.client.post("/call/incoming", data={
            "From": "+919876543210",
        })
        assert r.status_code == 200
        assert "Hangup" in r.text

    def test_status_webhook(self):
        r = self.client.post("/call/status", data={
            "CallSid": "STATUS_TEST_001",
            "Status": "completed",
            "Duration": "45",
        })
        assert r.status_code == 200

    def test_status_webhook_empty_duration(self):
        r = self.client.post("/call/status", data={
            "CallSid": "STATUS_TEST_002",
            "Status": "completed",
            "Duration": "",
        })
        assert r.status_code == 200

    def test_make_call_missing_mobile(self):
        r = self.client.post("/api/call/make", json={})
        assert r.status_code == 400
