"""Tests for FastAPI triage endpoint and schema validation."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.idempotency import init_db


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    """Sets up an isolated test database for each test."""
    db_file = tmp_path / "test_triage.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_file))
    init_db(str(db_file))
    return str(db_file)


client = TestClient(app)


def test_health_check():
    """Verifies that the /health endpoint is operational."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "dhaba-triage"


def test_valid_ticket_triage():
    """Verifies that a valid ticket returns 200 OK with the complete TriageResponse schema."""
    payload = {
        "id": "T-TEST-01",
        "received_at": "2026-09-02T09:14:00+05:30",
        "subject": "charged 249 without telling me",
        "body": "i only paid 1 rupee to try the app. today 249 is gone from my account. refund it.",
        "purchases": [
            {"id": "pay_1", "type": "trial", "amount_inr": 1, "status": "successful", "at": "2026-08-31T20:02:00+05:30"},
            {"id": "pay_2", "type": "renewal", "amount_inr": 249, "status": "successful", "at": "2026-09-01T20:04:00+05:30"}
        ],
        "app_opens_since_renewal": 0
    }
    response = client.post("/triage", json=payload)
    assert response.status_code == 200
    data = response.json()

    assert data["ticket_id"] == "T-TEST-01"
    assert "category" in data
    assert "severity" in data
    assert "refund" in data
    assert "decision" in data["refund"]
    assert "amount_inr" in data["refund"]
    assert "reason" in data["refund"]
    assert "reply_draft" in data
    assert "needs_human" in data
    assert "confidence" in data
    assert isinstance(data["confidence"], float)
    assert 0.0 <= data["confidence"] <= 1.0


def test_invalid_ticket_schema_returns_422():
    """Verifies that malformed ticket payloads are rejected with 422 Unprocessable Entity."""
    # Missing required 'id' and 'received_at'
    invalid_payload = {
        "subject": "broken ticket",
        "body": "no id provided"
    }
    response = client.post("/triage", json=invalid_payload)
    assert response.status_code == 422


def test_all_12_official_tickets_replay():
    """Replays all 12 tickets from dhaba_tickets.json through POST /triage and validates outputs."""
    fixture_path = Path(__file__).resolve().parent.parent / "dhaba_tickets.json"
    with open(fixture_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    tickets = data.get("tickets", [])
    assert len(tickets) == 12

    for ticket in tickets:
        response = client.post("/triage", json=ticket)
        assert response.status_code == 200, f"Failed for ticket {ticket['id']}: {response.text}"
        res_data = response.json()
        assert res_data["ticket_id"] == ticket["id"]
        assert res_data["category"] in [
            "billing", "technical_issue", "account", "cancellation", "payment_issue",
            "feature_request", "invoice", "subscription_question", "fraud", "unknown"
        ]
        assert res_data["severity"] in ["low", "medium", "high", "critical"]
        assert res_data["refund"]["decision"] in ["approved", "rejected", "no_refund", "human_review"]
