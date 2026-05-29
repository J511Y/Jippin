from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from src.auth.providers import google, kakao, naver
from src.auth.state_store import (
    OAuthStateBackendUnavailable,
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


@pytest.mark.parametrize(
    ("provider", "expected_endpoint", "expected_client_id"),
    [
        ("kakao", kakao.AUTHORIZATION_ENDPOINT, "kakao-client"),
        ("naver", naver.AUTHORIZATION_ENDPOINT, "naver-client"),
        ("google", google.AUTHORIZATION_ENDPOINT, "google-client"),
    ],
)
def test_oauth_start_json_builds_provider_authorization_url(
    monkeypatch,
    oauth_env,
    provider,
    expected_endpoint,
    expected_client_id,
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

    assert response.status_code == 200
    authorization_url = response.json()["authorization_url"]
    parsed = urlparse(authorization_url)
    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == expected_endpoint
    query = parse_qs(parsed.query)
    assert query["client_id"] == [expected_client_id]
    assert query["response_type"] == ["code"]
    assert query["state"] == [store.put_calls[0][0]]
    assert query["nonce"] == [store.put_calls[0][1].nonce]
    assert len(store.put_calls[0][0]) >= 64
    assert store.put_calls[0][1].anonymous_user_id == anonymous_user_id
    assert store.put_calls[0][1].provider == provider
    assert store.put_calls[0][1].return_url == (
        "http://localhost:3000/auth/success?from=login"
    )


def test_oauth_start_defaults_to_redirect(monkeypatch, oauth_env):
    store = _FakeStateStore()
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)

    app = create_app()
    with TestClient(app, follow_redirects=False) as client:
        response = client.get("/auth/google/start")

    assert response.status_code == 302
    assert response.headers["location"].startswith(google.AUTHORIZATION_ENDPOINT)


def test_oauth_start_invalid_provider_returns_422(oauth_env):
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/auth/github/start", params={"mode": "json"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_oauth_start_rejects_unapproved_return_url(monkeypatch, oauth_env):
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

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "RETURN_URL_NOT_ALLOWED"
    assert store.put_calls == []


def test_oauth_start_ignores_invalid_anonymous_user_id(monkeypatch, oauth_env):
    store = _FakeStateStore()
    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: store)

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/auth/google/start",
            params={"mode": "json", "anonymous_user_id": "not-a-uuid"},
        )

    assert response.status_code == 200
    assert store.put_calls[0][1].anonymous_user_id is None


def test_oauth_start_redis_failure_returns_503(monkeypatch, oauth_env):
    class FailingStore:
        async def put(self, state: str, payload: OAuthStatePayload) -> bool:
            raise OAuthStateBackendUnavailable("OAuth state backend is unavailable.")

    monkeypatch.setattr(auth_router, "get_oauth_state_store", lambda: FailingStore())

    app = create_app()
    with TestClient(app) as client:
        response = client.get("/auth/google/start", params={"mode": "json"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "OAUTH_STATE_BACKEND_UNAVAILABLE"


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
