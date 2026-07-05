from fastapi import FastAPI
from fastapi.testclient import TestClient

from opti_mind.api.middleware import REQUEST_ID_HEADER, RequestContextMiddleware


def test_middleware_generates_request_id() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/test")
    def test_endpoint() -> dict[str, str]:
        return {"ok": "true"}

    client = TestClient(app)
    response = client.get("/test")
    assert response.status_code == 200
    assert REQUEST_ID_HEADER in response.headers
    assert response.headers[REQUEST_ID_HEADER]


def test_middleware_reuses_incoming_request_id() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/test")
    def test_endpoint() -> dict[str, str]:
        return {"ok": "true"}

    client = TestClient(app)
    custom_id = "custom-request-id-abc"
    response = client.get("/test", headers={REQUEST_ID_HEADER: custom_id})
    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == custom_id
