"""Integration tests for the optimize API endpoint."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from opti_mind.main import app

client = TestClient(app)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_optimize_facility_location_success() -> None:
    fixture = str(FIXTURE_DIR / "facility_location.csv")
    response = client.post(
        "/api/v1/optimize",
        json={"source": fixture, "business_goal": "minimize total cost"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("success", "partial")
    assert body["ir"] is not None
    assert body["solution"] is not None
    assert isinstance(body["ir"], dict)
    assert isinstance(body["solution"], dict)
    assert isinstance(body["solution"]["objective_value"], (int, float))


def test_optimize_knapsack_success() -> None:
    fixture = str(FIXTURE_DIR / "knapsack.csv")
    response = client.post(
        "/api/v1/optimize",
        json={"source": fixture, "business_goal": "maximize total value"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("success", "partial")
    assert body["ir"] is not None
    assert body["solution"] is not None
    assert isinstance(body["solution"]["objective_value"], (int, float))


def test_optimize_missing_source_field() -> None:
    response = client.post("/api/v1/optimize", json={})
    assert response.status_code == 422


def test_optimize_invalid_source_path() -> None:
    response = client.post(
        "/api/v1/optimize",
        json={"source": "/nonexistent/path/file.csv"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in ("error", "partial")
    assert len(body["errors"]) > 0
