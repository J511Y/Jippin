"""SOLAPI SDK 클라이언트 공용 헬퍼 (CMP-DIRECT).

SMS 본인인증(``sms.py``)과 카카오 알림톡(``alimtalk.py``)이 공유하는
``SolapiMessageService`` 생성기.
"""

from __future__ import annotations

from solapi import SolapiMessageService

from ..config import Settings


def build_message_service(
    settings: Settings, api_key: str, api_secret: str
) -> SolapiMessageService:
    service = SolapiMessageService(api_key=api_key, api_secret=api_secret)
    # SDK 는 base_url 을 https://api.solapi.com 으로 고정한다. 프록시/모의 서버로
    # 엔드포인트를 바꿔야 하는 환경을 위해 설정값(SOLAPI_API_URL)으로 덮어쓴다.
    service.base_url = settings.solapi_api_url.rstrip("/")
    return service
