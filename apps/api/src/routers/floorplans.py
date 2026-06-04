"""Phase A 도면 후보/업로드 라우터 skeleton (CMP-609).

엔드포인트는 ``/sessions/{session_id}`` 아래에 둔다:

- ``POST /sessions/{id}/floorplan-uploads`` → 사용자 업로드 metadata row 생성
- ``POST /sessions/{id}/floorplan-candidates`` → catalog 후보 snapshot 저장

자세한 contract 는 ``schemas/floorplans.py`` 와 ``services/main_flow.py`` 참조.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path

from ..auth.request_token import RequestUser, require_supabase_request_user
from ..logging import get_logger
from ..schemas.floorplans import (
    FloorplanCandidateResponse,
    FloorplanCandidateSnapshotRequest,
    FloorplanCandidateSnapshotResponse,
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
    row = main_flow.create_floorplan_upload(
        session_id=session_id,
        owner_user_id=requester.user_id,
        payload=payload.model_dump(),
    )
    logger.info(
        "floorplan_upload_created",
        session_id=str(session_id),
        upload_id=str(row["id"]),
    )
    return FloorplanUploadResponse.model_validate(row)


@router.post(
    "/{session_id}/floorplan-candidates",
    response_model=FloorplanCandidateSnapshotResponse,
    status_code=201,
)
async def save_floorplan_candidate_snapshot(
    payload: FloorplanCandidateSnapshotRequest,
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> FloorplanCandidateSnapshotResponse:
    rows = main_flow.save_floorplan_candidate_snapshot(
        session_id=session_id,
        owner_user_id=requester.user_id,
        lookup_revision=payload.lookup_revision,
        items=[item.model_dump() for item in payload.items],
    )
    logger.info(
        "floorplan_candidate_snapshot_saved",
        session_id=str(session_id),
        lookup_revision=payload.lookup_revision,
        candidate_count=len(rows),
    )
    return FloorplanCandidateSnapshotResponse(
        session_id=session_id,
        lookup_revision=payload.lookup_revision,
        candidates=[FloorplanCandidateResponse.model_validate(r) for r in rows],
    )
