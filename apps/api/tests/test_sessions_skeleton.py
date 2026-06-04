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


def test_anonymous_session_has_expires_at_from_ttl_setting(monkeypatch):
    """익명 사전검토 세션은 ``ANON_SESSION_TTL_DAYS`` 만큼 expires_at 가 잡힌다.

    Phase D cleanup cron 이 만료 익명 artifact 를 정리할 수 있어야 한다.
    """

    import datetime as datetime_module

    monkeypatch.setenv("ANON_SESSION_TTL_DAYS", "7")
    get_settings.cache_clear()

    client, pem, kid, _ = _client(monkeypatch)
    anon_token, _ = helpers.mint_token(pem, kid, is_anonymous=True)
    perm_token, _ = helpers.mint_token(pem, kid, is_anonymous=False)
    with client:
        anon_resp = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {anon_token}"},
            json={},
        )
        perm_resp = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {perm_token}"},
            json={},
        )
    assert anon_resp.status_code == 201
    assert perm_resp.status_code == 201
    anon_body = anon_resp.json()
    perm_body = perm_resp.json()

    # 익명 owner 는 expires_at 가 ttl 만큼 미래로 설정된다.
    assert anon_body["expires_at"] is not None
    created = datetime_module.datetime.fromisoformat(anon_body["created_at"])
    expires = datetime_module.datetime.fromisoformat(anon_body["expires_at"])
    delta = expires - created
    assert 7 * 24 * 3600 - 5 <= delta.total_seconds() <= 7 * 24 * 3600 + 5

    # permanent user 의 expiry 정책은 별도 — 본 skeleton 단계에선 null.
    assert perm_body["expires_at"] is None


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
        # board P2-1 회귀: 두 번째 PUT 이 ``unit_ho`` 만 보내도 이미 저장된
        # ``road_address`` / ``apartment_name`` 등은 그대로 보존되어야 한다.
        upsert2 = client.put(
            f"/sessions/{session_id}/address",
            headers={"Authorization": f"Bearer {token}"},
            json={"unit_ho": "1503호"},
        )
        assert upsert2.status_code == 200
        merged = upsert2.json()
        assert merged["id"] == addr["id"]
        assert merged["road_address"] == "서울 강남구 테헤란로 1"
        assert merged["apartment_name"] == "예시아파트"
        assert merged["building_dong"] == "101동"
        assert merged["exclusive_area_m2"] == "84.99"
        assert merged["size_type"] == "84A"
        assert merged["unit_ho"] == "1503호"

        # 세션 status 가 address_ready 로 전이.
        after = client.get(
            f"/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        assert after["address_id"] == addr["id"]
        assert after["status"] == "address_ready"


def test_put_session_address_rejects_empty_payload(monkeypatch):
    """빈 payload 로는 ``address_ready`` 전이를 허용하지 않는다 (board P2-2)."""

    client, pem, kid, _ = _client(monkeypatch)
    token, _ = helpers.mint_token(pem, kid)
    with client:
        created = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        ).json()
        session_id = created["id"]

        rejected = client.put(
            f"/sessions/{session_id}/address",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "INSUFFICIENT_ADDRESS_DATA"

        # status 는 여전히 draft 그대로.
        after = client.get(
            f"/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        assert after["status"] == "draft"
        assert after["address_id"] is None


def test_put_session_address_rejects_non_identifying_metadata(monkeypatch):
    """``apartment_name`` 단독은 식별력이 없어 reject."""

    client, pem, kid, _ = _client(monkeypatch)
    token, _ = helpers.mint_token(pem, kid)
    with client:
        created = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        ).json()
        session_id = created["id"]

        rejected = client.put(
            f"/sessions/{session_id}/address",
            headers={"Authorization": f"Bearer {token}"},
            json={"apartment_name": "예시아파트"},
        )
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "INSUFFICIENT_ADDRESS_DATA"


def test_put_session_address_accepts_building_identity_only(monkeypatch):
    """PNU / building_identity 만으로도 sufficient — road/jibun 없이 통과."""

    client, pem, kid, _ = _client(monkeypatch)
    token, _ = helpers.mint_token(pem, kid)
    with client:
        created = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        ).json()
        session_id = created["id"]

        ok = client.put(
            f"/sessions/{session_id}/address",
            headers={"Authorization": f"Bearer {token}"},
            json={"building_identity": {"pnu": "1100012300100001"}},
        )
        assert ok.status_code == 200
        assert ok.json()["building_identity"] == {"pnu": "1100012300100001"}

        after = client.get(
            f"/sessions/{session_id}",
            headers={"Authorization": f"Bearer {token}"},
        ).json()
        assert after["status"] == "address_ready"


def test_non_anonymous_access_clears_anon_owner_and_expires_at(monkeypatch):
    """``linkIdentity()`` conversion 회귀 (board P2-5).

    같은 ``auth.users.id`` 가 익명 token 으로 세션을 만들고, 이후 동일 UUID 가
    permanent token 으로 다시 접근하면 ``is_anonymous_owner`` 와
    ``expires_at`` 이 정리되어야 한다. 그래야 가입 완료 사용자의 사전검토
    artifact 가 익명 TTL cleanup 으로 삭제되지 않는다.
    """

    client, pem, kid, _ = _client(monkeypatch)
    anon_token, subject = helpers.mint_token(pem, kid, is_anonymous=True)
    with client:
        created = client.post(
            "/sessions",
            headers={"Authorization": f"Bearer {anon_token}"},
            json={},
        ).json()
        assert created["is_anonymous_owner"] is True
        assert created["expires_at"] is not None
        session_id = created["id"]

        # 같은 sub UUID 로 발급된 non-anonymous token (Supabase linkIdentity 시뮬).
        perm_token, perm_subject = helpers.mint_token(
            pem, kid, sub=str(subject), is_anonymous=False
        )
        assert perm_subject == subject
        promoted = client.get(
            f"/sessions/{session_id}",
            headers={"Authorization": f"Bearer {perm_token}"},
        ).json()

    assert promoted["is_anonymous_owner"] is False
    assert promoted["expires_at"] is None
    assert promoted["user_id"] == str(subject)


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
