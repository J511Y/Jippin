from __future__ import annotations

import uuid

from fastapi import Request
from fastapi.testclient import TestClient

from src.errors import ZippinException
from src.main import create_app
from src.middleware import request_log
from src.middleware.request_log import (
    build_request_log_record,
    classify_device,
    extract_ip_addrs,
)


def test_request_log_captures_request_id_and_duration(monkeypatch):
    records = []
    request_id = uuid.uuid4()
    monkeypatch.setattr(request_log, "schedule_request_log_insert", records.append)

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/healthz",
            headers={
                "x-request-id": str(request_id),
                "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "x-forwarded-for": "203.0.113.9, 10.0.0.10",
                "cf-ipcountry": "KR",
                "x-vercel-ip-region": "11",
            },
        )

    assert response.status_code == 200
    assert len(records) == 1
    record = records[0]
    assert record["request_id"] == request_id
    assert record["duration_ms"] >= 1
    assert record["response_code"] == 200
    assert record["method"] == "GET"
    assert record["device"] == "pc"
    assert record["country"] == "KR"
    assert record["region"] == "11"
    assert record["last_ip"] == "203.0.113.9"


def test_request_log_redacts_body_and_query_without_consuming_body(monkeypatch):
    records = []
    monkeypatch.setattr(request_log, "schedule_request_log_insert", records.append)

    app = create_app()

    @app.post("/_echo")
    async def _echo(request: Request):
        body = await request.json()
        return {"received": body}

    with TestClient(app) as client:
        response = client.post(
            "/_echo?token=query-token&safe=value",
            json={
                "email": "user@example.com",
                "password": "plain-text",
                "nested": {"access_token": "secret-token", "ok": True},
            },
        )

    assert response.status_code == 200
    assert response.json()["received"]["password"] == "plain-text"
    assert len(records) == 1
    record = records[0]
    assert record["parameter"]["token"] == "[REDACTED]"
    assert record["parameter"]["safe"] == "value"
    assert record["body"]["email"] == "user@example.com"
    assert record["body"]["password"] == "[REDACTED]"
    assert record["body"]["nested"]["access_token"] == "[REDACTED]"


def test_request_log_parses_error_envelope(monkeypatch):
    records = []
    monkeypatch.setattr(request_log, "schedule_request_log_insert", records.append)

    app = create_app()

    @app.get("/_error")
    async def _error():
        raise ZippinException(
            "more data is required",
            code="INSUFFICIENT_DATA",
            http_status=400,
        )

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/_error")

    assert response.status_code == 400
    record = records[0]
    assert record["response_code"] == 400
    assert record["response_message"] == "more data is required"
    assert record["error_code"] == "INSUFFICIENT_DATA"


def test_request_log_schedule_failure_does_not_affect_response(monkeypatch):
    def _raise(_record):
        raise RuntimeError("schedule failed")

    monkeypatch.setattr(request_log, "schedule_request_log_insert", _raise)

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/healthz")

    assert response.status_code == 200


def test_request_log_truncates_large_body(monkeypatch):
    records = []
    monkeypatch.setattr(request_log, "schedule_request_log_insert", records.append)

    app = create_app()

    @app.post("/_large")
    async def _large(request: Request):
        return {"bytes": len(await request.body())}

    payload = {"safe": "x" * 5000, "password": "secret"}
    with TestClient(app) as client:
        response = client.post("/_large", json=payload)

    assert response.status_code == 200
    assert response.json()["bytes"] > 4096
    assert records[0]["body"]["_truncated"] == "[TRUNCATED]"


def test_request_log_helper_classifies_devices():
    assert classify_device("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X)") == "tablet"
    assert classify_device("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0) Mobile") == "mobile"
    assert classify_device("Mozilla/5.0 (X11; Linux x86_64)") == "pc"
    assert classify_device(None) == "other"


def test_request_log_helper_orders_last_ip_as_client():
    class _Headers(dict):
        def get(self, key, default=None):
            return super().get(key.lower(), default)

    addrs = extract_ip_addrs(
        _Headers({"x-forwarded-for": "203.0.113.1, 10.0.0.5"}),
        "10.0.0.9",
    )

    assert addrs == ["10.0.0.9", "10.0.0.5", "203.0.113.1"]
    assert addrs[-1] == "203.0.113.1"


def test_request_id_string_is_deterministically_mapped_to_uuid():
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "scheme": "http",
            "client": ("testclient", 50000),
        }
    )
    request.state.request_id = "req-test-123"

    first = build_request_log_record(
        request=request,
        request_body=b"",
        response_body=b"",
        response_status=200,
        duration_ms=1,
    )
    second = build_request_log_record(
        request=request,
        request_body=b"",
        response_body=b"",
        response_status=200,
        duration_ms=1,
    )

    assert first["request_id"] == second["request_id"]
    assert isinstance(first["request_id"], uuid.UUID)
