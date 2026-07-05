from fastapi.testclient import TestClient

from opti_mind.main import app


def test_health_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == "0.1.0"
    assert "available_solver_backends" in body
    assert isinstance(body["available_solver_backends"], list)
