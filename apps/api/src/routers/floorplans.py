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
    # owner/session-folder 강제 + traversal 차단: object_key 는 정확히
    # `<user_id>/<session_id>/...` 로 시작해야 하고, '..'·빈 세그먼트를 포함하면 안 된다.
    # 첫 세그먼트만 보면 `<uid>/../<other>/f.png` 같은 키가 통과해 서명 단계에서 HTTP
    # 정규화로 다른 객체를 가리킬 수 있다(#path-traversal).
    expected_prefix = f"{requester.user_id}/{session_id}/"
    segments = payload.object_key.split("/")
    if (
        not payload.object_key.startswith(expected_prefix)
        or ".." in segments
        or "" in segments
    ):
        raise ZippinException(
            "object_key must be under your own user/session folder.",
            code="FLOORPLAN_ASSET_OWNER_MISMATCH",
            http_status=403,
        )
    # 엣지 검증: 세그멘테이션은 래스터 이미지를 분석하므로 image/* 만 받는다(AV 스캔
    # 전 최소 검증). PDF 등은 현재 미지원(#unblock-analysis 보강).
    if not payload.content_type.lower().startswith("image/"):
        raise ZippinException(
            "Only image/* floorplans are supported.",
            code="FLOORPLAN_ASSET_UNSUPPORTED_TYPE",
            http_status=422,
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
