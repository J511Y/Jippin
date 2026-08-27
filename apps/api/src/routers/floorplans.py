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
    # 창호(발코니-실 경계 창호 철거 검토) 선택 — None 이면 기존 선택을 건드리지 않는다
    # (하위호환: 구 클라이언트는 이 필드를 보내지 않는다). 빈 목록은 선택 해제.
    window_region_ids: list[str] | None = Field(default=None, max_length=500)
    # 이 선택이 유래한 오버레이 카드의 도면 asset — 도면이 **교체**된 뒤 옛 카드가
    # 제출되면 거절하기 위한 지문(#overlay-asset-fingerprint). region id 는 도면이
    # 달라도 재사용되므로(pred:N) id 존재 검증만으로는 다른 도면의 벽이 선택될 수
    # 있다. None 이면 검사 생략(하위호환: asset_id 없는 옛 카드/클라이언트).
    asset_id: uuid.UUID | None = None


class SelectedWallsResponse(BaseModel):
    selected_walls: list[str]
    selected_windows: list[str] = Field(default_factory=list)


def _dedupe_region_ids(region_ids: list[str]) -> list[str]:
    """빈 문자열 제거 + 순서 보존 dedupe."""

    seen: set[str] = set()
    clean: list[str] = []
    for rid in region_ids:
        rid = rid.strip()
        if rid and rid not in seen:
            seen.add(rid)
            clean.append(rid)
    return clean


@router.patch(
    "/{session_id}/selected-walls",
    response_model=SelectedWallsResponse,
)
async def update_selected_walls(
    payload: SelectedWallsRequest,
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> SelectedWallsResponse:
    """OVERLAY 가 수집한 철거 대상 벽·창호 선택을 공통 판단 스키마에 기록한다(HITL).

    빈 문자열 제거 + 순서 보존 dedupe 후 ``judgment_schema.selected_walls``(벽) /
    ``selected_windows``(창호) 로 병합한다. LLM 을 거치지 않는 직접 UI 액션이라 REST 로
    둔다(클릭마다 모델을 깨우지 않음). 창호의 철거 가부(외기 접촉 vs 발코니-실 경계)는
    여기서 판정하지 않는다 — 에이전트(CHAT)가 window_demolition_boundary 로 판단한다.

    선택 id 는 **최신 분석 산출**(wall_objects/window_objects)과 대조해, 존재하지 않거나
    선택 불가(내력벽)인 id 가 섞이면 409(SELECTION_STALE)로 거절한다 — 재분석 이전의
    옛 오버레이 카드 제출이 프루닝된 id 를 되살리는 경로 차단(#stale-overlay-submission).

    ``asset_id`` 가 오면 **현재 선택 도면**과도 대조해, 다르면
    409(ANALYSIS_INPUT_STALE)로 거절한다 — region id 는 다른 도면에서도 재사용되므로
    (pred:N), 도면 교체 뒤 옛 카드의 제출이 id 존재 검증을 우연히 통과해 **다른
    도면의 벽**을 선택하는 경로 차단(#overlay-asset-fingerprint).
    """

    clean_walls = _dedupe_region_ids(payload.region_ids)
    clean_windows = (
        _dedupe_region_ids(payload.window_region_ids)
        if payload.window_region_ids is not None
        else None
    )
    patch: dict[str, list[str]] = {"selected_walls": clean_walls}
    if clean_windows is not None:
        patch["selected_windows"] = clean_windows
    # 최신 분석 산출과의 대조 검증(#stale-overlay-submission)은 merge 가 **행잠금
    # 트랜잭션 안에서** 수행한다(validate_selection) — 라우트에서 스냅숏으로 검증하면
    # 그 읽기와 영속 사이에 재분석 커밋이 끼어 옛 id 가 새 객체 옆에 살아남는 TOCTOU
    # 창이 생긴다. 어긋나면 409 SELECTION_STALE(세션 무변경), 빈 목록(선택 해제)은
    # 검증 대상이 없다. 카드의 asset 지문도 같은 행잠금에서 검사한다
    # (#overlay-asset-fingerprint).
    merged = await main_flow.merge_judgment_schema(
        session_id=session_id,
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
        patch=patch,
        validate_selection=True,
        **({"expected_asset_id": payload.asset_id} if payload.asset_id else {}),
    )
    walls = merged.get("selected_walls")
    windows = merged.get("selected_windows")
    return SelectedWallsResponse(
        selected_walls=walls if isinstance(walls, list) else clean_walls,
        selected_windows=(
            windows if isinstance(windows, list) else patch.get("selected_windows", [])
        ),
    )
