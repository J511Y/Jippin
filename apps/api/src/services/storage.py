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


async def head_object(
    settings: Settings,
    *,
    bucket: str,
    object_path: str,
    operation: str = "head_object",
) -> tuple[str | None, int | None] | None:
    """저장된 객체의 (content_type, content_length) 를 조회한다 — 검증 못 하면 None.

    클라이언트가 백엔드 라우트에 보낸 JSON content_type/byte_size 는 신뢰할 수 없으므로
    (presign 우회 가능), 실제 Storage 객체 헤더로 검증한다. service-role 로 authenticated
    object 엔드포인트에 HEAD 한다.
    """

    base = storage_base(settings)
    if base is None:
        return None
    safe_path = quote(object_path, safe="/")
    url = f"{base}/object/authenticated/{bucket}/{safe_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key or "",
    }

    async def _do() -> httpx.Response:
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await client.head(url, headers=headers)

    try:
        response = await log_http_call("supabase_storage", operation, _do)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    content_type = response.headers.get("content-type")
    raw_len = response.headers.get("content-length")
    try:
        content_length = int(raw_len) if raw_len is not None else None
    except ValueError:
        content_length = None
    return content_type, content_length


async def download_object(
    settings: Settings,
    *,
    bucket: str,
    object_path: str,
    operation: str = "download_object",
) -> bytes | None:
    """service-role 로 저장 객체의 원본 바이트를 받는다 — 실패하면 None(호출자 degrade).

    리포트 PDF 가 도면 이미지를 인라인(data URI)으로 합성할 때, 짧은-수명 서명 URL 을
    거치지 않고 서버가 직접 authenticated 엔드포인트에서 내려받기 위해 쓴다.
    """

    base = storage_base(settings)
    if base is None:
        return None
    safe_path = quote(object_path, safe="/")
    url = f"{base}/object/authenticated/{bucket}/{safe_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key or "",
    }

    async def _do() -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.get(url, headers=headers)

    try:
        response = await log_http_call("supabase_storage", operation, _do)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    return response.content


async def upload_object(
    settings: Settings,
    *,
    bucket: str,
    object_path: str,
    content: bytes,
    content_type: str,
    upsert: bool = True,
    operation: str = "upload_object",
) -> bool:
    """service-role 로 객체를 업로드한다(기본 upsert). 성공 여부를 반환(실패 시 False).

    ``home_check`` 의 ``_upload_pdf`` 패턴을 일반화한다 — 발부 PDF 등 서버 생성
    산출물을 Storage 에 보관할 때 공용으로 쓴다.
    """

    base = storage_base(settings)
    if base is None:
        return False
    safe_path = quote(object_path, safe="/")
    url = f"{base}/object/{bucket}/{safe_path}"
    headers = {
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "apikey": settings.supabase_service_role_key or "",
        "Content-Type": content_type,
    }
    if upsert:
        headers["x-upsert"] = "true"

    async def _do() -> httpx.Response:
        async with httpx.AsyncClient(timeout=30.0) as client:
            return await client.post(url, content=content, headers=headers)

    try:
        response = await log_http_call("supabase_storage", operation, _do)
    except httpx.HTTPError:
        return False
    return response.status_code in (200, 201)
