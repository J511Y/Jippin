"""상담 리드(consultation leads) 라우터 (CMP-DIRECT).

비회원(Supabase Anonymous Sign-In)도 상담 신청을 할 수 있다는 요구사항에 따라
``POST /leads`` 는 ``require_supabase_request_user`` (익명 OK)를 쓴다. 이는 ADR-0004
§5.3 #11 / AGENTS §4.7 의 conversion-only(is_anonymous=false) 봉인을 사용자 결정으로
override 한 것이다.

``GET /leads/address/search`` 는 공공 도로명주소 데이터 프록시라 인증을 요구하지 않는다
(익명 세션 부트스트랩과 분리). 승인키는 서버측에만 둔다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from ..auth.request_token import (
    RequestUser,
    require_supabase_admin_user,
    require_supabase_request_user,
)
from ..errors import ZippinException
from ..logging import get_logger
from ..schemas.leads import (
    AddressSearchResponse,
    AssigneeNotificationRequest,
    AssigneeNotificationResponse,
    LeadCreateRequest,
    LeadResponse,
    MyLeadsResponse,
)
from ..services import alimtalk as alimtalk_service
from ..services import leads as leads_service

logger = get_logger("zippin.leads")
router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("", response_model=LeadResponse, status_code=201)
async def create_lead(
    payload: LeadCreateRequest,
    background_tasks: BackgroundTasks,
    requester: RequestUser = Depends(require_supabase_request_user),
) -> LeadResponse:
    row = await leads_service.create_lead(
        user_id=requester.user_id,
        is_anonymous=requester.is_anonymous,
        payload=payload.model_dump(),
    )
    # PII(이름/연락처/주소/내용)는 로깅하지 않는다.
    logger.info(
        "lead_created",
        lead_id=str(row["id"]),
        source_form=row["source_form"],
        is_anonymous=requester.is_anonymous,
        attachment_count=len(payload.attachments),
    )
    # 접수 알림톡은 응답 이후 best-effort 로 발송한다 — 미설정/실패해도 신청은 이미 성공이다.
    background_tasks.add_task(
        alimtalk_service.notify_lead_received,
        phone=payload.applicant_phone,
        applicant_name=payload.applicant_name,
        source_form=payload.source_form,
    )
    return LeadResponse.model_validate(row)


@router.post(
    "/{lead_id}/assignee-notification",
    response_model=AssigneeNotificationResponse,
    status_code=202,
)
async def notify_assignee_assigned(
    lead_id: uuid.UUID,
    payload: AssigneeNotificationRequest,
    admin: RequestUser = Depends(require_supabase_admin_user),
) -> AssigneeNotificationResponse:
    """담당자 배정 알림톡 발송 — 관리자 콘솔(apps/admin)의 배정 액션 전용.

    배정 자체(assigned_admin_id 갱신)는 관리자 앱이 service_role 로 직접 수행하고,
    본 엔드포인트는 알림톡 발송만 담당한다(SOLAPI 자격증명은 backend 단독 보유).
    발송 실패는 ``ZippinException`` 으로 그대로 전파해 관리자에게 결과를 알린다.
    """

    contact = await leads_service.get_lead_contact(lead_id=lead_id)
    if contact is None:
        raise ZippinException(
            "상담 리드를 찾을 수 없습니다.",
            code="LEAD_NOT_FOUND",
            http_status=404,
        )
    await alimtalk_service.send_assignee_assigned_alimtalk(
        phone=contact["applicant_phone"],
        applicant_name=contact["applicant_name"],
        assignee_name=payload.assignee_name,
    )
    # PII(고객명/연락처)는 로깅하지 않는다 — lead_id 와 발송자만 남긴다.
    logger.info(
        "lead_assignee_alimtalk_sent",
        lead_id=str(lead_id),
        admin_user_id=str(admin.user_id),
    )
    return AssigneeNotificationResponse(sent=True)


@router.get("/mine", response_model=MyLeadsResponse)
async def list_my_leads(
    requester: RequestUser = Depends(require_supabase_request_user),
) -> MyLeadsResponse:
    """마이페이지 상담 현황 — 로그인한 회원 본인의 리드만 반환한다."""
    if requester.is_anonymous:
        raise ZippinException(
            "상담 현황 조회는 로그인한 회원만 가능합니다.",
            code="AUTH_ANONYMOUS_TOKEN_NOT_ALLOWED",
            http_status=403,
        )
    rows = await leads_service.list_leads_for_user(user_id=requester.user_id)
    return MyLeadsResponse.model_validate({"items": rows})


@router.get("/address/search", response_model=AddressSearchResponse)
async def search_addresses(
    keyword: str = Query(..., min_length=1),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1, le=100),
) -> AddressSearchResponse:
    result = await leads_service.search_addresses(
        keyword=keyword,
        page=page,
        per_page=per_page,
    )
    return AddressSearchResponse.model_validate(result)
