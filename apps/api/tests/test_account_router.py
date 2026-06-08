"""이메일 회원가입·문자인증·아이디/비번 찾기·회원탈퇴 라우터 테스트 (CMP-DIRECT).

Redis/Supabase/SOLAPI 외부 의존성은 monkeypatch 로 대체하고 라우터/검증/인증/에러 코드
경로를 검증한다.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from src.config import get_settings
from src.errors import ZippinException
from src.main import create_app
from src.services.supabase_admin import CreatedUser

from . import _supabase_helpers as helpers

NORMALIZED_PHONE = "010-1234-5678"


class FakeStore:
    """phone_verification 스토어 대역 — Redis 없이 동작한다."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.tokens: dict[str, str] = {"goodtok": NORMALIZED_PHONE}

    async def reserve_send(self, phone: str) -> str:
        self.sent.append(phone)
        return "123456"

    async def verify_code(self, phone: str, code: str) -> str:
        if code != "123456":
            raise ZippinException(
                "인증번호가 일치하지 않습니다.",
                code="PHONE_OTP_MISMATCH",
                http_status=400,
            )
        token = "issued-token"
        self.tokens[token] = phone
        return token

    async def consume_token(self, token: str) -> str | None:
        return self.tokens.pop(token, None)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    helpers.set_supabase_env(monkeypatch)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "svc-role-test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def store(monkeypatch) -> FakeStore:
    fake = FakeStore()
    monkeypatch.setattr(
        "src.routers.account.get_phone_verification_store", lambda: fake
    )
    return fake


def test_send_code_sends_sms_and_returns_ttl(monkeypatch, store) -> None:
    captured: dict[str, str] = {}

    async def fake_send(*, phone: str, code: str, **_) -> None:
        captured["phone"] = phone
        captured["code"] = code

    monkeypatch.setattr("src.services.sms.send_verification_sms", fake_send)

    client = TestClient(create_app())
    with client:
        resp = client.post("/auth/phone/send-code", json={"phone": "01012345678"})
    assert resp.status_code == 200
    assert resp.json()["expires_in_seconds"] == get_settings().phone_otp_ttl_seconds
    assert captured["phone"] == NORMALIZED_PHONE
    assert captured["code"] == "123456"


def test_verify_code_returns_token(store) -> None:
    client = TestClient(create_app())
    with client:
        resp = client.post(
            "/auth/phone/verify-code",
            json={"phone": "01012345678", "code": "123456"},
        )
    assert resp.status_code == 200
    assert resp.json()["phone_token"] == "issued-token"


def test_verify_code_rejects_wrong_code(store) -> None:
    client = TestClient(create_app())
    with client:
        resp = client.post(
            "/auth/phone/verify-code",
            json={"phone": "01012345678", "code": "000000"},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PHONE_OTP_MISMATCH"


def test_signup_creates_user_and_profile(monkeypatch, store) -> None:
    created_id = uuid.uuid4()
    calls: dict[str, object] = {}

    async def fake_create_user(**kwargs):
        calls["create"] = kwargs
        return CreatedUser(user_id=created_id)

    async def fake_profile(**kwargs):
        calls["profile"] = kwargs

    monkeypatch.setattr(
        "src.services.supabase_admin.create_email_user", fake_create_user
    )
    monkeypatch.setattr("src.routers.account.create_signup_profile", fake_profile)

    client = TestClient(create_app())
    with client:
        resp = client.post(
            "/auth/signup",
            json={
                "name": "홍길동",
                "email": "hong@example.com",
                "phone": "01012345678",
                "password": "abc123",
                "phone_token": "goodtok",
            },
        )
    assert resp.status_code == 201
    body = resp.json()
    assert body["user_id"] == str(created_id)
    assert body["email"] == "hong@example.com"
    assert calls["create"]["phone"] == NORMALIZED_PHONE
    assert calls["create"]["display_name"] == "홍길동"
    assert calls["profile"]["display_name"] == "홍길동"


def test_signup_rejects_expired_phone_token(store) -> None:
    client = TestClient(create_app())
    with client:
        resp = client.post(
            "/auth/signup",
            json={
                "name": "홍길동",
                "email": "hong@example.com",
                "phone": "01012345678",
                "password": "abc123",
                "phone_token": "missing",
            },
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "PHONE_TOKEN_INVALID"


def test_find_email_returns_masked(monkeypatch, store) -> None:
    async def fake_find(phone: str):
        assert phone == NORMALIZED_PHONE
        return [{"email": "hong@example.com", "created_at": "2026-06-01T00:00:00+00:00"}]

    monkeypatch.setattr("src.services.supabase_admin.find_emails_by_phone", fake_find)

    client = TestClient(create_app())
    with client:
        resp = client.post(
            "/auth/find-email",
            json={"phone": "01012345678", "phone_token": "goodtok"},
        )
    assert resp.status_code == 200
    emails = resp.json()["emails"]
    assert emails[0]["email_masked"] == "ho**@example.com"


def test_reset_password_updates_when_account_matches(monkeypatch, store) -> None:
    user_id = uuid.uuid4()
    updated: dict[str, object] = {}

    async def fake_find(email: str, phone: str):
        return user_id

    async def fake_update(**kwargs):
        updated.update(kwargs)

    monkeypatch.setattr(
        "src.services.supabase_admin.find_user_id_by_email_and_phone", fake_find
    )
    monkeypatch.setattr(
        "src.services.supabase_admin.update_user_password", fake_update
    )

    client = TestClient(create_app())
    with client:
        resp = client.post(
            "/auth/reset-password",
            json={
                "email": "hong@example.com",
                "phone": "01012345678",
                "phone_token": "goodtok",
                "new_password": "newpw123",
            },
        )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert updated["user_id"] == user_id
    assert updated["password"] == "newpw123"


def test_reset_password_404_when_no_match(monkeypatch, store) -> None:
    async def fake_find(email: str, phone: str):
        return None

    monkeypatch.setattr(
        "src.services.supabase_admin.find_user_id_by_email_and_phone", fake_find
    )

    client = TestClient(create_app())
    with client:
        resp = client.post(
            "/auth/reset-password",
            json={
                "email": "nobody@example.com",
                "phone": "01012345678",
                "phone_token": "goodtok",
                "new_password": "newpw123",
            },
        )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "ACCOUNT_NOT_FOUND"


def test_change_password_succeeds(monkeypatch) -> None:
    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    token, subject = helpers.mint_token(pem, "test-key-1", is_anonymous=False)

    updated: dict[str, object] = {}

    async def fake_email(user_id):
        return "hong@example.com"

    async def fake_verify(*, email, password):
        return password == "oldpw123"

    async def fake_update(**kwargs):
        updated.update(kwargs)

    monkeypatch.setattr("src.services.supabase_admin.get_email_by_user_id", fake_email)
    monkeypatch.setattr("src.services.supabase_admin.verify_password", fake_verify)
    monkeypatch.setattr("src.services.supabase_admin.update_user_password", fake_update)

    client = TestClient(create_app())
    with client:
        resp = client.post(
            "/auth/change-password",
            headers={"authorization": f"Bearer {token}"},
            json={"current_password": "oldpw123", "new_password": "newpw123"},
        )
    assert resp.status_code == 200
    assert updated["user_id"] == subject
    assert updated["password"] == "newpw123"


def test_change_password_rejects_wrong_current(monkeypatch) -> None:
    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    token, _subject = helpers.mint_token(pem, "test-key-1", is_anonymous=False)

    async def fake_email(user_id):
        return "hong@example.com"

    async def fake_verify(*, email, password):
        return False

    monkeypatch.setattr("src.services.supabase_admin.get_email_by_user_id", fake_email)
    monkeypatch.setattr("src.services.supabase_admin.verify_password", fake_verify)

    client = TestClient(create_app())
    with client:
        resp = client.post(
            "/auth/change-password",
            headers={"authorization": f"Bearer {token}"},
            json={"current_password": "wrong1", "new_password": "newpw123"},
        )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "CURRENT_PASSWORD_MISMATCH"


def test_delete_account_requires_permanent_user(monkeypatch) -> None:
    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    token, _subject = helpers.mint_token(pem, "test-key-1", is_anonymous=True)

    client = TestClient(create_app())
    with client:
        resp = client.delete(
            "/auth/account", headers={"authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "AUTH_ANONYMOUS_TOKEN_NOT_ALLOWED"


def test_delete_account_deletes_permanent_user(monkeypatch) -> None:
    pem, jwk = helpers.rsa_keypair()
    helpers.install_jwks(monkeypatch, {"keys": [jwk]})
    token, subject = helpers.mint_token(pem, "test-key-1", is_anonymous=False)

    deleted: dict[str, object] = {}

    async def fake_delete(**kwargs):
        deleted.update(kwargs)

    monkeypatch.setattr("src.services.supabase_admin.delete_user", fake_delete)

    client = TestClient(create_app())
    with client:
        resp = client.delete(
            "/auth/account", headers={"authorization": f"Bearer {token}"}
        )
    assert resp.status_code == 200
    assert deleted["user_id"] == subject
