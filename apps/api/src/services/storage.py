"""Supabase Storage 공용 헬퍼 — service_role 서명 URL 발급 (CMP-DIRECT).

``home_check`` 의 PDF 서명 패턴을 일반화해 세션 도면 등 다른 트랙도 재사용한다.
서버 전용(service_role 키)이며 브라우저에 노출되지 않는다.
"""

from __future__ import annotations

from urllib.parse import quote

import httpx

from ..config import Settings
from ..logging import log_http_call


def storage_base(settings: Settings) -> str | None:
    """Supabase Storage REST base. URL/서비스키 미설정 시 None."""

    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    return settings.supabase_url.rstrip("/") + "/storage/v1"


async def sign_object_url(
    settings: Settings,
    *,
    bucket: str,
    object_path: str,
    expires_in: int = 3600,
    operation: str = "sign_object",
) -> str | None:
    """단기 서명 다운로드 URL 을 발급한다. 실패하면 None(호출자가 degrade)."""

    base = storage_base(settings)
    if base is None:
        return None
    # object_path 를 인코딩(세그먼트 구분 '/' 만 보존)해 HTTP 정규화로 다른 객체를
    # 가리키지 못하게 한다(방어적 — 호출 전 경로 검증과 이중 안전, #path-traversal).
    safe_path = quote(object_path, safe="/")
    url = f"{base}/object/sign/{bucket}/{safe_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key or "",
        "Content-Type": "application/json",
    }

    async def _do() -> httpx.Response:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.post(
                url, json={"expiresIn": expires_in}, headers=headers
            )

    try:
        response = await log_http_call("supabase_storage", operation, _do)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        signed = response.json().get("signedURL")
    except ValueError:
        return None
    if not signed:
        return None
    return settings.supabase_url.rstrip("/") + "/storage/v1" + signed
