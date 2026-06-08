"""SOLAPI SMS 발송 서비스 (CMP-DIRECT).

휴대폰 본인확인용 6자리 인증번호를 SOLAPI(https://solapi.com) 로 발송한다. SOLAPI 의
HMAC-SHA256 인증 헤더는 stdlib(`hmac`/`hashlib`) 로 직접 구성한다 — 별도 SDK 의존성을
추가하지 않는다.

인증 헤더 규격(SOLAPI 공식 문서):

    Authorization: HMAC-SHA256 apiKey=<KEY>, date=<ISO8601>, salt=<RANDOM>,
                   signature=<hex(hmac_sha256(secret, date + salt))>

발신번호(`SOLAPI_SENDER_PHONE`)는 SOLAPI 콘솔에 사전 등록된 번호여야 발송된다.
키/시크릿/발신번호 미설정 시 503(SMS_PROVIDER_NOT_CONFIGURED).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime

import httpx

from ..config import Settings, get_settings
from ..errors import ZippinException
from ..logging import get_logger

logger = get_logger("zippin.sms")

_SEND_PATH = "/messages/v4/send"


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


def _build_authorization(api_key: str, api_secret: str) -> str:
    """SOLAPI HMAC-SHA256 Authorization 헤더를 만든다."""

    date = datetime.now(UTC).isoformat()
    salt = secrets.token_hex(16)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        (date + salt).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"HMAC-SHA256 apiKey={api_key}, date={date}, "
        f"salt={salt}, signature={signature}"
    )


def _strip_phone(phone: str) -> str:
    """SOLAPI 는 하이픈 없는 숫자 형태의 수신번호를 기대한다."""

    return "".join(ch for ch in phone if ch.isdigit())


async def send_verification_sms(
    *,
    phone: str,
    code: str,
    http_client: httpx.AsyncClient | None = None,
    settings: Settings | None = None,
) -> None:
    """인증번호 문자를 발송한다. 실패 시 ``ZippinException``."""

    settings = settings or get_settings()
    api_key, api_secret, sender = _require_provider(settings)

    text = f"[집핀] 인증번호 [{code}] 를 입력해 주세요."
    payload = {
        "message": {
            "to": _strip_phone(phone),
            "from": _strip_phone(sender),
            "text": text,
        }
    }
    headers = {
        "Authorization": _build_authorization(api_key, api_secret),
        "Content-Type": "application/json",
    }
    url = settings.solapi_api_url.rstrip("/") + _SEND_PATH

    async def _run(client: httpx.AsyncClient) -> httpx.Response:
        return await client.post(url, json=payload, headers=headers)

    try:
        if http_client is not None:
            response = await _run(http_client)
        else:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await _run(client)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        # 본문에 수신번호/발신번호가 포함될 수 있으므로 status 만 로깅한다(PII 보호).
        logger.warning("sms_send_failed", status=exc.response.status_code)
        raise ZippinException(
            "인증번호 발송에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            code="SMS_SEND_FAILED",
            http_status=502,
        ) from exc
    except httpx.HTTPError as exc:
        logger.warning("sms_send_error")
        raise ZippinException(
            "인증번호 발송에 실패했습니다. 잠시 후 다시 시도해 주세요.",
            code="SMS_SEND_FAILED",
            http_status=502,
        ) from exc
