from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.auth.session import create_session_token
from src.auth.state_store import OAuthStatePayload
from src.config import get_settings
from src.errors import ZippinException
from src.main import create_app
from src.routers import auth as auth_router
from src.services import auth as auth_service
from src.services.auth import (
    CurrentUserContext,
    SupabaseSessionBridgeResult,
    TermsAcceptResult,
)


class _FakeStateStore:
    def __init__(self, payload: OAuthStatePayload | None = None) -> None:
        self.payload = payload
        self.put_calls: list[tuple[str, OAuthStatePayload]] = []
        self.consume_calls: list[str] = []

    async def put(self, state: str, payload: OAuthStatePayload) -> bool:
        self.put_calls.append((state, payload))
        return True

    async def consume(self, state: str) -> OAuthStatePayload | None:
        self.consume_calls.append(state)
        return self.payload


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def auth_env(monkeypatch):
    values = {
        "KAKAO_REST_API_KEY": "kakao-client",
        "KAKAO_REDIRECT_URI": "http://localhost:8000/auth/callback/kakao",
        "GOOGLE_OAUTH_CLIENT_ID": "google-client",
        "GOOGLE_OAUTH_CLIENT_SECRET": "google-secret",
        "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/auth/callback/google",
        "NAVER_OAUTH_CLIENT_ID": "naver-client",
        "NAVER_OAUTH_CLIENT_SECRET": "naver-secret",
        "NAVER_OAUTH_REDIRECT_URI": "http://localhost:8000/auth/callback/naver",
        "FRONTEND_AUTH_SUCCESS_URL": "http://localhost:3000/auth/success",
        "FRONTEND_AUTH_TERMS_URL": "http://localhost:3000/auth/terms",
        "AUTH_JWT_SECRET": "test-session-secret",
        "AUTH_COOKIE_SECURE": "false",
        "SUPABASE_JWT_SECRET": "test-supabase-secret",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def _session_cookie(
    user_id: uuid.UUID, *, pending_anon: uuid.UUID | None = None
) -> str:
    return create_session_token(
        user_id,
        get_settings(),
        pending_anonymous_user_id=pending_anon,
    )


def test_auth_me_without_cookie_returns_401(auth_env):
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_UNAUTHENTICATED"


def test_auth_me_with_valid_cookie_returns_user_context(monkeypatch, auth_env):
    user_id = uuid.uuid4()

    async def fake_get_context(seen_user_id: uuid.UUID) -> CurrentUserContext:
        assert seen_user_id == user_id
        return CurrentUserContext(
            user_id=user_id,
            email="user@example.com",
            display_name="Jippin User",
            profile_image_url="https://cdn.example/profile.png",
            role="user",
            providers=["kakao"],
            missing_required_terms=[],
        )

    monkeypatch.setattr(auth_router, "get_current_user_context", fake_get_context)

    app = create_app()
    with TestClient(app) as client:
        client.cookies.set("jippin_session", _session_cookie(user_id))
        response = client.get("/auth/me")

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "id": str(user_id),
            "email": "user@example.com",
            "display_name": "Jippin User",
            "profile_image_url": "https://cdn.example/profile.png",
            "role": "user",
        },
        "providers": ["kakao"],
        "signup_complete": True,
        "missing_required_terms": [],
    }


def test_logout_expires_session_cookie(monkeypatch, auth_env):
    user_id = uuid.uuid4()

    async def fake_get_context(seen_user_id: uuid.UUID) -> CurrentUserContext:
        return CurrentUserContext(
            user_id=seen_user_id,
            email=None,
            display_name=None,
            profile_image_url=None,
            role="user",
            providers=[],
            missing_required_terms=[],
        )

    monkeypatch.setattr(auth_router, "get_current_user_context", fake_get_context)

    app = create_app()
    with TestClient(app) as client:
        client.cookies.set(
            "jippin_session",
            _session_cookie(user_id),
            domain="testserver.local",
        )
        assert client.get("/auth/me").status_code == 200

        logout_response = client.post("/auth/logout")
        me_response = client.get("/auth/me")

    assert logout_response.status_code == 200
    assert logout_response.json() == {"ok": True}
    assert "jippin_session=" in logout_response.headers["set-cookie"]
    assert "Max-Age=0" in logout_response.headers["set-cookie"]
    assert me_response.status_code == 401


def test_supabase_session_bridge_requires_bearer_token(auth_env):
    app = create_app()
    with TestClient(app) as client:
        response = client.post("/auth/supabase/session", json={})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SUPABASE_SESSION_BEARER_REQUIRED"


def test_supabase_session_bridge_sets_backend_cookie_and_forwards_anonymous_id(
    monkeypatch, auth_env
):
    user_id = uuid.uuid4()
    anonymous_user_id = uuid.uuid4()
    calls = []

    async def fake_complete_supabase_session(
        *, access_token, anonymous_user_id, requested_provider
    ):
        calls.append((access_token, anonymous_user_id, requested_provider))
        return SupabaseSessionBridgeResult(
            user_id=user_id,
            pending_anonymous_user_id=None,
            missing_required_terms=[],
        )

    monkeypatch.setattr(
        auth_router, "complete_supabase_session", fake_complete_supabase_session
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": "Bearer supabase-access-token"},
            json={
                "anonymous_user_id": str(anonymous_user_id),
                "requested_provider": "kakao",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "signup_complete": True,
        "missing_required_terms": [],
        "redirect_url": None,
    }
    assert calls == [("supabase-access-token", str(anonymous_user_id), "kakao")]
    assert "jippin_session=" in response.headers["set-cookie"]


def test_supabase_session_bridge_rejects_invalid_anonymous_user_id(auth_env):
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": "Bearer supabase-access-token"},
            json={"anonymous_user_id": "x" * 4096},
        )

    assert response.status_code == 422


def test_supabase_session_bridge_routes_incomplete_signup_to_terms(
    monkeypatch, auth_env
):
    user_id = uuid.uuid4()
    anonymous_user_id = uuid.uuid4()

    async def fake_complete_supabase_session(
        *, access_token, anonymous_user_id, requested_provider
    ):
        assert requested_provider == "kakao"
        return SupabaseSessionBridgeResult(
            user_id=user_id,
            pending_anonymous_user_id=uuid.UUID(anonymous_user_id),
            missing_required_terms=["service_terms", "privacy_policy"],
        )

    monkeypatch.setattr(
        auth_router, "complete_supabase_session", fake_complete_supabase_session
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": "Bearer supabase-access-token"},
            json={
                "anonymous_user_id": str(anonymous_user_id),
                "requested_provider": "kakao",
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "signup_complete": False,
        "missing_required_terms": ["service_terms", "privacy_policy"],
        "redirect_url": "http://localhost:3000/auth/terms",
    }
    cookie = response.headers["set-cookie"]
    assert "jippin_session=" in cookie
    token = cookie.split("jippin_session=", 1)[1].split(";", 1)[0]
    claims = auth_router.read_session_claims(
        type("Request", (), {"cookies": {"jippin_session": token}})()
    )
    assert claims.pending_anonymous_user_id == anonymous_user_id


def test_supabase_account_link_requires_existing_backend_session(auth_env):
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/link",
            headers={"Authorization": "Bearer supabase-access-token"},
            json={"requested_provider": "google"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_UNAUTHENTICATED"


def test_supabase_account_link_uses_current_session_user(monkeypatch, auth_env):
    user_id = uuid.uuid4()
    calls = []

    async def fake_link_supabase_account(
        *, access_token, linking_user_id, requested_provider
    ):
        calls.append((access_token, linking_user_id, requested_provider))

    monkeypatch.setattr(
        auth_router, "link_supabase_account", fake_link_supabase_account
    )

    app = create_app()
    with TestClient(app) as client:
        client.cookies.set("jippin_session", _session_cookie(user_id))
        response = client.post(
            "/auth/supabase/link",
            headers={"Authorization": "Bearer supabase-access-token"},
            json={"requested_provider": "kakao"},
        )

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert calls == [("supabase-access-token", user_id, "kakao")]


@pytest.mark.asyncio
async def test_service_level_supabase_session_bridge_is_not_execution_path(auth_env):
    with pytest.raises(ZippinException) as exc_info:
        await auth_service.complete_supabase_session(
            access_token="supabase-access-token",
            anonymous_user_id=str(uuid.uuid4()),
            requested_provider="google",
        )

    assert exc_info.value.code == "AUTH_SESSION_INTERNAL_ERROR"


def test_sso_link_start_removed_before_session_lookup(auth_env):
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/sso-accounts/google/link", params={"mode": "json"}
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"


def test_sso_link_start_removed_without_state_write(monkeypatch, auth_env):
    user_id = uuid.uuid4()
    store = _FakeStateStore()
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)

    app = create_app()
    with TestClient(app) as client:
        client.cookies.set("jippin_session", _session_cookie(user_id))
        response = client.post(
            "/auth/sso-accounts/google/link",
            params={
                "mode": "json",
                "return_url": "http://localhost:3000/auth/success?linked=1",
            },
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"
    assert store.put_calls == []


def test_link_callback_route_removed_without_provider_exchange(monkeypatch, auth_env):
    user_id = uuid.uuid4()
    payload = OAuthStatePayload(
        anonymous_user_id=None,
        provider="google",
        return_url="http://localhost:3000/auth/success?linked=1",
        nonce="nonce-value",
        created_at=datetime.now(UTC),
        linking_user_id=user_id,
    )
    store = _FakeStateStore(payload)
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)

    async def fake_link_oauth_account(*, linking_user_id, provider, profile):
        raise AssertionError("legacy link callback must not call link_oauth_account")

    async def fail_complete_oauth_login(**kwargs):
        raise AssertionError("link callback must not create or login a user")

    monkeypatch.setattr(auth_router, "link_oauth_account", fake_link_oauth_account)
    monkeypatch.setattr(auth_router, "complete_oauth_login", fail_complete_oauth_login)

    app = create_app()
    with TestClient(app, follow_redirects=False) as client:
        response = client.get(
            "/auth/callback/google",
            params={"code": "oauth-code", "state": "state-value"},
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"
    assert store.consume_calls == []


def test_link_callback_removed_before_link_conflict(monkeypatch, auth_env):
    payload = OAuthStatePayload(
        anonymous_user_id=None,
        provider="google",
        return_url=None,
        nonce="nonce-value",
        created_at=datetime.now(UTC),
        linking_user_id=uuid.uuid4(),
    )
    monkeypatch.setattr(
        auth_router, "get_oauth_state_store", lambda: _FakeStateStore(payload)
    )

    async def fake_link_oauth_account(*, linking_user_id, provider, profile):
        raise ZippinException(
            "This SSO account is already linked to another user.",
            code="SSO_ALREADY_LINKED_TO_OTHER_USER",
            http_status=409,
        )

    monkeypatch.setattr(auth_router, "link_oauth_account", fake_link_oauth_account)

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/auth/callback/google",
            params={"code": "oauth-code", "state": "state-value"},
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"


def test_terms_accept_requires_login(auth_env):
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/terms/accept",
            json={"consents": [{"term_id": "service_terms", "agreed": True}]},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_UNAUTHENTICATED"


def test_terms_accept_returns_422_with_missing_terms(monkeypatch, auth_env):
    user_id = uuid.uuid4()

    async def fake_accept_terms(*, user_id, agreed_term_ids, pending_anonymous_user_id):
        raise ZippinException(
            "Required terms are missing.",
            code="TERMS_REQUIRED_MISSING",
            http_status=422,
            details={"missing_required_terms": ["privacy_policy"]},
        )

    monkeypatch.setattr(auth_router, "accept_required_terms", fake_accept_terms)

    app = create_app()
    with TestClient(app) as client:
        client.cookies.set("jippin_session", _session_cookie(user_id))
        response = client.post(
            "/auth/terms/accept",
            json={"consents": [{"term_id": "service_terms", "agreed": True}]},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "TERMS_REQUIRED_MISSING"
    assert response.json()["detail"] == {"missing_required_terms": ["privacy_policy"]}


def test_terms_accept_completes_signup_without_legacy_anonymous_claim(
    monkeypatch,
    auth_env,
):
    user_id = uuid.uuid4()
    anonymous_user_id = uuid.uuid4()
    calls = []

    async def fake_accept_terms(*, user_id, agreed_term_ids, pending_anonymous_user_id):
        calls.append((user_id, agreed_term_ids, pending_anonymous_user_id))
        return TermsAcceptResult(
            signup_complete=True,
            missing_required_terms=[],
            claimed_anonymous_user=False,
        )

    monkeypatch.setattr(auth_router, "accept_required_terms", fake_accept_terms)

    app = create_app()
    with TestClient(app) as client:
        client.cookies.set(
            "jippin_session",
            _session_cookie(user_id, pending_anon=anonymous_user_id),
        )
        response = client.post(
            "/auth/terms/accept",
            json={
                "consents": [
                    {"term_id": "service_terms", "agreed": True},
                    {"term_id": "privacy_policy", "agreed": True},
                    {"term_id": "marketing", "agreed": False},
                ]
            },
        )

    assert response.status_code == 200
    assert response.json() == {
        "signup_complete": True,
        "missing_required_terms": [],
        "claimed_anonymous_user": False,
    }
    assert calls == [
        (
            user_id,
            {"service_terms", "privacy_policy"},
            anonymous_user_id,
        )
    ]


class _FakeResult:
    def __init__(self, value=None, values=None):
        self.value = value
        self.values = values or []

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return self

    def all(self):
        return self.values


class _FakeBegin:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def begin(self):
        return _FakeBegin(self.conn)


class _FakeConnection:
    def __init__(self, user_id: uuid.UUID, anonymous_user_id: uuid.UUID):
        self.user_id = user_id
        self.anonymous_user_id = anonymous_user_id
        self.statements: list[str] = []

    async def execute(self, statement):
        statement_text = str(statement)
        self.statements.append(statement_text)
        if statement_text.startswith("SELECT users.id"):
            return _FakeResult(self.user_id)
        if statement_text.startswith("SELECT terms_consents.term_id"):
            return _FakeResult(values=["service_terms", "privacy_policy"])
        return _FakeResult()


@pytest.mark.asyncio
async def test_accept_required_terms_upserts_rows_without_legacy_anonymous_claim(
    monkeypatch, auth_env
):
    user_id = uuid.uuid4()
    anonymous_user_id = uuid.uuid4()
    conn = _FakeConnection(user_id, anonymous_user_id)
    monkeypatch.setattr(auth_service, "get_engine", lambda: _FakeEngine(conn))

    result = await auth_service.accept_required_terms(
        user_id=user_id,
        agreed_term_ids={"service_terms", "privacy_policy"},
        pending_anonymous_user_id=anonymous_user_id,
    )

    combined_sql = "\n".join(conn.statements)
    assert result == TermsAcceptResult(
        signup_complete=True,
        missing_required_terms=[],
        claimed_anonymous_user=False,
    )
    assert "INSERT INTO terms_consents" in combined_sql
    assert "(user_id, term_id, version, source" in combined_sql
    assert "ON CONFLICT (user_id, term_id, version) DO UPDATE" in combined_sql
    assert "UPDATE anonymous_users" not in combined_sql


def test_kakao_sync_audit_stub_accepts_payload_with_bearer_header(auth_env):
    """CMP-581 round-13 — POST /auth/terms/kakao-sync stub returns 202 + stubbed flag."""
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/terms/kakao-sync",
            headers={"Authorization": "Bearer fake-supabase-access-token"},
            json={
                "supabase_user_id": "supabase-uuid-1",
                "linked_provider": "kakao",
                "provider_access_token": "kakao-access-token",
                "provider_refresh_token": None,
            },
        )

    assert response.status_code == 202
    body = response.json()
    assert body["accepted"] is True
    assert body["stubbed"] is True
    assert "Backend/Auth" in body["detail"]


def test_kakao_sync_audit_stub_rejects_missing_bearer_header(auth_env):
    """Bearer 헤더 부재 → 401. 실 JWT 검증 전 단계 fence."""
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/terms/kakao-sync",
            json={
                "supabase_user_id": "supabase-uuid-1",
                "linked_provider": "kakao",
                "provider_access_token": "kakao-access-token",
                "provider_refresh_token": None,
            },
        )

    assert response.status_code == 401
    # round-16 항목 3 — 기존 API contract 의 uppercase stable code 정합.
    assert response.json()["error"]["code"] == "AUTH_UNAUTHENTICATED"


def test_kakao_sync_audit_stub_rejects_empty_bearer_value(auth_env):
    """round-17 항목 2 — `Bearer ` prefix 만 보고 빈 token 을 허용하면 안 됨."""
    app = create_app()
    with TestClient(app) as client:
        for header_value in ("Bearer ", "Bearer   ", "bearer "):
            response = client.post(
                "/auth/terms/kakao-sync",
                headers={"Authorization": header_value},
                json={
                    "supabase_user_id": "u",
                    "linked_provider": "kakao",
                    "provider_access_token": None,
                    "provider_refresh_token": None,
                },
            )
            assert response.status_code == 401, header_value
            assert response.json()["error"]["code"] == "AUTH_UNAUTHENTICATED"


def test_kakao_sync_audit_stub_rejects_non_kakao_provider(auth_env):
    """schema fence — linked_provider 는 'kakao' literal 만 허용 (round-12 normalize 와 정합)."""
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/terms/kakao-sync",
            headers={"Authorization": "Bearer fake-token"},
            json={
                "supabase_user_id": "u",
                "linked_provider": "google",
                "provider_access_token": None,
                "provider_refresh_token": None,
            },
        )

    # FastAPI Pydantic validation → 422 Unprocessable Entity.
    assert response.status_code == 422
