from fastapi.testclient import TestClient

from opti_mind.core.exceptions import OptiMindError
from opti_mind.main import app


def _raise_optimind_error() -> None:
    raise OptiMindError("test_error", "boom")


app.add_api_route("/__raise", _raise_optimind_error, methods=["GET"])


def test_error_handler_returns_structured_response() -> None:
    client = TestClient(app)
    response = client.get("/__raise")
    assert response.status_code == 400
    body = response.json()
    assert body["code"] == "test_error"
    assert body["message"] == "boom"
