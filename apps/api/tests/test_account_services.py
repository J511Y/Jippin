"""SOLAPI 발송 래퍼·이메일 마스킹·가입 동의 기록·휴대폰 토큰 검증 단위 테스트 (CMP-DIRECT)."""

from __future__ import annotations

import uuid

import pytest

from solapi.error.MessageNotReceiveError import MessageNotReceivedError
from solapi.model import RequestMessage
from sqlalchemy.dialects import postgresql

from src.config import Settings
from src.errors import ZippinException
from src.services.account import (
    AGE_OVER_14_TERM_ID,
    MARKETING_TERM_ID,
    _mask_email,
    create_signup_profile,
)
from src.services.phone_verification import assert_token_phone_match
from src.services.sms import send_verification_sms


class _FakeService:
    """SolapiMessageService 의 send() 만 흉내 내는 테스트 더블."""

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.sent: list[RequestMessage] = []

    def send(self, message: RequestMessage):
        self.sent.append(message)
        if self.error is not None:
            raise self.error
        return None


def _sms_settings() -> Settings:
    return Settings(
        solapi_api_key="key",
        solapi_api_secret="secret",
        solapi_sender_phone="01000000000",
    )


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


class _FakeBegin:
    def __init__(self, conn) -> None:
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeEngine:
    def __init__(self, conn) -> None:
        self.conn = conn

    def begin(self) -> _FakeBegin:
        return _FakeBegin(self.conn)


class _FakeConnection:
    def __init__(self) -> None:
        self.statements: list = []

    async def execute(self, statement):
        self.statements.append(statement)
        return None


def _consent_term_ids(statements) -> set[str]:
    """terms_consents INSERT 문에서 multi-VALUES 의 term_id 파라미터를 추출한다."""

    term_ids: set[str] = set()
    for stmt in statements:
        if "INSERT INTO terms_consents" not in str(stmt):
            continue
        params = stmt.compile(dialect=postgresql.dialect()).params
        term_ids |= {v for k, v in params.items() if k.startswith("term_id")}
    return term_ids


@pytest.fixture
def signup_profile_conn(monkeypatch) -> _FakeConnection:
    conn = _FakeConnection()
    monkeypatch.setattr("src.services.account.get_engine", lambda: _FakeEngine(conn))
    monkeypatch.setattr("src.services.account.get_settings", lambda: Settings())
    return conn


async def test_create_signup_profile_records_age_attestation(
    signup_profile_conn,
) -> None:
    # 만 14세 이상 확인(age_over_14)은 항상 기록, 마케팅 미동의는 row 를 남기지 않는다.
    await create_signup_profile(
        user_id=uuid.uuid4(), display_name="홍길동", marketing_agreed=False
    )
    term_ids = _consent_term_ids(signup_profile_conn.statements)
    assert AGE_OVER_14_TERM_ID in term_ids
    assert "service_terms" in term_ids
    assert "privacy_policy" in term_ids
    assert MARKETING_TERM_ID not in term_ids


async def test_create_signup_profile_records_marketing_consent_when_agreed(
    signup_profile_conn,
) -> None:
    await create_signup_profile(
        user_id=uuid.uuid4(), display_name="홍길동", marketing_agreed=True
    )
    term_ids = _consent_term_ids(signup_profile_conn.statements)
    assert MARKETING_TERM_ID in term_ids
    assert AGE_OVER_14_TERM_ID in term_ids


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


async def test_send_verification_sms_builds_message_and_sends() -> None:
    service = _FakeService()
    await send_verification_sms(
        phone="010-1234-5678",
        code="123456",
        service=service,
        settings=_sms_settings(),
    )
    msg = service.sent[0]
    # RequestMessage 가 하이픈을 직접 정규화한다.
    assert msg.to == "01012345678"
    assert msg.from_ == "01000000000"
    assert msg.text is not None and "123456" in msg.text


async def test_send_verification_sms_raises_when_all_messages_rejected() -> None:
    # SDK 가 전건 접수 실패 시 올리는 예외 → SMS_SEND_FAILED 로 매핑된다.
    service = _FakeService(error=MessageNotReceivedError([]))
    with pytest.raises(ZippinException) as exc:
        await send_verification_sms(
            phone="010-1234-5678",
            code="123456",
            service=service,
            settings=_sms_settings(),
        )
    assert exc.value.code == "SMS_SEND_FAILED"


async def test_send_verification_sms_raises_on_transport_error() -> None:
    # SDK 가 4xx/5xx/네트워크 오류로 올리는 일반 예외도 SMS_SEND_FAILED 로 매핑된다.
    service = _FakeService(error=Exception("ValidationError", "발신번호 미등록"))
    with pytest.raises(ZippinException) as exc:
        await send_verification_sms(
            phone="010-1234-5678",
            code="123456",
            service=service,
            settings=_sms_settings(),
        )
    assert exc.value.code == "SMS_SEND_FAILED"


async def test_send_verification_sms_requires_provider_configured() -> None:
    with pytest.raises(ZippinException) as exc:
        await send_verification_sms(
            phone="010-1234-5678",
            code="123456",
            service=_FakeService(),
            settings=Settings(),
        )
    assert exc.value.code == "SMS_PROVIDER_NOT_CONFIGURED"
