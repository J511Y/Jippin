"""Phase A 사전검토 세션/주소 라우터 skeleton (CMP-609).

비회원 사전검토는 Supabase Anonymous Sign-In 토큰으로 진입하므로 본 라우터의
모든 엔드포인트는 ``require_supabase_request_user`` (anonymous OK) 를 쓴다.
``user_id`` 는 Supabase ``sub`` 클레임 (= ``auth.users.id``) 에서 직접 온다.
legacy ``x-jippin-anon-id`` 헤더는 받지 않는다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path

from ..auth.request_token import RequestUser, require_supabase_request_user
from ..logging import get_logger
from ..schemas.sessions import (
    SessionAddressInput,
    SessionAddressResponse,
    SessionCreateRequest,
    SessionReportResponse,
    SessionResponse,
)
from ..services import main_flow

logger = get_logger("zippin.sessions")
router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionResponse, status_code=201)
async def create_session(
    payload: SessionCreateRequest,
    requester: RequestUser = Depends(require_supabase_request_user),
) -> SessionResponse:
    row = await main_flow.create_session(
        user_id=requester.user_id,
        is_anonymous_owner=requester.is_anonymous,
        judgment_schema_version=payload.judgment_schema_version,
    )
    logger.info(
        "session_created",
        session_id=str(row["id"]),
        is_anonymous_owner=requester.is_anonymous,
    )
    return SessionResponse.model_validate(row)


@router.get("", response_model=list[SessionResponse])
async def list_sessions(
    requester: RequestUser = Depends(require_supabase_request_user),
) -> list[SessionResponse]:
    # 본인 소유 세션만 최신 활동순으로(목록 화면 복원용).
    rows = await main_flow.list_owned_sessions(
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
    )
    return [SessionResponse.model_validate(row) for row in rows]


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> SessionResponse:
    row = await main_flow.get_owned_session(
        session_id,
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
    )
    return SessionResponse.model_validate(row)


@router.put(
    "/{session_id}/address",
    response_model=SessionAddressResponse,
    status_code=200,
)
async def upsert_session_address(
    payload: SessionAddressInput,
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> SessionAddressResponse:
    # ``exclude_unset=True`` 로 client 가 명시한 key 만 service 단으로 넘겨
    # partial upsert 가 기존 ``session_addresses`` row 의 값을 ``None`` 으로
    # 덮어쓰지 않게 한다 (board P2-1).
    row = await main_flow.upsert_session_address(
        session_id=session_id,
        owner_user_id=requester.user_id,
        payload=payload.model_dump(exclude_unset=True),
        owner_is_anonymous=requester.is_anonymous,
    )
    logger.info(
        "session_address_upserted",
        session_id=str(session_id),
        address_id=str(row["id"]),
    )
    return SessionAddressResponse.model_validate(row)


@router.get("/{session_id}/report", response_model=SessionReportResponse)
async def get_session_report(
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> SessionReportResponse:
    # 리포트 정본은 sessions.rule_eval_result(에이전트 evaluate_rules 영속). 없으면
    # main_flow 가 404 REPORT_NOT_READY 를 던진다 — 가짜 판정을 만들지 않는다.
    data = await main_flow.get_session_report(
        session_id=session_id,
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
    )
    session = data["session"]
    address = data["address"]
    return SessionReportResponse(
        session_id=session["id"],
        status=session["status"],
        rule_eval_result=session["rule_eval_result"],
        evaluated_at=session.get("rule_evaluated_at"),
        address=(
            SessionAddressResponse.model_validate(address)
            if address is not None
            else None
        ),
    )
