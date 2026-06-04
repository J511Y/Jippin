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
    row = main_flow.create_session(
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


@router.get("/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> SessionResponse:
    row = main_flow.get_owned_session(
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
    row = main_flow.upsert_session_address(
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
