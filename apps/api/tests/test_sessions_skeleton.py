"""Phase A skeleton tests for /sessions (CMP-609).

Coverage:

- 익명 + 비익명 Supabase 토큰 모두 ``POST /sessions`` 가 허용된다.
- ``GET /sessions/{id}`` 은 owner subject 만 본인 row 를 본다 (다른 owner = 404).
- ``PUT /sessions/{id}/address`` 가 ``session_addresses`` row 를 upsert 하고
  세션 status 를 ``address_ready`` 로 전이한다.
- legacy ``x-jippin-anon-id`` 헤더는 무시된다 (auth 는 Supabase 토큰 SSOT).
- bearer 누락 시 표준 error envelope (code/message/request_id/timestamp) 가
  내려간다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.main import create_app
from src.services import main_flow

from . import _supabase_helpers as helpers


@pytest.fixture(autouse=True)
def _clear_state(monkeypatch):
    helpers.set_supabase_env(monkeypatch)
    get_settings.cache_clear()
    main_flow._reset_for_tests()
    yield
    main_flow._reset_for_tests()
    get_settings.cache_clear()


def _client(monkeypatch) -> tuple[TestClient, str, str, dict]:
    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    return TestClient(create_app()), pem, jwk["kid"], jwk


def test_create_session_allows_non_anonymous_user(monkeypatch):
    client, pem, kid, _ = _client(monkeypatch)
    token, subject = helpers.mint_token(pem, kid, is_anonymous=False)
    with client:
        response = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == str(subject)
    assert body["is_anonymous_owner"] is False
    assert body["status"] == "draft"


def test_create_session_allows_anonymous_supabase_token(monkeypatch):
    client, pem, kid, _ = _client(monkeypatch)
    token, subject = helpers.mint_token(pem, kid, is_anonymous=True)
    with client:
        response = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
    assert response.status_code == 201
    body = response.json()
    assert body["user_id"] == str(subject)
    assert body["is_anonymous_owner"] is True


def test_get_session_owner_only(monkeypatch):
    client, pem, kid, _ = _client(monkeypatch)
    owner_token, _ = helpers.mint_token(pem, kid)
    with client:
        created = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={},
        ).json()
        session_id = created["id"]

        # 같은 owner 토큰으로는 200.
        ok = client.get(
            f"/sessions/{session_id}",
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert ok.status_code == 200
        assert ok.json()["id"] == session_id

        # 다른 owner 토큰으로는 404 (정보 누수 방지).
        other_token, _ = helpers.mint_token(pem, kid)
        forbidden = client.get(
            f"/sessions/{session_id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        assert forbidden.status_code == 404
        assert forbidden.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_put_session_address_transitions_to_address_ready(monkeypatch):
    client, pem, kid, _ = _client(monkeypatch)
    token, _ = helpers.mint_token(pem, kid)
    with client:
        created = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        ).json()
        session_id = created["id"]

        upsert = client.put(
            f"/sessions/{session_id}/address",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "road_address": "서울 강남구 테헤란로 1",
                "apartment_name": "예시아파트",
                "building_dong": "101동",
                "unit_ho": "1502호",
                "exclusive_area_m2": "84.99",
                "size_type": "84A",
            },
        )
        assert upsert.status_code == 200
        addr = upsert.json()
        assert addr["apartment_name"] == "예시아파트"
        assert addr["exclusive_area_m2"] == "84.99"

        # 같은 endpoint 를 다시 호출하면 address_id 가 유지되며 idempotent 다.
        upsert2 = client.put(
            f"/sessions/{session_id}/address",
            headers={"Authorization": f"Bearer {token}"},
            json={"apartment_name": "예시아파트2"},
        )
        assert upsert2.status_code == 200
        assert upsert2.json()["id"] == addr["id"]

        # 세션 status 가 address_ready 로 전이.
        after = client.get(
            f"/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        assert after["address_id"] == addr["id"]
        assert after["status"] == "address_ready"


def test_legacy_anonymous_header_is_ignored(monkeypatch):
    """legacy ``x-jippin-anon-id`` 헤더는 새 라우터에 받혀들여지지 않는다."""

    client, pem, kid, _ = _client(monkeypatch)
    token, subject = helpers.mint_token(pem, kid)
    with client:
        response = client.post(
            "/sessions",
            headers={
                "Authorization": f"Bearer {token}",
                # 옛 phase 의 anon 식별 헤더. 새 skeleton 은 무시해야 한다.
                "x-jippin-anon-id": "00000000-0000-0000-0000-deadbeefdead",
            },
            json={},
        )
    assert response.status_code == 201
    # owner 는 무조건 Supabase ``sub`` 다 — legacy header 의 값이 들어가지 않는다.
    assert response.json()["user_id"] == str(subject)


def test_missing_bearer_returns_standard_error_envelope(monkeypatch):
    client, _pem, _kid, _ = _client(monkeypatch)
    with client:
        response = client.post("/sessions", json={})
    assert response.status_code == 401
    body = response.json()
    error = body["error"]
    assert error["code"] == "SUPABASE_SESSION_BEARER_REQUIRED"
    assert error["message"]
    assert error["request_id"]
    assert error["timestamp"]
