from __future__ import annotations

import json
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
from src.middleware.request_log_redaction import REDACTED_VALUE


def _serialized(value):
    return json.dumps(value, default=str, sort_keys=True)


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
    assert record["url"] == "/_echo"
    assert "query-token" not in record["url"]
    assert "safe=value" not in record["url"]
    assert record["parameter"]["token"] == "[REDACTED]"
    assert record["parameter"]["safe"] == "value"
    assert record["body"]["email"] == "user@example.com"
    assert record["body"]["password"] == "[REDACTED]"
    assert record["body"]["nested"]["access_token"] == "[REDACTED]"


def test_request_log_text_body_never_persists_raw_secret_bytes(monkeypatch):
    records = []
    monkeypatch.setattr(request_log, "schedule_request_log_insert", records.append)

    app = create_app()

    @app.post("/_text")
    async def _text(request: Request):
        return {"bytes": len(await request.body())}

    payload = (
        b"Authorization: Bearer SECRET\n"
        b"password=hunter2\n"
        b"token=abc123\n"
        b"client_secret=cs_123"
    )
    with TestClient(app) as client:
        response = client.post(
            "/_text",
            content=payload,
            headers={"content-type": "text/plain"},
        )

    assert response.status_code == 200
    body = records[0]["body"]
    assert body == {"_content_type": "text/plain", "_bytes": len(payload)}
    serialized = _serialized(body)
    for leaked in ("Authorization", "SECRET", "hunter2", "abc123", "cs_123"):
        assert leaked not in serialized


def test_request_log_malformed_json_body_stores_metadata_only(monkeypatch):
    records = []
    monkeypatch.setattr(request_log, "schedule_request_log_insert", records.append)

    app = create_app()

    @app.post("/_malformed")
    async def _malformed(request: Request):
        return {"bytes": len(await request.body())}

    payload = b'{"password":"hunter2","token":"abc123"'
    with TestClient(app) as client:
        response = client.post(
            "/_malformed",
            content=payload,
            headers={"content-type": "application/json"},
        )

    assert response.status_code == 200
    body = records[0]["body"]
    assert body == {
        "_unparsable": True,
        "_content_type": "application/json",
        "_bytes": len(payload),
    }
    serialized = _serialized(body)
    for leaked in ("password", "hunter2", "token", "abc123"):
        assert leaked not in serialized


def test_request_log_redacts_expanded_sensitive_keys_in_params_and_body(monkeypatch):
    records = []
    monkeypatch.setattr(request_log, "schedule_request_log_insert", records.append)

    app = create_app()

    @app.post("/_sensitive")
    async def _sensitive(request: Request):
        return {"received": await request.json()}

    sensitive_keys = (
        "api_key",
        "apikey",
        "x_api_key",
        "x-api-key",
        "apiKey",
        "client_secret",
        "id_token",
        "refresh_token",
    )
    query = {key: f"query-secret-{index}" for index, key in enumerate(sensitive_keys)}
    body = {
        key: f"body-secret-{index}" for index, key in enumerate(sensitive_keys)
    } | {
        "nested": {"client_secret": "nested-secret"},
        "items": [{"id_token": "list-secret"}],
    }

    with TestClient(app) as client:
        response = client.post("/_sensitive", params=query, json=body)

    assert response.status_code == 200
    record = records[0]
    for key in sensitive_keys:
        assert record["parameter"][key] == REDACTED_VALUE
        assert record["body"][key] == REDACTED_VALUE
    assert record["body"]["nested"]["client_secret"] == REDACTED_VALUE
    assert record["body"]["items"][0]["id_token"] == REDACTED_VALUE

    serialized = _serialized(record["parameter"]) + _serialized(record["body"])
    for leaked in (
        "query-secret",
        "body-secret",
        "nested-secret",
        "list-secret",
    ):
        assert leaked not in serialized


def test_request_log_does_not_persist_sensitive_header_names_or_values(monkeypatch):
    records = []
    monkeypatch.setattr(request_log, "schedule_request_log_insert", records.append)

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/healthz",
            headers={
                "Authorization": "Bearer HEADERSECRET",
                "Cookie": "session=COOKIESECRET",
                "Set-Cookie": "server=SETCOOKIESECRET",
                "X-Api-Key": "APIKEYSECRET",
            },
        )

    assert response.status_code == 200
    serialized = _serialized(records[0]).lower()
    for leaked in (
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "headersecret",
        "cookiesecret",
        "setcookiesecret",
        "apikeysecret",
    ):
        assert leaked not in serialized


def test_request_log_sanitizes_referrer_query_and_fragment(monkeypatch):
    records = []
    monkeypatch.setattr(request_log, "schedule_request_log_insert", records.append)

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/healthz",
            headers={
                "Referer": "https://example.com/callback?token=ABC&state=xyz#frag"
            },
        )

    assert response.status_code == 200
    assert records[0]["referrer"] == "https://example.com/callback"
    assert "ABC" not in records[0]["referrer"]
    assert "token=" not in records[0]["referrer"]


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
