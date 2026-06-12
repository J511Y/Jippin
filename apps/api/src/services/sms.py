"""SOLAPI SMS 발송 서비스 (CMP-DIRECT).

휴대폰 본인확인용 6자리 인증번호를 공식 SOLAPI Python SDK(`solapi`)로 발송한다.
HMAC-SHA256 인증 헤더 구성·발송 엔드포인트(`/messages/v4/send-many/detail`)·실패
판정은 모두 SDK 가 담당한다 — 직접 구현하지 않는다(과거 stdlib 직접 구현 → 리팩토링).

발신번호(`SOLAPI_SENDER_PHONE`)는 SOLAPI 콘솔에 사전 등록된 번호여야 발송된다.
키/시크릿/발신번호 미설정 시 503(SMS_PROVIDER_NOT_CONFIGURED).
"""

from __future__ import annotations

import asyncio

from solapi import SolapiMessageService
from solapi.error.MessageNotReceiveError import MessageNotReceivedError
from solapi.model import RequestMessage

from ..config import Settings, get_settings
from ..errors import ZippinException
from ..logging import get_logger, log_external_op
from .solapi_client import build_message_service

logger = get_logger("zippin.sms")


def _require_provider(settings: Settings) -> tuple[str, str, str]:
    if not (
        settings.solapi_api_key
        and settings.solapi_api_secret
        and settings.solapi_sender_phone
    ):
        raise ZippinException(
            "문자 발송이 설정되지 않았습니다.",
            code="SMS_PROVIDER_NOT_CONFIGURED",
            http_status=503,
        )
    return (
        settings.solapi_api_key,
        settings.solapi_api_secret,
        settings.solapi_sender_phone,
    )


async def send_verification_sms(
    *,
    phone: str,
    code: str,
    service: SolapiMessageService | None = None,
    settings: Settings | None = None,
) -> None:
    """인증번호 문자를 발송한다. 실패 시 ``ZippinException``.

    수신/발신번호의 하이픈 제거는 SDK 의 ``RequestMessage`` 가 직접 정규화한다.
    """

    settings = settings or get_settings()
    api_key, api_secret, sender = _require_provider(settings)

    text = f"[집핀] 인증번호 [{code}] 를 입력해 주세요."
    message = RequestMessage(from_=sender, to=phone, text=text)
    service = service or build_message_service(settings, api_key, api_secret)

    try:
        # SDK 의 send() 는 동기(blocking) httpx 호출이므로 스레드로 위임해
        # 이벤트 루프를 막지 않는다. 성공/실패는 external_call 로그로 남는다.
        async with log_external_op("solapi", "send_verification_sms"):
            await asyncio.to_thread(service.send, message)
    except MessageNotReceivedError as exc:
        # 전건 접수 실패. 수신/발신번호가 실패 목록에 담겨 있으므로 개수만 로깅한다(PII 보호).
        logger.warning("sms_send_rejected", failed_count=len(exc.failed_messages))
        raise ZippinException(
            "인증번호 발송에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            code="SMS_SEND_FAILED",
            http_status=502,
        ) from exc
    except Exception as exc:
        # 네트워크/4xx/5xx 등 SDK 가 올리는 그 밖의 오류(상세는 external_call_failed 에 기록).
        raise ZippinException(
            "인증번호 발송에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            code="SMS_SEND_FAILED",
            http_status=502,
        ) from exc
