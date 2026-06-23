"""Pydantic contracts for Phase A 도면 후보/업로드 (CMP-609).

DB 정본은 ``docs/plans/main-feature-db-schema-v0.1.md`` 의 ``floorplan_uploads``
와 ``floorplan_candidates`` 다. ``floorplans`` catalog metadata 와
``floorplan_assets`` (R2/S3 object metadata) 의 실 CRUD 는 본 skeleton 범위
밖이다 — Phase A skeleton 은 "사용자 업로드 record 와 catalog 후보 snapshot
저장" 의 최소 contract 만 다룬다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FloorplanUploadStatus = Literal[
    "uploaded",
    "scan_pending",
    "scan_failed",
    "ready_for_processing",
    "processing",
    "processed",
    "rejected",
    "promoted_to_catalog",
]


class FloorplanUploadCreateRequest(BaseModel):
    """`POST /sessions/{id}/floorplan-uploads` body.

    ``original_asset_id`` 는 별도 asset 생성 API (Phase A skeleton 범위 밖) 후
    PATCH 로 채우는 흐름을 가정한다. skeleton 은 row 생성만 책임진다.
    """

    file_name: str | None = None
    source_note: str | None = None
    upload_metadata: dict[str, Any] = Field(default_factory=dict)


class FloorplanUploadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID
    original_asset_id: uuid.UUID | None
    status: FloorplanUploadStatus
    file_name: str | None
    source_note: str | None
    upload_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class FloorplanAssetCreateRequest(BaseModel):
    """`POST /sessions/{id}/floorplan-assets` body — 클라이언트가 presigned URL 로
    Storage 에 직접 PUT 한 뒤 객체 메타데이터만 등록한다(파일 바이너리 미전송).

    ``object_key`` 의 첫 경로 세그먼트는 owner user_id 여야 한다(라우터가 검증).
    """

    bucket: str = Field(min_length=1)
    object_key: str = Field(min_length=1)
    content_type: str = Field(min_length=1)
    byte_size: int = Field(ge=0)
    sha256_hex: str | None = None


class FloorplanAssetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID | None
    kind: str
    bucket: str
    object_key: str
    content_type: str
    byte_size: int
    scan_status: str


class FloorplanCandidateItemInput(BaseModel):
    """Single candidate inside a snapshot batch — **internal-only** contract.

    Public route was removed in round-2 (board P2-3); only the agent runtime /
    검색·매칭 서비스가 ``services.main_flow.save_floorplan_candidate_snapshot``
    를 호출한다. Caller 가 catalog FK 와 owner 를 직접 검증한다.

    ``floorplan_snapshot`` 은 사용자가 실제 본 후보 표시값 (display label,
    type/thumbnail, ranking metadata 등) 을 영구 보존하기 위해 **필수**이며 빈
    object 를 허용하지 않는다. 후속 ``floorplans`` catalog row 가 삭제되어
    ``floorplan_id`` 가 NULL 이 되어도 사용자가 본 후보 화면이 재현 가능해야
    하기 때문이다 (board round-3 #4 + DB ``floorplan_candidates.floorplan_snapshot``
    JSONB NOT NULL).
    """

    floorplan_id: uuid.UUID
    rank: int = Field(ge=1)
    confidence: Decimal = Field(ge=0, le=1)
    match_reasons: list[Any] = Field(default_factory=list)
    lookup_input: dict[str, Any] = Field(default_factory=dict)
    floorplan_snapshot: dict[str, Any] = Field(min_length=1)


class FloorplanCandidateSnapshotRequest(BaseModel):
    """`POST /sessions/{id}/floorplan-candidates` body.

    한 세션에서 주소/평형을 바꿔 후보를 재계산할 때마다 ``lookup_revision`` 을
    증가시켜 동일 ``(session_id, lookup_revision, floorplan_id)`` 가 겹치지
    않도록 한다. DB 단의 unique constraint 와 정합된다.
    """

    lookup_revision: int = Field(ge=1)
    items: list[FloorplanCandidateItemInput] = Field(min_length=1)


class FloorplanCandidateResponse(BaseModel):
    """DB-shaped ``floorplan_candidates`` row.

    ``floorplan_id`` 는 nullable 이다 — DB 는 ``ON DELETE SET NULL`` 로 catalog
    row 삭제 시 후보 snapshot 자체는 보존한다 (board round-3 #3). 사용자가 본
    후보 화면은 ``floorplan_snapshot`` 에 보존되므로 catalog 삭제 후에도 응답이
    가능하다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    lookup_revision: int
    floorplan_id: uuid.UUID | None
    rank: int
    confidence: Decimal
    match_reasons: list[Any]
    lookup_input: dict[str, Any]
    floorplan_snapshot: dict[str, Any]
    selected_at: datetime | None
    rejected_at: datetime | None
    created_at: datetime


class FloorplanCandidateSnapshotResponse(BaseModel):
    """Snapshot batch response — DB-shape rows in rank order."""

    session_id: uuid.UUID
    lookup_revision: int
    candidates: list[FloorplanCandidateResponse]
