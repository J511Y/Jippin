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


class FloorplanCandidateItemInput(BaseModel):
    """Single candidate inside a snapshot batch.

    Phase A skeleton 은 후보 catalog (``floorplans`` table) 의 사전 존재를
    검증하지 않는다 — caller (검색/매칭 서비스) 가 floorplan_id 가
    유효한지 보장한다. 실 FK enforcement 는 migration PR 에서 들어온다.
    """

    floorplan_id: uuid.UUID
    rank: int = Field(ge=1)
    confidence: Decimal = Field(ge=0, le=1)
    match_reasons: list[Any] = Field(default_factory=list)
    lookup_input: dict[str, Any] = Field(default_factory=dict)


class FloorplanCandidateSnapshotRequest(BaseModel):
    """`POST /sessions/{id}/floorplan-candidates` body.

    한 세션에서 주소/평형을 바꿔 후보를 재계산할 때마다 ``lookup_revision`` 을
    증가시켜 동일 ``(session_id, lookup_revision, floorplan_id)`` 가 겹치지
    않도록 한다. DB 단의 unique constraint 와 정합된다.
    """

    lookup_revision: int = Field(ge=1)
    items: list[FloorplanCandidateItemInput] = Field(min_length=1)


class FloorplanCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    lookup_revision: int
    floorplan_id: uuid.UUID
    rank: int
    confidence: Decimal
    match_reasons: list[Any]
    lookup_input: dict[str, Any]
    selected_at: datetime | None
    rejected_at: datetime | None
    created_at: datetime


class FloorplanCandidateSnapshotResponse(BaseModel):
    """Snapshot batch response — DB-shape rows in rank order."""

    session_id: uuid.UUID
    lookup_revision: int
    candidates: list[FloorplanCandidateResponse]
