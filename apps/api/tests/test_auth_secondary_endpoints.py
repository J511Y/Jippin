from __future__ import annotations

import uuid
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from src.auth.providers import OAuthProvider, OAuthTokens, ProviderProfile, google
from src.auth.session import create_session_token
from src.auth.state_store import OAuthStatePayload
from src.config import get_settings
from src.errors import ZippinException
from src.main import create_app
from src.routers import auth as auth_router
from src.services import auth as auth_service
from src.services.auth import CurrentUserContext, TermsAcceptResult


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


def test_sso_link_start_requires_login(auth_env):
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/sso-accounts/google/link", params={"mode": "json"}
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_UNAUTHENTICATED"


def test_sso_link_start_stores_linking_user_id(monkeypatch, auth_env):
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

    assert response.status_code == 200
    authorization_url = response.json()["authorization_url"]
    parsed = urlparse(authorization_url)
    query = parse_qs(parsed.query)
    assert (
        f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        == google.AUTHORIZATION_ENDPOINT
    )
    assert query["state"] == [store.put_calls[0][0]]
    assert store.put_calls[0][1].linking_user_id == user_id
    assert store.put_calls[0][1].anonymous_user_id is None
    assert store.put_calls[0][1].return_url == (
        "http://localhost:3000/auth/success?linked=1"
    )


def test_link_callback_links_account_without_creating_user(monkeypatch, auth_env):
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
    provider_module = auth_router.PROVIDER_MODULES[OAuthProvider.GOOGLE]
    linked_calls = []

    async def fake_exchange_code(code, *, http_client, settings):
        assert code == "oauth-code"
        return OAuthTokens(access_token="provider-access-token")

    async def fake_fetch_userinfo(tokens, *, http_client, settings, **kwargs):
        assert kwargs == {"expected_nonce": "nonce-value"}
        return ProviderProfile(
            provider_subject="google-subject",
            email="google@example.com",
            display_name="Google User",
        )

    async def fake_link_oauth_account(*, linking_user_id, provider, profile):
        linked_calls.append((linking_user_id, provider, profile.provider_subject))

    async def fail_complete_oauth_login(**kwargs):
        raise AssertionError("link callback must not create or login a user")

    monkeypatch.setattr(provider_module, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(provider_module, "fetch_userinfo", fake_fetch_userinfo)
    monkeypatch.setattr(auth_router, "link_oauth_account", fake_link_oauth_account)
    monkeypatch.setattr(auth_router, "complete_oauth_login", fail_complete_oauth_login)

    app = create_app()
    with TestClient(app, follow_redirects=False) as client:
        response = client.get(
            "/auth/callback/google",
            params={"code": "oauth-code", "state": "state-value"},
        )

    assert response.status_code == 302
    assert response.headers["location"] == "http://localhost:3000/auth/success?linked=1"
    assert linked_calls == [(user_id, OAuthProvider.GOOGLE, "google-subject")]


def test_link_callback_returns_409_for_other_user_link(monkeypatch, auth_env):
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
    provider_module = auth_router.PROVIDER_MODULES[OAuthProvider.GOOGLE]

    async def fake_exchange_code(code, *, http_client, settings):
        return OAuthTokens(access_token="provider-access-token")

    async def fake_fetch_userinfo(tokens, *, http_client, settings, **kwargs):
        return ProviderProfile(provider_subject="google-subject")

    async def fake_link_oauth_account(*, linking_user_id, provider, profile):
        raise ZippinException(
            "This SSO account is already linked to another user.",
            code="SSO_ALREADY_LINKED_TO_OTHER_USER",
            http_status=409,
        )

    monkeypatch.setattr(provider_module, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(provider_module, "fetch_userinfo", fake_fetch_userinfo)
    monkeypatch.setattr(auth_router, "link_oauth_account", fake_link_oauth_account)

    app = create_app()
    with TestClient(app) as client:
        response = client.get(
            "/auth/callback/google",
            params={"code": "oauth-code", "state": "state-value"},
        )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SSO_ALREADY_LINKED_TO_OTHER_USER"


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


def test_terms_accept_completes_signup_and_claims_pending_anonymous_user(
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
            claimed_anonymous_user=True,
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
        "claimed_anonymous_user": True,
    }
    assert calls == [
        (
            user_id,
            {"service_terms", "privacy_policy"},
            anonymous_user_id,
        )
    ]


def test_terms_accept_uses_body_pending_anonymous_user_id(monkeypatch, auth_env):
    user_id = uuid.uuid4()
    anonymous_user_id = uuid.uuid4()
    calls = []

    async def fake_accept_terms(*, user_id, agreed_term_ids, pending_anonymous_user_id):
        calls.append((user_id, agreed_term_ids, pending_anonymous_user_id))
        return TermsAcceptResult(
            signup_complete=True,
            missing_required_terms=[],
            claimed_anonymous_user=True,
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
                ],
                "pending_anonymous_user_id": str(anonymous_user_id),
            },
        )

    assert response.status_code == 200
    assert calls == [
        (
            user_id,
            {"service_terms", "privacy_policy"},
            anonymous_user_id,
        )
    ]


def test_terms_accept_rejects_body_pending_anonymous_mismatch(monkeypatch, auth_env):
    user_id = uuid.uuid4()

    async def fake_accept_terms(*, user_id, agreed_term_ids, pending_anonymous_user_id):
        raise AssertionError("accept_required_terms must not be called")

    monkeypatch.setattr(auth_router, "accept_required_terms", fake_accept_terms)

    app = create_app()
    with TestClient(app) as client:
        client.cookies.set("jippin_session", _session_cookie(user_id))
        response = client.post(
            "/auth/terms/accept",
            json={
                "consents": [
                    {"term_id": "service_terms", "agreed": True},
                    {"term_id": "privacy_policy", "agreed": True},
                ],
                "pending_anonymous_user_id": str(uuid.uuid4()),
            },
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PENDING_ANONYMOUS_MISMATCH"


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
        if statement_text.startswith("UPDATE anonymous_users"):
            return _FakeResult(self.anonymous_user_id)
        return _FakeResult()


@pytest.mark.asyncio
async def test_accept_required_terms_upserts_rows_and_claims_anonymous(
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
        claimed_anonymous_user=True,
    )
    assert "INSERT INTO terms_consents" in combined_sql
    assert "(user_id, term_id, version, source" in combined_sql
    assert "ON CONFLICT (user_id, term_id, version) DO UPDATE" in combined_sql
    assert "UPDATE anonymous_users" in combined_sql
