"""Integration tests for the session-based conversational API."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from opti_mind.main import app

client = TestClient(app)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "knapsack.csv"


def test_create_session_success() -> None:
    with FIXTURE.open("rb") as f:
        response = client.post(
            "/api/v1/sessions",
            files={"file": ("knapsack.csv", f, "text/csv")},
            data={"business_goal": "maximize total value"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"]
    assert body["status"] in ("success", "awaiting_input", "created")
    assert len(body["messages"]) >= 1


def test_get_session_success() -> None:
    with FIXTURE.open("rb") as f:
        create_resp = client.post(
            "/api/v1/sessions",
            files={"file": ("knapsack.csv", f, "text/csv")},
        )
    session_id = create_resp.json()["session_id"]

    get_resp = client.get(f"/api/v1/sessions/{session_id}")
    assert get_resp.status_code == 200
    body = get_resp.json()
    assert body["session_id"] == session_id
    assert len(body["messages"]) >= 1


def test_chat_nonexistent_session_returns_404() -> None:
    response = client.post(
        "/api/v1/sessions/nonexistent-id/chat",
        json={"message": "use default values"},
    )
    assert response.status_code == 404


def test_get_session_events_success() -> None:
    """The events endpoint returns the JSONL log for an existing session."""
    with FIXTURE.open("rb") as f:
        create_resp = client.post(
            "/api/v1/sessions",
            files={"file": ("knapsack.csv", f, "text/csv")},
        )
    session_id = create_resp.json()["session_id"]

    events_resp = client.get(f"/api/v1/sessions/{session_id}/events")
    assert events_resp.status_code == 200
    events = events_resp.json()
    assert isinstance(events, list)
    assert len(events) >= 1
    assert all("event_type" in e for e in events)
    assert all("sequence" in e for e in events)


def test_get_session_events_not_found() -> None:
    """The events endpoint returns 404 for a nonexistent session."""
    response = client.get("/api/v1/sessions/nonexistent-id/events")
    assert response.status_code == 404
