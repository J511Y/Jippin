from fastapi.testclient import TestClient

from src.errors import ZippinException
from src.main import create_app


def test_healthz_status_ok_with_db_ok_in_test_mode():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["db"]["ok"] is True
    assert body["db"]["select_1"] == 1
    assert "version" in body
    assert "request_id" in body
    assert response.headers.get("x-request-id")


def test_healthz_propagates_incoming_request_id():
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/healthz", headers={"x-request-id": "req-test-123"})

    assert response.status_code == 200
    body = response.json()
    assert body["request_id"] == "req-test-123"
    assert response.headers.get("x-request-id") == "req-test-123"


def test_zippin_exception_emits_agents_md_envelope():
    app = create_app()

    @app.get("/_boom")
    async def _boom():
        raise ZippinException(
            "missing required input",
            code="INSUFFICIENT_DATA",
            http_status=400,
        )

    with TestClient(app) as client:
        response = client.get("/_boom")

    assert response.status_code == 400
    body = response.json()
    assert "error" in body
    err = body["error"]
    assert err["code"] == "INSUFFICIENT_DATA"
    assert err["message"] == "missing required input"
    assert "request_id" in err
    assert "timestamp" in err
