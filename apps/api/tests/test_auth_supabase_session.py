"""Regression tests for POST /auth/supabase/session.

The bridge verifies a Supabase access token via JWKS, resolves ``sub`` directly
to ``public.users.id``, and mints the existing ``jippin_session`` cookie when an
active profile exists.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jose import jwt

from src.config import get_settings
from src.errors import ZippinException
from src.main import create_app
from src.services import supabase_session as bridge_service


_ISSUER = "https://example-project.supabase.co/auth/v1"
_AUDIENCE = "authenticated"
_JWKS_URL = "https://example-project.supabase.co/auth/v1/.well-known/jwks.json"
_KAKAO_APP_METADATA = {"provider": "kakao", "providers": ["kakao"]}


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def supabase_env(monkeypatch):
    values = {
        "AUTH_JWT_SECRET": "test-session-secret",
        "AUTH_COOKIE_SECURE": "false",
        "SUPABASE_JWT_ISSUER": _ISSUER,
        "SUPABASE_JWKS_URL": _JWKS_URL,
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()


def _b64url_uint(value: int) -> str:
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _rsa_keypair() -> tuple[str, dict[str, Any]]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")
    public_numbers = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": "test-key-1",
        "alg": "RS256",
        "use": "sig",
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }
    return pem, jwk


def _mint_token(
    private_pem: str,
    kid: str,
    *,
    sub: str | None = None,
    email: str | None = "user@example.com",
    issuer: str = _ISSUER,
    expires_in: timedelta = timedelta(hours=1),
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": sub or str(uuid.uuid4()),
        "aud": _AUDIENCE,
        "iss": issuer,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_in).timestamp()),
        "role": "authenticated",
    }
    if email is not None:
        claims["email"] = email
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(
        claims,
        private_pem,
        algorithm="RS256",
        headers={"kid": kid},
    )


def _install_jwks(monkeypatch, jwks: dict[str, Any]) -> None:
    async def fake_get_supabase_jwks(http_client, jwks_url):  # noqa: ARG001
        assert jwks_url == _JWKS_URL
        return jwks

    monkeypatch.setattr(bridge_service, "get_supabase_jwks", fake_get_supabase_jwks)


def _install_identity_lookup(monkeypatch, *, user_id: uuid.UUID | None) -> None:
    """Bypass the DB by patching the service-layer resolver directly."""

    async def fake_resolve(*, supabase_subject, email_claim):  # noqa: ARG001
        if user_id is not None:
            return bridge_service.SupabaseBridgeResult(user_id=user_id)
        raise ZippinException(
            "No active Jippin profile exists for this Supabase user.",
            code="AUTH_SIGNUP_REQUIRED",
            http_status=401,
        )

    monkeypatch.setattr(
        "src.routers.auth.resolve_jippin_user_for_supabase",
        fake_resolve,
    )

    async def fake_current_user_context(user_id: uuid.UUID):
        from src.services.auth import CurrentUserContext

        return CurrentUserContext(
            user_id=user_id,
            email="user@example.com",
            display_name=None,
            profile_image_url=None,
            role="user",
            providers=["kakao"],
            missing_required_terms=[],
        )

    monkeypatch.setattr(
        "src.routers.auth.get_current_user_context",
        fake_current_user_context,
    )

    # Kakao 브리지 경로는 record_kakao_sync_consent 로 동의를 기록하고 잔여 누락을
    # 반환한다. 기본 mock 은 누락 없음([]) — 내부 약관 화면으로 빠지지 않는다.
    async def fake_record_kakao_sync_consent(user_id: uuid.UUID):  # noqa: ARG001
        return []

    monkeypatch.setattr(
        "src.routers.auth.record_kakao_sync_consent",
        fake_record_kakao_sync_consent,
    )


def test_supabase_session_missing_authorization_header_returns_401(
    supabase_env, monkeypatch
):
    _, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})

    app = create_app()
    with TestClient(app) as client:
        response = client.post("/auth/supabase/session")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "SUPABASE_SESSION_BEARER_REQUIRED"


def test_supabase_session_valid_token_mints_cookie(supabase_env, monkeypatch):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    user_id = uuid.uuid4()
    _install_identity_lookup(monkeypatch, user_id=user_id)

    token = _mint_token(
        pem,
        jwk["kid"],
        extra_claims={"app_metadata": _KAKAO_APP_METADATA},
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"requested_provider": "kakao"},
        )

    assert response.status_code == 200
    assert response.json()["signup_complete"] is True
    set_cookie = response.headers["set-cookie"]
    assert "jippin_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()


def test_supabase_session_email_provider_mints_cookie(supabase_env, monkeypatch):
    """이메일/비밀번호 로그인(provider='email')도 jippin_session 을 발급해야 한다.

    회귀(P1): SupabaseSessionBridgeRequest.requested_provider Literal 에 'email' 이
    없으면 422 로 막혀 이메일 로그인이 전혀 동작하지 않는다.
    """
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    user_id = uuid.uuid4()
    _install_identity_lookup(monkeypatch, user_id=user_id)

    token = _mint_token(
        pem,
        jwk["kid"],
        extra_claims={"app_metadata": {"provider": "email", "providers": ["email"]}},
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"requested_provider": "email"},
        )

    assert response.status_code == 200
    assert response.json()["signup_complete"] is True
    assert "jippin_session=" in response.headers["set-cookie"]


def test_supabase_session_ignores_legacy_anonymous_id_after_completed_signin(
    supabase_env, monkeypatch
):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    user_id = uuid.uuid4()
    anonymous_user_id = uuid.uuid4()
    _install_identity_lookup(monkeypatch, user_id=user_id)
    token = _mint_token(
        pem,
        jwk["kid"],
        extra_claims={"app_metadata": _KAKAO_APP_METADATA},
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "anonymous_user_id": str(anonymous_user_id),
                "requested_provider": "kakao",
            },
        )

    assert response.status_code == 200
    assert response.json()["signup_complete"] is True


def test_supabase_session_rejects_anonymous_supabase_token(supabase_env, monkeypatch):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    _install_identity_lookup(monkeypatch, user_id=uuid.uuid4())
    token = _mint_token(
        pem,
        jwk["kid"],
        extra_claims={
            "is_anonymous": True,
            "app_metadata": {"provider": "anonymous", "providers": ["anonymous"]},
        },
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_ANONYMOUS_TOKEN_NOT_ALLOWED"


def test_supabase_session_accepts_converted_token_with_anonymous_metadata(
    supabase_env, monkeypatch
):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    user_id = uuid.uuid4()
    _install_identity_lookup(monkeypatch, user_id=user_id)
    token = _mint_token(
        pem,
        jwk["kid"],
        extra_claims={
            "is_anonymous": False,
            "app_metadata": {
                "provider": "anonymous",
                "providers": ["anonymous", "kakao"],
            },
        },
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"requested_provider": "kakao"},
        )

    assert response.status_code == 200
    assert response.json()["signup_complete"] is True


def test_supabase_session_expired_token_returns_401(supabase_env, monkeypatch):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})

    expired_token = _mint_token(
        pem,
        jwk["kid"],
        expires_in=timedelta(seconds=-30),
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {expired_token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_EXPIRED_TOKEN"


def test_supabase_session_requires_signed_provider_context(supabase_env, monkeypatch):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    _install_identity_lookup(monkeypatch, user_id=uuid.uuid4())
    token = _mint_token(
        pem,
        jwk["kid"],
        extra_claims={"app_metadata": _KAKAO_APP_METADATA},
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_PROVIDER_REQUIRED"


def test_supabase_session_rejects_non_enabled_provider_before_profile_upsert(
    supabase_env, monkeypatch
):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    token = _mint_token(
        pem,
        jwk["kid"],
        extra_claims={"app_metadata": {"provider": "google", "providers": ["google"]}},
    )
    called = False

    async def fake_resolve(*, supabase_subject, email_claim):  # noqa: ARG001
        nonlocal called
        called = True
        return bridge_service.SupabaseBridgeResult(user_id=uuid.uuid4())

    monkeypatch.setattr(
        "src.routers.auth.resolve_jippin_user_for_supabase",
        fake_resolve,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"requested_provider": "google"},
        )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "AUTH_PROVIDER_NOT_ALLOWED"
    assert called is False


def test_supabase_session_rejects_provider_mismatch_before_profile_upsert(
    supabase_env, monkeypatch
):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    token = _mint_token(
        pem,
        jwk["kid"],
        extra_claims={"app_metadata": {"provider": "email", "providers": ["email"]}},
    )
    called = False

    async def fake_resolve(*, supabase_subject, email_claim):  # noqa: ARG001
        nonlocal called
        called = True
        return bridge_service.SupabaseBridgeResult(user_id=uuid.uuid4())

    monkeypatch.setattr(
        "src.routers.auth.resolve_jippin_user_for_supabase",
        fake_resolve,
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"requested_provider": "kakao"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_PROVIDER_MISMATCH"
    assert called is False


def test_supabase_session_accepts_custom_kakao_provider_alias(
    supabase_env, monkeypatch
):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    user_id = uuid.uuid4()
    _install_identity_lookup(monkeypatch, user_id=user_id)
    token = _mint_token(
        pem,
        jwk["kid"],
        extra_claims={
            "app_metadata": {
                "provider": "anonymous",
                "providers": ["anonymous", "custom:kakao"],
            }
        },
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"requested_provider": "kakao"},
        )

    assert response.status_code == 200
    assert response.json()["signup_complete"] is True


def test_supabase_session_wrong_signature_returns_401(supabase_env, monkeypatch):
    _, advertised_jwk = _rsa_keypair()
    # JWKS advertises one key, but the token was signed by a foreign key.
    _install_jwks(monkeypatch, {"keys": [advertised_jwk]})

    foreign_pem, _foreign_jwk = _rsa_keypair()
    forged_token = _mint_token(foreign_pem, advertised_jwk["kid"])

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {forged_token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_INVALID_TOKEN"


def test_supabase_session_missing_mapping_returns_401(supabase_env, monkeypatch):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    _install_identity_lookup(monkeypatch, user_id=None)

    token = _mint_token(
        pem,
        jwk["kid"],
        extra_claims={"app_metadata": _KAKAO_APP_METADATA},
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"requested_provider": "kakao"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_SIGNUP_REQUIRED"


class _FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
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


class _FakeProfileConnection:
    def __init__(self, value):
        self.value = value
        self.statements: list[str] = []

    async def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        assert "auth_identities" not in sql
        assert "lower(users.email)" not in sql
        if sql.startswith("INSERT INTO users"):
            assert "ON CONFLICT (id) DO NOTHING" in sql
            return _FakeScalarResult(None)
        assert "FROM users" in sql
        assert "users.id =" in sql
        assert "users.status" in sql
        return _FakeScalarResult(self.value)


@pytest.mark.asyncio
async def test_supabase_identity_lookup_upserts_profile_from_subject_uuid(monkeypatch):
    user_id = uuid.uuid4()
    conn = _FakeProfileConnection(user_id)
    monkeypatch.setattr(bridge_service, "get_engine", lambda: _FakeEngine(conn))

    result = await bridge_service.resolve_jippin_user_for_supabase(
        supabase_subject=str(user_id),
        email_claim="USER@EXAMPLE.COM",
    )

    assert result.user_id == user_id
    assert len(conn.statements) == 2
    assert conn.statements[0].startswith("INSERT INTO users")
    assert conn.statements[1].startswith("SELECT users.id")


@pytest.mark.asyncio
async def test_supabase_identity_lookup_rejects_non_uuid_subject(monkeypatch):
    conn = _FakeProfileConnection(None)
    monkeypatch.setattr(bridge_service, "get_engine", lambda: _FakeEngine(conn))

    with pytest.raises(ZippinException) as exc_info:
        await bridge_service.resolve_jippin_user_for_supabase(
            supabase_subject="not-a-uuid",
            email_claim=None,
        )

    assert exc_info.value.code == "AUTH_INVALID_TOKEN"
    assert conn.statements == []


def test_supabase_session_kakao_records_sync_consent_and_skips_internal_terms(
    supabase_env, monkeypatch
):
    """Kakao Sync 로그인은 source='kakao_sync' 동의를 기록하고 /auth/terms 로 보내지 않는다.

    회귀: 브리지가 동의를 기록하지 않아 missing_required_terms 가 채워지면 Kakao
    사용자가 내부 약관 화면으로 잘못 유도된다 (AGENTS §4.7 #5 위반).
    """
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    user_id = uuid.uuid4()

    async def fake_resolve(*, supabase_subject, email_claim):  # noqa: ARG001
        return bridge_service.SupabaseBridgeResult(user_id=user_id)

    monkeypatch.setattr(
        "src.routers.auth.resolve_jippin_user_for_supabase", fake_resolve
    )

    recorded: dict[str, Any] = {}

    async def fake_record(consenting_user_id: uuid.UUID):
        recorded["user_id"] = consenting_user_id
        return []

    monkeypatch.setattr("src.routers.auth.record_kakao_sync_consent", fake_record)

    async def fail_context(_user_id: uuid.UUID):
        raise AssertionError("get_current_user_context must not run on the kakao path")

    monkeypatch.setattr("src.routers.auth.get_current_user_context", fail_context)

    token = _mint_token(
        pem, jwk["kid"], extra_claims={"app_metadata": _KAKAO_APP_METADATA}
    )
    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"requested_provider": "kakao"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["signup_complete"] is True
    assert body["missing_required_terms"] == []
    assert body["redirect_url"] is None
    assert recorded["user_id"] == user_id


class _FakeScalars:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _FakeKakaoConsentConn:
    def __init__(self, agreed_after_insert):
        self.agreed = agreed_after_insert
        self.statements: list[str] = []

    async def execute(self, statement, *args):  # noqa: ARG002
        sql = str(statement)
        self.statements.append(sql)
        if sql.startswith("INSERT INTO terms_consents"):
            return None
        return _FakeScalars(self.agreed)


@pytest.mark.asyncio
async def test_record_kakao_sync_consent_inserts_kakao_source_and_returns_missing(
    supabase_env, monkeypatch
):
    from src.services import auth as auth_service

    user_id = uuid.uuid4()
    # insert 직후 select 에서 모든 필수 태그가 동의됨으로 보이게 → missing 없음.
    conn = _FakeKakaoConsentConn(
        agreed_after_insert=["service_terms", "privacy_policy"]
    )
    monkeypatch.setattr(auth_service, "get_engine", lambda: _FakeEngine(conn))

    missing = await auth_service.record_kakao_sync_consent(user_id)

    assert missing == []
    insert_sql = next(
        s for s in conn.statements if s.startswith("INSERT INTO terms_consents")
    )
    assert "ON CONFLICT" in insert_sql
    assert "DO NOTHING" in insert_sql
