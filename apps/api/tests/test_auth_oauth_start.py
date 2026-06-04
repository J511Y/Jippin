from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from src.auth.state_store import (
    OAuthStatePayload,
    OAuthStateStore,
)
from src.config import get_settings
from src.main import create_app
from src.routers import auth as auth_router


class _FakeStateStore:
    def __init__(self) -> None:
        self.put_calls: list[tuple[str, OAuthStatePayload]] = []

    async def put(self, state: str, payload: OAuthStatePayload) -> bool:
        self.put_calls.append((state, payload))
        return True


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def oauth_env(monkeypatch):
    values = {
        "KAKAO_REST_API_KEY": "kakao-client",
        "KAKAO_REDIRECT_URI": "http://localhost:8000/auth/callback/kakao",
        "GOOGLE_OAUTH_CLIENT_ID": "google-client",
        "GOOGLE_OAUTH_REDIRECT_URI": "http://localhost:8000/auth/callback/google",
        "NAVER_OAUTH_CLIENT_ID": "naver-client",
        "NAVER_OAUTH_REDIRECT_URI": "http://localhost:8000/auth/callback/naver",
        "FRONTEND_AUTH_SUCCESS_URL": "http://localhost:3000/auth/success",
        "FRONTEND_AUTH_FAILURE_URL": "http://localhost:3000/auth/failure",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


@pytest.mark.parametrize("provider", ["kakao", "naver", "google"])
def test_oauth_start_removed_returns_410_without_state_write(
    monkeypatch, oauth_env, provider
):
    store = _FakeStateStore()
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)
    anonymous_user_id = uuid.uuid4()

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            f"/auth/{provider}/start",
            params={
                "mode": "json",
                "anonymous_user_id": str(anonymous_user_id),
                "return_url": "http://localhost:3000/auth/success?from=login",
            },
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"
    assert store.put_calls == []


def test_oauth_start_removed_before_redirect_mode_state_write(monkeypatch, oauth_env):
    store = _FakeStateStore()
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)

    app = create_app()
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/auth/google/start")

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"
    assert "location" not in response.headers
    assert store.put_calls == []


def test_oauth_start_invalid_provider_returns_422(oauth_env):
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/auth/github/start", params={"mode": "json"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_oauth_start_removed_before_return_url_validation(monkeypatch, oauth_env):
    store = _FakeStateStore()
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/auth/google/start",
            params={
                "mode": "json",
                "return_url": "https://evil.example/auth/success",
            },
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"
    assert store.put_calls == []


def test_oauth_start_removed_before_anonymous_id_parsing(monkeypatch, oauth_env):
    store = _FakeStateStore()
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/auth/google/start",
            params={"mode": "json", "anonymous_user_id": "not-a-uuid"},
        )

    assert response.status_code == 410
    assert response.json()["error"]["code"] == "AUTH_LEGACY_FLOW_REMOVED"
    assert store.put_calls == []


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls: list[dict[str, object]] = []

    async def set(self, key: str, value: str, *, ex: int, nx: bool):
        self.set_calls.append({"key": key, "ex": ex, "nx": nx})
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    async def execute_command(self, command: str, key: str):
        assert command == "GETDEL"
        return self.values.pop(key, None)

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_state_store_put_consume_is_single_use():
    redis = _FakeRedis()
    store = OAuthStateStore(redis, ttl_seconds=600)  # type: ignore[arg-type]
    anonymous_user_id = uuid.uuid4()
    payload = OAuthStatePayload(
        anonymous_user_id=anonymous_user_id,
        provider="google",
        return_url="http://localhost:3000/auth/success",
        nonce="nonce-value",
        created_at=datetime.now(UTC),
    )

    stored = await store.put("state-value", payload)
    consumed = await store.consume("state-value")
    consumed_again = await store.consume("state-value")

    assert stored is True
    assert consumed == payload
    assert consumed_again is None
    assert redis.set_calls == [
        {"key": "auth:oauth_state:state-value", "ex": 600, "nx": True}
    ]
