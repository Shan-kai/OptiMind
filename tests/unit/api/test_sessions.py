"""Tests for the session-based conversational API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from opti_mind.main import app

client = TestClient(app)

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "facility_location.csv"


def test_create_session_success():
    """Uploading a valid CSV should create a session and run to completion."""
    with FIXTURE.open("rb") as f:
        response = client.post(
            "/api/v1/sessions",
            files={"file": ("facility_location.csv", f, "text/csv")},
            data={"business_goal": "minimize total cost"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("success", "awaiting_input")
    assert body["session_id"]
    assert len(body["messages"]) >= 1


def test_get_session():
    """GET /sessions/{id} should return the current session state."""
    with FIXTURE.open("rb") as f:
        response = client.post(
            "/api/v1/sessions",
            files={"file": ("facility_location.csv", f, "text/csv")},
        )
    body = response.json()
    session_id = body["session_id"]

    get_response = client.get(f"/api/v1/sessions/{session_id}")
    assert get_response.status_code == 200
    get_body = get_response.json()
    assert get_body["session_id"] == session_id
    assert get_body["status"] == body["status"]


def test_get_session_not_found():
    response = client.get("/api/v1/sessions/nonexistent-id")
    assert response.status_code == 404
