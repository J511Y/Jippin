"""SOLAPI 카카오 알림톡 발송 서비스 (CMP-DIRECT).

상담 접수/담당자 배정 알림톡을 공식 SOLAPI Python SDK(`solapi`)로 발송한다.
템플릿은 SOLAPI 콘솔(카카오 비즈메시지)에 등록·검수 승인된 것만 발송되며, 변수
치환은 ``KakaoOption.variables`` 가 키를 ``#{변수명}`` 으로 감싸 SOLAPI 서버측에서
수행한다.

- 채널 ID(pfId)는 ``SOLAPI_CHANNEL_ID`` 환경변수로 주입한다.
- 상담 접수 알림(``notify_lead_received``)은 best-effort 다 — 미설정이면 건너뛰고,
  발송 실패도 리드 생성 응답에 영향을 주지 않는다(로그만 남김).
- 담당자 배정(``send_assignee_assigned_alimtalk``)은 추후 관리자 페이지의 배정
  액션에서 그대로 호출하는 용도다. 실패를 ``ZippinException`` 으로 올려 호출자가
  사용자에게 결과를 알릴 수 있게 한다.
"""

from __future__ import annotations

import asyncio

from solapi import SolapiMessageService
from solapi.error.MessageNotReceiveError import MessageNotReceivedError
from solapi.model import KakaoOption, RequestMessage

from ..config import Settings, get_settings
from ..errors import ZippinException
from ..logging import get_logger, log_external_op
from .solapi_client import build_message_service

logger = get_logger("zippin.alimtalk")

# 알림톡 템플릿 ID 는 환경변수(Settings)로 주입한다. 콘솔에서 템플릿을 재등록해 ID 가
# 바뀌면 코드 배포 없이 환경변수로 교체할 수 있다. 변수 목록이 달라지면 아래 발송 함수의
# variables 도 함께 맞춰야 한다. 기본값(현재 승인본)은 config.Settings 에 있다.


def _lead_received_template_id(settings: Settings, source_form: str) -> str | None:
    # 상담 접수 알림은 신청 경로(source_form)에 따라 템플릿이 갈린다.
    return {
        "lead_page": settings.solapi_template_expert_lead_received,
        "main_page": settings.solapi_template_quick_lead_received,
    }.get(source_form)


def is_configured(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(
        settings.solapi_api_key
        and settings.solapi_api_secret
        and settings.solapi_channel_id
    )


def _require_provider(settings: Settings) -> tuple[str, str, str]:
    if not (
        settings.solapi_api_key
        and settings.solapi_api_secret
        and settings.solapi_channel_id
    ):
        raise ZippinException(
            "알림톡 발송이 설정되지 않았습니다.",
            code="ALIMTALK_PROVIDER_NOT_CONFIGURED",
            http_status=503,
        )
    return (
        settings.solapi_api_key,
        settings.solapi_api_secret,
        settings.solapi_channel_id,
    )


async def send_alimtalk(
    *,
    phone: str,
    template_id: str,
    variables: dict[str, str],
    service: SolapiMessageService | None = None,
    settings: Settings | None = None,
) -> None:
    """알림톡 한 건을 발송한다. 실패 시 ``ZippinException``.

    수신번호의 하이픈 제거는 SDK 의 ``RequestMessage`` 가 직접 정규화한다.
    """

    settings = settings or get_settings()
    api_key, api_secret, channel_id = _require_provider(settings)

    message = RequestMessage(
        # 발신번호는 SMS 대체발송에만 쓰인다. 대체발송은 콘솔 템플릿에 구성하지 않았고
        # 본문 불일치/이중 과금을 막기 위해 끈다(disable_sms=True).
        from_=settings.solapi_sender_phone,
        to=phone,
        kakao_options=KakaoOption(
            pf_id=channel_id,
            template_id=template_id,
            variables=variables,
            disable_sms=True,
        ),
    )
    service = service or build_message_service(settings, api_key, api_secret)

    try:
        # SDK 의 send() 는 동기(blocking) httpx 호출이므로 스레드로 위임해
        # 이벤트 루프를 막지 않는다. 성공/실패는 external_call 로그로 남는다.
        async with log_external_op("solapi", "send_alimtalk"):
            await asyncio.to_thread(service.send, message)
    except MessageNotReceivedError as exc:
        # 전건 접수 실패. 실패 목록에 수신번호가 담기므로 개수/템플릿만 로깅한다(PII 보호).
        logger.warning(
            "alimtalk_send_rejected",
            template_id=template_id,
            failed_count=len(exc.failed_messages),
        )
        raise ZippinException(
            "알림톡 발송에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            code="ALIMTALK_SEND_FAILED",
            http_status=502,
        ) from exc
    except Exception as exc:
        # 네트워크/4xx/5xx 등 SDK 가 올리는 그 밖의 오류(상세는 external_call_failed 에 기록).
        raise ZippinException(
            "알림톡 발송에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            code="ALIMTALK_SEND_FAILED",
            http_status=502,
        ) from exc


async def send_lead_received_alimtalk(
    *,
    phone: str,
    applicant_name: str,
    source_form: str,
    service: SolapiMessageService | None = None,
    settings: Settings | None = None,
) -> None:
    """상담 접수 알림톡 — 신청 경로(source_form)에 맞는 템플릿으로 발송한다."""

    settings = settings or get_settings()
    template_id = _lead_received_template_id(settings, source_form)
    if template_id is None:
        raise ValueError(f"알 수 없는 source_form 입니다: {source_form!r}")
    await send_alimtalk(
        phone=phone,
        template_id=template_id,
        variables={"고객명": applicant_name},
        service=service,
        settings=settings,
    )


async def send_assignee_assigned_alimtalk(
    *,
    phone: str,
    applicant_name: str,
    assignee_name: str,
    service: SolapiMessageService | None = None,
    settings: Settings | None = None,
) -> None:
    """담당자 배정 알림톡. 추후 관리자 페이지의 담당자 배정 액션에서 호출한다."""

    settings = settings or get_settings()
    await send_alimtalk(
        phone=phone,
        template_id=settings.solapi_template_assignee_assigned,
        variables={"고객명": applicant_name, "담당자명": assignee_name},
        service=service,
        settings=settings,
    )


async def notify_lead_received(
    *,
    phone: str,
    applicant_name: str,
    source_form: str,
) -> None:
    """상담 접수 알림톡의 best-effort 발송 — 어떤 실패도 호출자에게 전파하지 않는다.

    ``POST /leads`` 응답 이후 background task 로 실행된다. 리드는 이미 저장됐으므로
    알림 실패가 신청 자체를 실패시키면 안 된다.
    """

    settings = get_settings()
    if not is_configured(settings):
        logger.info(
            "alimtalk_skipped_not_configured",
            kind="lead_received",
            source_form=source_form,
        )
        return
    try:
        await send_lead_received_alimtalk(
            phone=phone,
            applicant_name=applicant_name,
            source_form=source_form,
            settings=settings,
        )
    except Exception:
        # 발송 상세 실패 사유는 send_alimtalk 가 이미 로깅했다.
        logger.warning("alimtalk_lead_received_failed", source_form=source_form)
        return
    logger.info("alimtalk_lead_received_sent", source_form=source_form)
