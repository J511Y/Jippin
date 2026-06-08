"""상담 리드(consultation leads) 라우터 (CMP-DIRECT).

비회원(Supabase Anonymous Sign-In)도 상담 신청을 할 수 있다는 요구사항에 따라
``POST /leads`` 는 ``require_supabase_request_user`` (익명 OK)를 쓴다. 이는 ADR-0004
§5.3 #11 / AGENTS §4.7 의 conversion-only(is_anonymous=false) 봉인을 사용자 결정으로
override 한 것이다.

``GET /leads/address/search`` 는 공공 도로명주소 데이터 프록시라 인증을 요구하지 않는다
(익명 세션 부트스트랩과 분리). 승인키는 서버측에만 둔다.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth.request_token import RequestUser, require_supabase_request_user
from ..logging import get_logger
from ..schemas.leads import (
    AddressSearchResponse,
    LeadCreateRequest,
    LeadResponse,
)
from ..services import leads as leads_service

logger = get_logger("zippin.leads")
router = APIRouter(prefix="/leads", tags=["leads"])


@router.post("", response_model=LeadResponse, status_code=201)
async def create_lead(
    payload: LeadCreateRequest,
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
    return LeadResponse.model_validate(row)


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
