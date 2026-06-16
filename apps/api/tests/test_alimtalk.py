"""카카오 알림톡 서비스 테스트 (CMP-DIRECT).

실제 SOLAPI 호출 없이 ``SolapiMessageService.send()`` 테스트 더블로 RequestMessage
구성(채널/템플릿/변수/수신번호)을 검증한다. 변수 키는 SDK 의 ``KakaoOption`` 이
``#{변수명}`` 으로 감싼다.
"""

from __future__ import annotations

import pytest
from solapi.error.MessageNotReceiveError import MessageNotReceivedError
from solapi.model import RequestMessage

from src.config import Settings
from src.errors import ZippinException
from src.services import alimtalk

_CHANNEL_ID = "KA01PFTESTCHANNEL"


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


def _alimtalk_settings(**overrides) -> Settings:
    values: dict[str, object] = {
        "solapi_api_key": "key",
        "solapi_api_secret": "secret",
        "solapi_sender_phone": "01000000000",
        "solapi_channel_id": _CHANNEL_ID,
    }
    values.update(overrides)
    return Settings(**values)


async def test_lead_received_uses_expert_template_for_lead_page() -> None:
    service = _FakeService()
    await alimtalk.send_lead_received_alimtalk(
        phone="010-1234-5678",
        applicant_name="홍길동",
        source_form="lead_page",
        service=service,
        settings=_alimtalk_settings(),
    )
    msg = service.sent[0]
    assert msg.to == "01012345678"  # RequestMessage 가 하이픈을 직접 정규화한다.
    kakao = msg.kakao_options
    assert kakao is not None
    assert kakao.pf_id == _CHANNEL_ID
    assert (
        kakao.template_id == _alimtalk_settings().solapi_template_expert_lead_received
    )
    assert kakao.variables == {"#{고객명}": "홍길동"}
    assert kakao.disable_sms is True


async def test_lead_received_uses_quick_template_for_main_page() -> None:
    service = _FakeService()
    await alimtalk.send_lead_received_alimtalk(
        phone="010-1234-5678",
        applicant_name="홍길동",
        source_form="main_page",
        service=service,
        settings=_alimtalk_settings(),
    )
    assert (
        service.sent[0].kakao_options.template_id
        == _alimtalk_settings().solapi_template_quick_lead_received
    )


async def test_lead_received_rejects_unknown_source_form() -> None:
    with pytest.raises(ValueError):
        await alimtalk.send_lead_received_alimtalk(
            phone="010-1234-5678",
            applicant_name="홍길동",
            source_form="unknown_form",
            service=_FakeService(),
            settings=_alimtalk_settings(),
        )


async def test_assignee_assigned_sends_both_variables() -> None:
    service = _FakeService()
    await alimtalk.send_assignee_assigned_alimtalk(
        phone="010-1234-5678",
        applicant_name="홍길동",
        assignee_name="김매니저",
        service=service,
        settings=_alimtalk_settings(),
    )
    kakao = service.sent[0].kakao_options
    assert kakao.template_id == _alimtalk_settings().solapi_template_assignee_assigned
    assert kakao.variables == {"#{고객명}": "홍길동", "#{담당자명}": "김매니저"}


async def test_send_alimtalk_raises_503_when_not_configured() -> None:
    with pytest.raises(ZippinException) as exc:
        await alimtalk.send_alimtalk(
            phone="010-1234-5678",
            template_id=_alimtalk_settings().solapi_template_assignee_assigned,
            variables={"고객명": "홍길동"},
            service=_FakeService(),
            settings=_alimtalk_settings(solapi_channel_id=None),
        )
    assert exc.value.code == "ALIMTALK_PROVIDER_NOT_CONFIGURED"


async def test_send_alimtalk_maps_rejection_to_send_failed() -> None:
    service = _FakeService(error=MessageNotReceivedError([]))
    with pytest.raises(ZippinException) as exc:
        await alimtalk.send_lead_received_alimtalk(
            phone="010-1234-5678",
            applicant_name="홍길동",
            source_form="main_page",
            service=service,
            settings=_alimtalk_settings(),
        )
    assert exc.value.code == "ALIMTALK_SEND_FAILED"


async def test_send_alimtalk_maps_transport_error_to_send_failed() -> None:
    service = _FakeService(error=Exception("ValidationError", "pfId 불일치"))
    with pytest.raises(ZippinException) as exc:
        await alimtalk.send_lead_received_alimtalk(
            phone="010-1234-5678",
            applicant_name="홍길동",
            source_form="lead_page",
            service=service,
            settings=_alimtalk_settings(),
        )
    assert exc.value.code == "ALIMTALK_SEND_FAILED"


async def test_notify_lead_received_skips_when_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.services.alimtalk.get_settings",
        lambda: _alimtalk_settings(solapi_channel_id=None),
    )

    async def fail_if_called(**_kwargs):
        raise AssertionError("미설정이면 발송을 시도하면 안 된다.")

    monkeypatch.setattr(
        "src.services.alimtalk.send_lead_received_alimtalk", fail_if_called
    )
    await alimtalk.notify_lead_received(
        phone="010-1234-5678", applicant_name="홍길동", source_form="main_page"
    )


async def test_notify_lead_received_swallows_send_failure(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.services.alimtalk.get_settings", lambda: _alimtalk_settings()
    )

    async def boom(**_kwargs):
        raise ZippinException("발송 실패", code="ALIMTALK_SEND_FAILED", http_status=502)

    monkeypatch.setattr("src.services.alimtalk.send_lead_received_alimtalk", boom)
    # 예외가 호출자(background task)로 전파되지 않아야 한다.
    await alimtalk.notify_lead_received(
        phone="010-1234-5678", applicant_name="홍길동", source_form="lead_page"
    )
