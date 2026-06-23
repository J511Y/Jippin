"""Regression — Phase A skeleton 이 legacy 익명 흐름을 부활시키지 않는지 검증.

DB 설계 정본 (``docs/plans/main-feature-db-schema-v0.1.md``) 의 정책:

> 비회원 사전검토는 Supabase Anonymous Sign-In 으로 만든 ``auth.users.id`` 를
> 소유권 키로 쓴다. 별도 ``anonymous_users`` 테이블이나 브라우저 로컬 UUID
> (``x-jippin-anon-id``, ``localStorage.jippin_anonymous_user_id``) 를 쓰지
> 않는다.

본 테스트는 새 Phase A 라우터가 다음 두 가지를 따르는지 확인한다:

1. 새 라우터는 ``/auth/anonymous-users`` 로 라우팅되지 않는다.
2. 새 라우터 경로 어디에도 ``x-jippin-anon-id`` 헤더에 의미를 부여하지
   않는다 (auth 는 Supabase 토큰 SSOT).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.main import create_app

from . import _supabase_helpers as helpers


@pytest.fixture(autouse=True)
def _clear_state(monkeypatch):
    helpers.set_supabase_env(monkeypatch)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_phase_a_routes_are_all_under_sessions_prefix():
    """Phase A public 라우터의 모든 경로가 /sessions 아래에 있는지 확인.

    legacy ``/anonymous`` / ``/anon`` prefix 가 재등장하면 즉시 잡힌다.
    또한 board P2-3 / P2-4 회귀: candidate snapshot 과 tool-call lifecycle
    endpoint 는 public 라우터에 mount 되지 않는다.
    """

    app = create_app()
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]

    expected = {
        "/sessions",
        "/sessions/{session_id}",
        "/sessions/{session_id}/address",
        "/sessions/{session_id}/floorplan-uploads",
        "/sessions/{session_id}/chat/messages",
    }
    missing = expected - paths
    assert not missing, f"missing Phase A routes: {missing}"

    # board P2-3 / P2-4 — internal-only routes must NOT be public.
    forbidden = {
        "/sessions/{session_id}/floorplan-candidates",
        "/sessions/{session_id}/chat/tool-calls",
        "/sessions/{session_id}/chat/tool-calls/{tool_call_id}",
    }
    leaked_internal = forbidden & paths
    assert (
        not leaked_internal
    ), f"internal-only Phase A routes leaked into public router: {leaked_internal}"

    forbidden_prefixes = ("/anonymous-sessions", "/anonymous", "/anon")
    leaked = {p for p in paths if p.startswith(forbidden_prefixes)}
    assert not leaked, f"legacy anonymous prefix leaked into routes: {leaked}"


def test_session_create_bearer_required_returns_supabase_error_code(monkeypatch):
    """legacy 흐름이 부활했다면 anonymous-id 헤더만으로 통과될 수 있다.

    Phase A skeleton 은 Supabase Bearer 토큰을 반드시 요구해야 한다.
    """

    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    client = TestClient(create_app())
    with client:
        response = client.post(
            "/sessions",
            headers={
                "x-jippin-anon-id": "00000000-0000-0000-0000-deadbeefdead",
            },
            json={},
        )
    assert response.status_code == 401
    # 익명 헤더가 인증으로 인식됐다면 다른 code 가 나왔을 것이다.
    assert response.json()["error"]["code"] == "SUPABASE_SESSION_BEARER_REQUIRED"


def test_session_routes_mounted_regardless_of_skeleton_flag(monkeypatch):
    """사전검토 세션/도면/채팅은 프로덕션 실기능이라 phase_a 플래그와 무관하게 항상
    등록된다(CMP-DIRECT). 웹의 /sessions 노출이 빌드타임에 결정되므로, 백엔드 라우트를
    플래그로 가리면 프로덕션에서 /sessions 가 404 가 되는 사고를 막는다.

    에이전트 라우트만 agent_enabled 로 게이트된다(아래 별도 테스트).
    """

    helpers.set_supabase_env(monkeypatch)
    monkeypatch.setenv("PHASE_A_SKELETON_ENABLED", "false")
    get_settings.cache_clear()

    app = create_app()
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    for mounted in (
        "/sessions",
        "/sessions/{session_id}",
        "/sessions/{session_id}/address",
        "/sessions/{session_id}/floorplan-uploads",
        "/sessions/{session_id}/floorplan-assets",
        "/sessions/{session_id}/report",
        "/sessions/{session_id}/chat/messages",
    ):
        assert mounted in paths, f"{mounted} must be mounted in production"

    # 인증 없는 호출은 404 가 아니라 401(라우트는 존재, Bearer 필요).
    client = TestClient(app)
    with client:
        response = client.post("/sessions", json={})
    assert response.status_code == 401


def test_agent_routes_absent_when_agent_disabled(monkeypatch):
    """에이전트 라우트는 agent_enabled 가 꺼진 환경에선 등록되지 않는다."""

    helpers.set_supabase_env(monkeypatch)
    monkeypatch.setenv("AGENT_ENABLED", "false")
    get_settings.cache_clear()

    app = create_app()
    paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
    assert "/sessions/{session_id}/agent/runs" not in paths
