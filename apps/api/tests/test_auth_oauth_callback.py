from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.auth.providers import OAuthProvider, ProviderProfile
from src.auth.state_store import OAuthStatePayload
from src.config import get_settings
from src.errors import ZippinException
from src.main import create_app
from src.routers import auth as auth_router
from src.services import auth as auth_service


class _FakeStateStore:
    def __init__(self, payload: OAuthStatePayload | None) -> None:
        self.payload = payload
        self.consume_calls: list[str] = []

    async def consume(self, state: str) -> OAuthStatePayload | None:
        self.consume_calls.append(state)
        return self.payload


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def callback_env(monkeypatch):
    values = {
        "KAKAO_REST_API_KEY": "kakao-client",
        "KAKAO_CLIENT_SECRET": "kakao-secret",
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
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


@pytest.mark.parametrize("provider", ["kakao", "google", "naver"])
def test_oauth_callback_removed_returns_410_without_state_consume(
    monkeypatch,
    callback_env,
    provider,
):
    payload = OAuthStatePayload(
        anonymous_user_id=uuid.uuid4(),
        provider=provider,
        return_url="http://localhost:3000/auth/success?from=callback",
        nonce="nonce-value",
        created_at=datetime.now(UTC),
    )
    store = _FakeStateStore(payload)
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)

    app = create_app()
    with TestClient(app, follow_redirects=False) as client:
        response = client.get(
            f"/auth/callback/{provider}",
            params={"code": "oauth-code", "state": "state-value"},
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"
    assert store.consume_calls == []
    assert "set-cookie" not in response.headers


def test_oauth_callback_removed_before_state_lookup(monkeypatch, callback_env):
    store = _FakeStateStore(None)
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/auth/callback/google",
            params={"code": "oauth-code", "state": "missing-state"},
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"
    assert store.consume_calls == []


def test_oauth_callback_removed_before_provider_mismatch_check(monkeypatch, callback_env):
    store = _FakeStateStore(
        OAuthStatePayload(
            anonymous_user_id=None,
            provider="kakao",
            return_url=None,
            nonce="nonce-value",
            created_at=datetime.now(UTC),
        )
    )
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/auth/callback/google",
            params={"code": "oauth-code", "state": "wrong-provider"},
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"
    assert store.consume_calls == []


class _FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalar_one(self):
        return self.value


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
    def __init__(self, *, existing_user_id=None, inserted_user_id=None):
        self.existing_user_id = existing_user_id
        self.inserted_user_id = inserted_user_id or uuid.uuid4()
        self.statements: list[str] = []

    async def execute(self, statement):
        statement_text = str(statement)
        self.statements.append(statement_text)
        if statement_text.startswith("SELECT"):
            return _FakeResult(self.existing_user_id)
        if statement_text.startswith("INSERT") and "users" in statement_text:
            return _FakeResult(self.inserted_user_id)
        return _FakeResult(None)


@pytest.mark.asyncio
async def test_complete_oauth_login_is_removed_after_supabase_cutover(callback_env):
    with pytest.raises(ZippinException) as exc_info:
        await auth_service.complete_oauth_login(
            provider=OAuthProvider.KAKAO,
            profile=ProviderProfile(
                provider_subject="kakao-subject",
                email="shared@example.com",
                display_name="Kakao User",
                agreed_terms_tags=("service_terms", "privacy_policy"),
            ),
            anonymous_user_id=uuid.uuid4(),
        )

    assert exc_info.value.code == "AUTH_LEGACY_FLOW_REMOVED"
    assert exc_info.value.http_status == 410
