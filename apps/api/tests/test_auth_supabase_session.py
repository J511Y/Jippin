"""Regression tests for POST /auth/supabase/session (CMP-595).

The bridge verifies a Supabase access token via JWKS, looks up the jippin
``auth_identities`` mapping, and mints the existing ``jippin_session`` cookie
when the mapping exists. We mock the JWKS fetcher and the DB lookup so the
test suite stays hermetic — sealing the four documented regression cases
(valid / expired / wrong-signature / missing-mapping).
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
    sub: str = "supabase-user-uuid",
    email: str | None = "user@example.com",
    issuer: str = _ISSUER,
    expires_in: timedelta = timedelta(hours=1),
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(UTC)
    claims = {
        "sub": sub,
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


def _install_identity_lookup(
    monkeypatch, *, user_id: uuid.UUID | None, email_user_exists: bool = False
) -> None:
    """Bypass the DB by patching the service-layer resolver directly."""

    async def fake_resolve(*, supabase_subject, email_claim):  # noqa: ARG001
        if user_id is not None:
            return bridge_service.SupabaseBridgeResult(user_id=user_id)
        from src.errors import ZippinException

        if email_user_exists:
            raise ZippinException(
                "Supabase identity is not linked to a jippin account.",
                code="AUTH_IDENTITY_NOT_LINKED",
                http_status=401,
            )
        raise ZippinException(
            "No jippin account exists for this Supabase identity. Sign up first.",
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
            providers=["google"],
            missing_required_terms=[],
        )

    monkeypatch.setattr(
        "src.routers.auth.get_current_user_context",
        fake_current_user_context,
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

    token = _mint_token(pem, jwk["kid"])

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["signup_complete"] is True
    set_cookie = response.headers["set-cookie"]
    assert "jippin_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie.lower() or "samesite=lax" in set_cookie.lower()


def test_supabase_session_claims_anonymous_work_after_completed_signin(
    supabase_env, monkeypatch
):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    user_id = uuid.uuid4()
    anonymous_user_id = uuid.uuid4()
    claim_calls = []
    _install_identity_lookup(monkeypatch, user_id=user_id)

    async def fake_claim_anonymous_user(*, user_id, anonymous_user_id):
        claim_calls.append((user_id, anonymous_user_id))

    monkeypatch.setattr(
        "src.routers.auth.claim_anonymous_user",
        fake_claim_anonymous_user,
    )
    token = _mint_token(pem, jwk["kid"])

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
            json={"anonymous_user_id": str(anonymous_user_id)},
        )

    assert response.status_code == 200
    assert response.json()["signup_complete"] is True
    assert claim_calls == [(user_id, anonymous_user_id)]


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
                "providers": ["anonymous", "google"],
            },
        },
    )

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
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
    _install_identity_lookup(monkeypatch, user_id=None, email_user_exists=False)

    token = _mint_token(pem, jwk["kid"])

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_SIGNUP_REQUIRED"


def test_supabase_session_unlinked_existing_user_returns_identity_not_linked(
    supabase_env, monkeypatch
):
    pem, jwk = _rsa_keypair()
    _install_jwks(monkeypatch, {"keys": [jwk]})
    _install_identity_lookup(monkeypatch, user_id=None, email_user_exists=True)

    token = _mint_token(pem, jwk["kid"])

    app = create_app()
    with TestClient(app) as client:
        response = client.post(
            "/auth/supabase/session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "AUTH_IDENTITY_NOT_LINKED"


class _FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value


class _FakeConnect:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def connect(self):
        return _FakeConnect(self.conn)


class _FakeDuplicateEmailConnection:
    def __init__(self):
        self.statements: list[str] = []

    async def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if "FROM auth_identities" in sql:
            return _FakeScalarResult(None)
        if "FROM users" in sql:
            assert "lower(users.email)" in sql
            assert "LIMIT" in sql
            return _FakeScalarResult(uuid.uuid4())
        return _FakeScalarResult(None)


@pytest.mark.asyncio
async def test_supabase_identity_lookup_handles_duplicate_casefolded_emails(
    monkeypatch,
):
    conn = _FakeDuplicateEmailConnection()
    monkeypatch.setattr(bridge_service, "get_engine", lambda: _FakeEngine(conn))

    with pytest.raises(ZippinException) as exc_info:
        await bridge_service.resolve_jippin_user_for_supabase(
            supabase_subject="supabase-subject",
            email_claim="USER@EXAMPLE.COM",
        )

    assert exc_info.value.code == "AUTH_IDENTITY_NOT_LINKED"
