"""이메일 회원가입·인증 Pydantic 계약 검증 (CMP-DIRECT)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.account import (
    SignupRequest,
    validate_email_format,
    validate_password_policy,
)


@pytest.mark.parametrize("pw", ["abc123", "Password1", "a1b2c3", "x" * 70 + "a1"])
def test_password_policy_accepts_valid(pw: str) -> None:
    assert validate_password_policy(pw) == pw


@pytest.mark.parametrize(
    "pw",
    [
        "abcde",  # 6자 미만
        "123456",  # 영문 없음
        "abcdef",  # 숫자 없음
        "ab1",  # 6자 미만
        "a" * 72 + "1",  # 72자 초과(73자)
    ],
)
def test_password_policy_rejects_invalid(pw: str) -> None:
    with pytest.raises(ValueError):
        validate_password_policy(pw)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("USER@Example.com", "user@example.com"),
        ("  a@b.co  ", "a@b.co"),
    ],
)
def test_email_format_normalizes(raw: str, expected: str) -> None:
    assert validate_email_format(raw) == expected


@pytest.mark.parametrize("raw", ["no-at", "a@b", "@b.co", "a@.co", "a b@c.co"])
def test_email_format_rejects_invalid(raw: str) -> None:
    with pytest.raises(ValueError):
        validate_email_format(raw)


def test_signup_request_normalizes_phone_and_email() -> None:
    req = SignupRequest(
        name="  홍길동 ",
        email="Hong@Example.com",
        phone="01012345678",
        password="abc123",
        phone_token="tok",
        agreed_to_terms=True,
    )
    assert req.name == "홍길동"
    assert req.email == "hong@example.com"
    assert req.phone == "010-1234-5678"
    # 만 14세 확인/마케팅 동의는 생략 시 False — 라우터가 만 14세 미확인을 400 으로 거부한다.
    assert req.age_over_14 is False
    assert req.marketing_consent is False


def test_signup_request_accepts_age_and_marketing_consents() -> None:
    req = SignupRequest(
        name="홍길동",
        email="hong@example.com",
        phone="01012345678",
        password="abc123",
        phone_token="tok",
        agreed_to_terms=True,
        age_over_14=True,
        marketing_consent=True,
    )
    assert req.age_over_14 is True
    assert req.marketing_consent is True


def test_signup_request_rejects_weak_password() -> None:
    with pytest.raises(ValidationError):
        SignupRequest(
            name="홍길동",
            email="hong@example.com",
            phone="01012345678",
            password="weak",  # 영문만 + 6자 미만
            phone_token="tok",
            agreed_to_terms=True,
        )


def test_signup_request_requires_terms_agreement() -> None:
    with pytest.raises(ValidationError):
        SignupRequest(
            name="홍길동",
            email="hong@example.com",
            phone="01012345678",
            password="abc123",
            phone_token="tok",
            agreed_to_terms=False,
        )


def test_signup_request_rejects_omitted_terms_agreement() -> None:
    # 필드를 아예 생략해도(직접 API 호출) 거부되어야 한다 — Literal[True] 필수.
    with pytest.raises(ValidationError):
        SignupRequest(
            name="홍길동",
            email="hong@example.com",
            phone="01012345678",
            password="abc123",
            phone_token="tok",
        )
