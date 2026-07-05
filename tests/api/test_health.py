"""Integration tests for the health-check endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient

from opti_mind.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "available_solver_backends" in body
    assert isinstance(body["available_solver_backends"], list)
    assert len(body["available_solver_backends"]) > 0
    assert "mock" in body["available_solver_backends"]
