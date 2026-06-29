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
from pydantic import BaseModel, Field

from ..auth.request_token import RequestUser, require_supabase_request_user
from ..config import get_settings
from ..errors import ZippinException
from ..logging import get_logger
from ..schemas.floorplans import (
    FloorplanAssetCreateRequest,
    FloorplanAssetResponse,
    FloorplanUploadCreateRequest,
    FloorplanUploadResponse,
)
from ..services import main_flow, storage

# 도면 업로드 상한(엣지 presign 정책과 일치). HEAD 로 검증한 실제 크기에 적용.
_MAX_FLOORPLAN_BYTES = 50 * 1024 * 1024

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
    settings = get_settings()
    # 버킷 경계: 세션 도면 버킷만 허용한다. 안 그러면 lead-floorplans 등 다른 비공개
    # 버킷의 객체를 자기 세션에 등록해 세그멘테이션이 서명·전달할 수 있다(#bucket-boundary).
    if payload.bucket != settings.session_floorplan_bucket:
        raise ZippinException(
            "Floorplan must be in the configured session bucket.",
            code="FLOORPLAN_ASSET_UNSUPPORTED_BUCKET",
            http_status=422,
        )
    # 빠른 거절: JSON content_type 이 image/* 가 아니면 즉시 막는다(아래 HEAD 검증 전).
    if not payload.content_type.lower().startswith("image/"):
        raise ZippinException(
            "Only image/* floorplans are supported.",
            code="FLOORPLAN_ASSET_UNSUPPORTED_TYPE",
            http_status=422,
        )
    # 저장된 객체 메타 검증: 클라이언트 JSON 은 신뢰 못 한다(presign 우회 가능). 실제
    # Storage 객체를 HEAD 해 content-type=image/* + 크기 상한을 확인하고, 검증값으로
    # 영속한다 — 비이미지/초과 페이로드가 pending 으로 분석에 들어가는 것 방지(#verify-object).
    meta = await storage.head_object(
        settings, bucket=payload.bucket, object_path=payload.object_key
    )
    if meta is None:
        raise ZippinException(
            "Could not verify the uploaded object.",
            code="FLOORPLAN_ASSET_UNVERIFIED",
            http_status=422,
        )
    verified_type, verified_size = meta
    if verified_type is None or not verified_type.lower().startswith("image/"):
        raise ZippinException(
            "Only image/* floorplans are supported.",
            code="FLOORPLAN_ASSET_UNSUPPORTED_TYPE",
            http_status=422,
        )
    if verified_size is not None and verified_size > _MAX_FLOORPLAN_BYTES:
        raise ZippinException(
            "Floorplan exceeds the maximum allowed size.",
            code="FLOORPLAN_ASSET_TOO_LARGE",
            http_status=422,
        )
    asset_payload = payload.model_dump()
    # 신뢰 가능한 검증값으로 덮어쓴다(클라이언트 주장 대신 실제 객체 메타).
    asset_payload["content_type"] = verified_type
    if verified_size is not None:
        asset_payload["byte_size"] = verified_size
    row = await main_flow.create_floorplan_asset(
        session_id=session_id,
        owner_user_id=requester.user_id,
        payload=asset_payload,
        owner_is_anonymous=requester.is_anonymous,
    )
    logger.info(
        "floorplan_asset_created",
        session_id=str(session_id),
        asset_id=str(row["id"]),
    )
    return FloorplanAssetResponse.model_validate(row)


class SignedUrlResponse(BaseModel):
    url: str


@router.get(
    "/{session_id}/floorplan-assets/{asset_id}/signed-url",
    response_model=SignedUrlResponse,
)
async def get_floorplan_asset_signed_url(
    session_id: uuid.UUID = Path(...),
    asset_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> SignedUrlResponse:
    """오버레이가 도면 이미지를 표시할 짧은-수명 서명 URL 을 발급한다(owner-gated).

    카드에 서명 URL 을 영속하면 만료(새로고침 시 깨짐)되므로, 카드는 asset_id 만 들고
    프론트가 렌더 시점에 본 엔드포인트로 신선한 URL 을 받는다. 세션의 선택된 도면
    asset 과 일치할 때만 서명한다(stale/타세션 참조 거절).
    """

    asset = await main_flow.get_selected_floorplan_asset(
        session_id=session_id,
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
    )
    if asset is None or str(asset["id"]) != str(asset_id):
        raise ZippinException(
            "Floorplan asset not found for this session.",
            code="FLOORPLAN_ASSET_NOT_FOUND",
            http_status=404,
        )
    settings = get_settings()
    signed = await storage.sign_object_url(
        settings,
        bucket=asset["bucket"],
        object_path=asset["object_key"],
        operation="sign_floorplan_display",
    )
    if not signed:
        raise ZippinException(
            "Could not sign the floorplan URL.",
            code="FLOORPLAN_SIGN_FAILED",
            http_status=502,
        )
    return SignedUrlResponse(url=signed)


class SelectedWallsRequest(BaseModel):
    # OVERLAY-002: 사용자가 클릭한 철거 희망 비내력벽 후보 region_id 목록. 빈 목록은
    # 선택 해제(전체)로 허용한다. 폭주 방지를 위해 상한을 둔다.
    region_ids: list[str] = Field(default_factory=list, max_length=500)


class SelectedWallsResponse(BaseModel):
    selected_walls: list[str]


@router.patch(
    "/{session_id}/selected-walls",
    response_model=SelectedWallsResponse,
)
async def update_selected_walls(
    payload: SelectedWallsRequest,
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> SelectedWallsResponse:
    """OVERLAY 가 수집한 철거 대상 벽 선택을 공통 판단 스키마에 기록한다(HITL).

    빈 문자열 제거 + 순서 보존 dedupe 후 ``judgment_schema.selected_walls`` 로 병합한다.
    LLM 을 거치지 않는 직접 UI 액션이라 REST 로 둔다(클릭마다 모델을 깨우지 않음).
    """

    seen: set[str] = set()
    clean: list[str] = []
    for rid in payload.region_ids:
        rid = rid.strip()
        if rid and rid not in seen:
            seen.add(rid)
            clean.append(rid)
    merged = await main_flow.merge_judgment_schema(
        session_id=session_id,
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
        patch={"selected_walls": clean},
    )
    walls = merged.get("selected_walls")
    return SelectedWallsResponse(
        selected_walls=walls if isinstance(walls, list) else clean
    )
