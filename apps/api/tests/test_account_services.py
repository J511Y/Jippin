"""SOLAPI 서명 헤더·이메일 마스킹·휴대폰 토큰 검증 단위 테스트 (CMP-DIRECT)."""

from __future__ import annotations

import hashlib
import hmac
import re

import pytest


from src.config import Settings
from src.errors import ZippinException
from src.services.account import _mask_email
from src.services.phone_verification import assert_token_phone_match
from src.services.sms import _build_authorization, send_verification_sms


class _FakeResponse:
    def __init__(self, status_code: int = 200, body: dict | None = None) -> None:
        self.status_code = status_code
        self._body = body or {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


class _FakeClient:
    def __init__(self, response: _FakeResponse) -> None:
        self.response = response
        self.calls: list[dict] = []

    async def post(self, url, json=None, headers=None):  # noqa: A002
        self.calls.append({"url": url, "json": json, "headers": headers})
        return self.response


def _sms_settings() -> Settings:
    return Settings(
        solapi_api_key="key",
        solapi_api_secret="secret",
        solapi_sender_phone="01000000000",
    )


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


async def test_send_verification_sms_uses_send_many_detail_endpoint() -> None:
    client = _FakeClient(_FakeResponse(200, {}))
    await send_verification_sms(
        phone="010-1234-5678",
        code="123456",
        http_client=client,
        settings=_sms_settings(),
    )
    call = client.calls[0]
    # SOLAPI v4 공식 경로(messages 배열) — 단건 전용 /messages/v4/send 가 아니다.
    assert call["url"].endswith("/messages/v4/send-many/detail")
    assert "messages" in call["json"]
    msg = call["json"]["messages"][0]
    assert msg["to"] == "01012345678"
    assert msg["from"] == "01000000000"
    assert "123456" in msg["text"]
    assert call["headers"]["Authorization"].startswith("HMAC-SHA256 ")


async def test_send_verification_sms_raises_on_failed_message_list() -> None:
    client = _FakeClient(_FakeResponse(200, {"failedMessageList": [{"to": "x"}]}))
    with pytest.raises(ZippinException) as exc:
        await send_verification_sms(
            phone="010-1234-5678",
            code="123456",
            http_client=client,
            settings=_sms_settings(),
        )
    assert exc.value.code == "SMS_SEND_FAILED"
