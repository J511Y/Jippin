"""Phase A 도면 업로드 라우터 skeleton (CMP-609).

공개 엔드포인트:

- ``POST /sessions/{id}/floorplan-uploads`` → 사용자 업로드 metadata row 생성

후보 snapshot 저장 (``floorplan_candidates``) 은 사용자-facing route 가 아니다.
백엔드 검색/매칭 서비스 (Phase B agent runtime) 가
``services.main_flow.save_floorplan_candidate_snapshot`` 을 직접 호출한다 —
board P2-3: 사용자가 catalog 후보를 임의로 persist 하지 못하게 막는다.

자세한 contract 는 ``schemas/floorplans.py`` 와 ``services/main_flow.py`` 참조.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path

from ..auth.request_token import RequestUser, require_supabase_request_user
from ..errors import ZippinException
from ..logging import get_logger
from ..schemas.floorplans import (
    FloorplanAssetCreateRequest,
    FloorplanAssetResponse,
    FloorplanUploadCreateRequest,
    FloorplanUploadResponse,
)
from ..services import main_flow

logger = get_logger("zippin.floorplans")
router = APIRouter(prefix="/sessions", tags=["floorplans"])


@router.post(
    "/{session_id}/floorplan-uploads",
    response_model=FloorplanUploadResponse,
    status_code=201,
)
async def create_floorplan_upload(
    payload: FloorplanUploadCreateRequest,
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> FloorplanUploadResponse:
    row = await main_flow.create_floorplan_upload(
        session_id=session_id,
        owner_user_id=requester.user_id,
        payload=payload.model_dump(),
        owner_is_anonymous=requester.is_anonymous,
    )
    logger.info(
        "floorplan_upload_created",
        session_id=str(session_id),
        upload_id=str(row["id"]),
    )
    return FloorplanUploadResponse.model_validate(row)


@router.post(
    "/{session_id}/floorplan-assets",
    response_model=FloorplanAssetResponse,
    status_code=201,
)
async def create_floorplan_asset(
    payload: FloorplanAssetCreateRequest,
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> FloorplanAssetResponse:
    # owner-folder 강제: object_key 의 첫 세그먼트(=업로드 시 부여한 user 폴더)가
    # 요청자 user_id 와 일치해야 한다 — 남의 폴더 객체를 자기 세션에 붙이지 못하게.
    owner_segment = payload.object_key.split("/", 1)[0]
    if owner_segment != str(requester.user_id):
        raise ZippinException(
            "object_key must be under your own user folder.",
            code="FLOORPLAN_ASSET_OWNER_MISMATCH",
            http_status=403,
        )
    row = await main_flow.create_floorplan_asset(
        session_id=session_id,
        owner_user_id=requester.user_id,
        payload=payload.model_dump(),
        owner_is_anonymous=requester.is_anonymous,
    )
    logger.info(
        "floorplan_asset_created",
        session_id=str(session_id),
        asset_id=str(row["id"]),
    )
    return FloorplanAssetResponse.model_validate(row)
