"""Supabase Auth(GoTrue) admin 연동 서비스 (CMP-DIRECT).

이메일/비밀번호 회원가입·비밀번호 재설정·회원 탈퇴는 GoTrue admin API 를
service_role 키로 호출한다. 비밀번호는 auth.users 가 단독 관리하며(우리 테이블엔
password 컬럼 없음 — AGENTS §4.7 #3), service_role 키는 백엔드만 보유한다.

휴대폰 번호는 ``user_metadata.phone`` 에 정규화 형태로 저장한다(auth.users.phone 의
unique/phone-provider 결합을 피하기 위함). 아이디(이메일) 찾기는 DB 의
``auth.users.raw_user_meta_data->>'phone'`` 를 조회한다 — 백엔드 DB role 은 RLS 를
우회하므로 service_role REST 없이도 안전하게 읽을 수 있다.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

import httpx
import sqlalchemy as sa

from ..config import Settings, get_settings
from ..db import get_engine
from ..errors import ZippinException


def _admin_base(settings: Settings) -> str:
    issuer = settings.supabase_jwt_issuer
    if issuer:
        return issuer.rstrip("/")
    if settings.supabase_url:
        return settings.supabase_url.rstrip("/") + "/auth/v1"
    raise ZippinException(
        "Supabase Auth 가 설정되지 않았습니다.",
        code="AUTH_SESSION_CONFIG_MISSING",
        http_status=503,
    )


def _require_service_role(settings: Settings) -> str:
    if not settings.supabase_service_role_key:
        raise ZippinException(
            "회원가입 기능이 설정되지 않았습니다.",
            code="AUTH_ADMIN_NOT_CONFIGURED",
            http_status=503,
        )
    return settings.supabase_service_role_key


def _admin_headers(service_role_key: str) -> dict[str, str]:
    return {
        "apikey": service_role_key,
        "Authorization": f"Bearer {service_role_key}",
        "Content-Type": "application/json",
    }


@dataclass(frozen=True)
class CreatedUser:
    user_id: uuid.UUID


def _conflict(message: str, code: str) -> ZippinException:
    return ZippinException(message, code=code, http_status=409)


async def find_emails_by_phone(phone: str) -> list[dict[str, str]]:
    """정규화된 휴대폰 번호로 가입 이메일을 조회한다(생성일 오름차순)."""

    query = sa.text(
        """
        select email, created_at
        from auth.users
        where raw_user_meta_data->>'phone' = :phone
          and email is not null
          and (is_anonymous is not true)
        order by created_at asc
        """
    )
    async with get_engine().begin() as conn:
        rows = (await conn.execute(query, {"phone": phone})).all()
    return [
        {"email": row.email, "created_at": row.created_at.isoformat()} for row in rows
    ]


async def get_email_by_user_id(user_id: uuid.UUID) -> str | None:
    query = sa.text("select email from auth.users where id = :id limit 1")
    async with get_engine().begin() as conn:
        row = (await conn.execute(query, {"id": str(user_id)})).first()
    return row.email if row is not None and row.email else None


async def verify_password(
    *,
    email: str,
    password: str,
    http_client: httpx.AsyncClient | None = None,
    settings: Settings | None = None,
) -> bool:
    """GoTrue password grant 로 현재 비밀번호가 맞는지 확인한다(세션은 버린다)."""

    settings = settings or get_settings()
    if not settings.supabase_publishable_key:
        raise ZippinException(
            "비밀번호 확인이 설정되지 않았습니다.",
            code="AUTH_ADMIN_NOT_CONFIGURED",
            http_status=503,
        )
    url = f"{_admin_base(settings)}/token?grant_type=password"
    headers = {
        "apikey": settings.supabase_publishable_key,
        "Content-Type": "application/json",
    }

    async def _run(client: httpx.AsyncClient) -> httpx.Response:
        return await client.post(
            url, json={"email": email, "password": password}, headers=headers
        )

    response = await _send(_run, http_client)
    return response.status_code == 200


async def find_user_id_by_email_and_phone(email: str, phone: str) -> uuid.UUID | None:
    """이메일 + 휴대폰이 같은 계정에 속하는지 확인하고 user id 를 반환한다."""

    query = sa.text(
        """
        select id
        from auth.users
        where lower(email) = lower(:email)
          and raw_user_meta_data->>'phone' = :phone
          and (is_anonymous is not true)
        limit 1
        """
    )
    async with get_engine().begin() as conn:
        row = (await conn.execute(query, {"email": email, "phone": phone})).first()
    return row.id if row is not None else None


async def create_email_user(
    *,
    email: str,
    password: str,
    phone: str,
    display_name: str,
    http_client: httpx.AsyncClient | None = None,
    settings: Settings | None = None,
) -> CreatedUser:
    """GoTrue admin API 로 이메일/비밀번호 사용자를 생성한다.

    이메일 자동 확인 여부는 ``settings.signup_auto_confirm_email`` 로 제어한다(기본 True).
    자동 확인은 이메일 소유를 검증하지 않으므로 squatting 위험이 있다 — 보안 강화 시
    False + Supabase 이메일 확인 플로우를 쓴다.
    """

    settings = settings or get_settings()
    service_role_key = _require_service_role(settings)

    # 같은 휴대폰으로 이미 가입한 영구 계정이 있으면 막는다(1 휴대폰 = 1 계정).
    existing = await find_emails_by_phone(phone)
    if existing:
        raise _conflict(
            "이미 해당 휴대폰 번호로 가입된 계정이 있습니다.",
            code="PHONE_ALREADY_REGISTERED",
        )

    url = f"{_admin_base(settings)}/admin/users"
    body = {
        "email": email,
        "password": password,
        # 휴대폰 인증만으로 본인확인을 대신할지(자동 confirm) 운영 설정으로 제어한다.
        # 자동 confirm 은 이메일 소유를 검증하지 않으므로 squatting 위험이 있다 — 강화 시 False.
        "email_confirm": settings.signup_auto_confirm_email,
        "user_metadata": {
            "name": display_name,
            "display_name": display_name,
            "phone": phone,
        },
    }

    async def _run(client: httpx.AsyncClient) -> httpx.Response:
        return await client.post(
            url, json=body, headers=_admin_headers(service_role_key)
        )

    response = await _send(_run, http_client)

    if response.status_code in (200, 201):
        data = response.json()
        user_id = data.get("id") or (data.get("user") or {}).get("id")
        if not user_id:
            raise ZippinException(
                "회원 생성 응답이 올바르지 않습니다.",
                code="AUTH_ADMIN_BAD_RESPONSE",
                http_status=502,
            )
        return CreatedUser(user_id=uuid.UUID(str(user_id)))

    if response.status_code in (400, 409, 422):
        message = _error_message(response)
        if "registered" in message.lower() or "already" in message.lower():
            raise _conflict(
                "이미 가입된 이메일입니다.", code="EMAIL_ALREADY_REGISTERED"
            )
        raise ZippinException(
            "회원 정보가 올바르지 않습니다.",
            code="AUTH_ADMIN_REJECTED",
            http_status=422,
        )

    raise ZippinException(
        "회원 생성에 실패했습니다. 잠시 후 다시 시도해 주세요.",
        code="AUTH_ADMIN_FAILED",
        http_status=502,
    )


async def update_user_password(
    *,
    user_id: uuid.UUID,
    password: str,
    http_client: httpx.AsyncClient | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    service_role_key = _require_service_role(settings)
    url = f"{_admin_base(settings)}/admin/users/{user_id}"

    async def _run(client: httpx.AsyncClient) -> httpx.Response:
        return await client.put(
            url, json={"password": password}, headers=_admin_headers(service_role_key)
        )

    response = await _send(_run, http_client)
    if response.status_code != 200:
        raise ZippinException(
            "비밀번호 재설정에 실패했습니다.",
            code="AUTH_ADMIN_FAILED",
            http_status=502,
        )


async def delete_user(
    *,
    user_id: uuid.UUID,
    http_client: httpx.AsyncClient | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    service_role_key = _require_service_role(settings)
    url = f"{_admin_base(settings)}/admin/users/{user_id}"

    async def _run(client: httpx.AsyncClient) -> httpx.Response:
        return await client.delete(url, headers=_admin_headers(service_role_key))

    response = await _send(_run, http_client)
    if response.status_code not in (200, 204):
        raise ZippinException(
            "회원 탈퇴 처리에 실패했습니다.",
            code="AUTH_ADMIN_FAILED",
            http_status=502,
        )


async def _send(run, http_client: httpx.AsyncClient | None) -> httpx.Response:
    try:
        if http_client is not None:
            return await run(http_client)
        async with httpx.AsyncClient(timeout=10.0) as client:
            return await run(client)
    except httpx.HTTPError as exc:
        raise ZippinException(
            "Supabase Auth 호출에 실패했습니다.",
            code="AUTH_ADMIN_UNAVAILABLE",
            http_status=502,
        ) from exc


def _error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text or ""
    if isinstance(data, dict):
        return str(
            data.get("msg")
            or data.get("message")
            or data.get("error_description")
            or data.get("error")
            or data.get("error_code")
            or ""
        )
    return ""
