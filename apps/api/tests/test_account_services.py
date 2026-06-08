"""SOLAPI 서명 헤더·이메일 마스킹·휴대폰 토큰 검증 단위 테스트 (CMP-DIRECT)."""

from __future__ import annotations

import hashlib
import hmac
import re

import pytest

from src.errors import ZippinException
from src.services.account import _mask_email
from src.services.phone_verification import assert_token_phone_match
from src.services.sms import _build_authorization


def test_build_authorization_signature_is_valid_hmac() -> None:
    header = _build_authorization("APIKEY123", "SECRET456")
    assert header.startswith("HMAC-SHA256 ")
    parts = dict(
        re.match(r"(\w+)=(.+)", kv.strip()).groups()  # type: ignore[union-attr]
        for kv in header[len("HMAC-SHA256 ") :].split(",")
    )
    assert parts["apiKey"] == "APIKEY123"
    expected = hmac.new(
        b"SECRET456",
        (parts["date"] + parts["salt"]).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    assert parts["signature"] == expected


@pytest.mark.parametrize(
    "email, expected",
    [
        ("abcde@gmail.com", "ab***@gmail.com"),
        ("ab@gmail.com", "a*@gmail.com"),
        ("a@gmail.com", "a*@gmail.com"),
    ],
)
def test_mask_email(email: str, expected: str) -> None:
    assert _mask_email(email) == expected


def test_assert_token_phone_match_accepts_equivalent_formats() -> None:
    # 토큰에 저장된 번호와 요청 번호의 표기가 달라도 정규화 후 일치하면 통과한다.
    assert assert_token_phone_match("01012345678", "010-1234-5678") == "010-1234-5678"


def test_assert_token_phone_match_rejects_mismatch() -> None:
    with pytest.raises(ZippinException) as exc:
        assert_token_phone_match("01099998888", "010-1234-5678")
    assert exc.value.code == "PHONE_TOKEN_INVALID"


def test_assert_token_phone_match_rejects_missing_token() -> None:
    with pytest.raises(ZippinException) as exc:
        assert_token_phone_match(None, "010-1234-5678")
    assert exc.value.code == "PHONE_TOKEN_INVALID"
