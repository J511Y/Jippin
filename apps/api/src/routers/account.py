"""이메일/비밀번호 회원가입·문자인증·아이디/비번 찾기·회원탈퇴 라우터 (CMP-DIRECT).

흐름:
  - ``POST /auth/phone/send-code``  — 휴대폰으로 6자리 인증번호 발송(SOLAPI).
  - ``POST /auth/phone/verify-code`` — 인증번호 검증 → 단기 ``phone_token`` 발급.
  - ``POST /auth/signup``           — phone_token + 이름/이메일/비밀번호로 Supabase 계정 생성.
  - ``POST /auth/find-email``       — 인증된 휴대폰으로 가입 이메일(마스킹) 조회.
  - ``POST /auth/reset-password``   — 인증된 휴대폰 + 이메일로 비밀번호 재설정.
  - ``DELETE /auth/account``        — 로그인한 회원 본인 탈퇴(익명 토큰 거부).

비밀번호는 auth.users 가 단독 관리한다(AGENTS §4.7 #3). 로그인 세션 발급은 기존
``/auth/supabase/session`` 브리지(web Route Handler)가 담당한다.
"""

from __future__ import annotations

import uuid

import httpx
from fastapi import APIRouter, Depends, Request

from ..auth.request_token import (
    RequestUser,
    require_supabase_request_user,
    verify_supabase_request_token,
)
from ..errors import ZippinException
from ..logging import get_logger
from ..schemas.account import (
    ChangePasswordRequest,
    ChangePasswordResponse,
    DeleteAccountResponse,
    FindEmailRequest,
    FindEmailResponse,
    FoundEmail,
    PhoneSendCodeRequest,
    PhoneSendCodeResponse,
    PhoneVerifyRequest,
    PhoneVerifyResponse,
    ResetPasswordRequest,
    ResetPasswordResponse,
    SignupRequest,
    SignupResponse,
)
from ..services import leads as leads_service
from ..services import sms as sms_service
from ..services import supabase_admin
from ..services.account import _mask_email, create_signup_profile
from ..services.phone_verification import (
    assert_token_phone_match,
    get_phone_verification_store,
)
from ..services.supabase_session import parse_bearer_token

logger = get_logger("zippin.account")
router = APIRouter(prefix="/auth", tags=["account"])


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    fly_ip = request.headers.get("fly-client-ip")
    if fly_ip:
        return fly_ip.strip()
    return request.client.host if request.client else None


@router.post("/phone/send-code", response_model=PhoneSendCodeResponse)
async def send_phone_code(
    payload: PhoneSendCodeRequest, request: Request
) -> PhoneSendCodeResponse:
    settings = sms_service.get_settings()
    store = get_phone_verification_store()
    # 번호 회전 남용 방지 — 번호 단위 한도(reserve_send) 전에 IP/글로벌 한도를 적용한다.
    await store.check_send_rate(_client_ip(request))
    code = await store.reserve_send(payload.phone)
    try:
        await sms_service.send_verification_sms(phone=payload.phone, code=code)
    except Exception:
        # 발송 실패 시 쿨다운/일일 카운트를 되돌려 번호가 잠기지 않게 한다(P2 리뷰).
        await store.rollback_send(payload.phone)
        raise
    logger.info("phone_code_sent")  # 휴대폰/코드는 로깅하지 않는다(PII).
    return PhoneSendCodeResponse(expires_in_seconds=settings.phone_otp_ttl_seconds)


async def _resolve_anonymous_owner(request: Request) -> "uuid.UUID | None":
    """가입 요청에 익명 Supabase 토큰이 실려 있으면 그 소유자 id 를 검증해 반환한다.

    토큰으로 소유권을 증명한 경우에만 기존 익명 리드를 새 계정으로 이관한다(IDOR 방지).
    헤더가 없거나 영구/무효 토큰이면 None — 가입 흐름을 막지 않는다.
    """

    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    try:
        token = parse_bearer_token(authorization)
        async with httpx.AsyncClient(timeout=10.0) as http_client:
            principal = await verify_supabase_request_token(
                token, http_client=http_client
            )
    except ZippinException:
        return None
    return principal.user_id if principal.is_anonymous else None


@router.post("/phone/verify-code", response_model=PhoneVerifyResponse)
async def verify_phone_code(payload: PhoneVerifyRequest) -> PhoneVerifyResponse:
    store = get_phone_verification_store()
    token = await store.verify_code(payload.phone, payload.code)
    return PhoneVerifyResponse(phone_token=token)


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(payload: SignupRequest, request: Request) -> SignupResponse:
    store = get_phone_verification_store()
    token_phone = await store.consume_token(payload.phone_token)
    phone = assert_token_phone_match(token_phone, payload.phone)

    # 익명 세션이 실려 있으면(증명된 경우) 기존 익명 리드를 새 계정으로 이관한다.
    anon_user_id = await _resolve_anonymous_owner(request)

    # 중복 확인 + 계정 생성을 휴대폰 단위로 직렬화해 동시 가입 경합을 막는다(P2 리뷰).
    if not await store.acquire_signup_lock(phone):
        raise ZippinException(
            "이미 같은 번호로 가입이 진행 중입니다. 잠시 후 다시 시도해 주세요.",
            code="SIGNUP_IN_PROGRESS",
            http_status=409,
        )
    try:
        created = await supabase_admin.create_email_user(
            email=payload.email,
            password=payload.password,
            phone=payload.phone,
            display_name=payload.name,
        )
        await create_signup_profile(user_id=created.user_id, display_name=payload.name)
        if anon_user_id is not None and anon_user_id != created.user_id:
            moved = await leads_service.reassign_leads_owner(
                from_user_id=anon_user_id, to_user_id=created.user_id
            )
            logger.info(
                "signup_claimed_anonymous_leads",
                user_id=str(created.user_id),
                moved=moved,
            )
    finally:
        await store.release_signup_lock(phone)
    logger.info("email_signup_completed", user_id=str(created.user_id))
    return SignupResponse(user_id=str(created.user_id), email=payload.email)


@router.post("/find-email", response_model=FindEmailResponse)
async def find_email(payload: FindEmailRequest) -> FindEmailResponse:
    store = get_phone_verification_store()
    token_phone = await store.consume_token(payload.phone_token)
    assert_token_phone_match(token_phone, payload.phone)

    rows = await supabase_admin.find_emails_by_phone(payload.phone)
    return FindEmailResponse(
        emails=[
            FoundEmail(
                email_masked=_mask_email(row["email"]), created_at=row["created_at"]
            )
            for row in rows
        ]
    )


@router.post("/reset-password", response_model=ResetPasswordResponse)
async def reset_password(payload: ResetPasswordRequest) -> ResetPasswordResponse:
    store = get_phone_verification_store()
    token_phone = await store.consume_token(payload.phone_token)
    assert_token_phone_match(token_phone, payload.phone)

    user_id = await supabase_admin.find_user_id_by_email_and_phone(
        payload.email, payload.phone
    )
    if user_id is None:
        raise ZippinException(
            "입력하신 이메일과 휴대폰 번호가 일치하는 계정을 찾을 수 없습니다.",
            code="ACCOUNT_NOT_FOUND",
            http_status=404,
        )
    await supabase_admin.update_user_password(
        user_id=user_id, password=payload.new_password
    )
    logger.info("password_reset_completed", user_id=str(user_id))
    return ResetPasswordResponse()


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
    requester: RequestUser = Depends(require_supabase_request_user),
) -> ChangePasswordResponse:
    if requester.is_anonymous:
        raise ZippinException(
            "비밀번호 변경은 로그인한 회원만 가능합니다.",
            code="AUTH_ANONYMOUS_TOKEN_NOT_ALLOWED",
            http_status=403,
        )
    email = await supabase_admin.get_email_by_user_id(requester.user_id)
    if email is None:
        raise ZippinException(
            "이메일 계정이 아니어서 비밀번호를 변경할 수 없습니다.",
            code="ACCOUNT_NOT_EMAIL_USER",
            http_status=400,
        )
    if not await supabase_admin.verify_password(
        email=email, password=payload.current_password
    ):
        raise ZippinException(
            "현재 비밀번호가 일치하지 않습니다.",
            code="CURRENT_PASSWORD_MISMATCH",
            http_status=400,
        )
    await supabase_admin.update_user_password(
        user_id=requester.user_id, password=payload.new_password
    )
    logger.info("password_changed", user_id=str(requester.user_id))
    return ChangePasswordResponse()


@router.delete("/account", response_model=DeleteAccountResponse)
async def delete_account(
    request: Request,  # noqa: ARG001 - principal 의존성이 request.state 를 채운다.
    requester: RequestUser = Depends(require_supabase_request_user),
) -> DeleteAccountResponse:
    if requester.is_anonymous:
        raise ZippinException(
            "회원 탈퇴는 로그인한 회원만 가능합니다.",
            code="AUTH_ANONYMOUS_TOKEN_NOT_ALLOWED",
            http_status=403,
        )
    await supabase_admin.delete_user(user_id=requester.user_id)
    logger.info("account_deleted", user_id=str(requester.user_id))
    return DeleteAccountResponse()
