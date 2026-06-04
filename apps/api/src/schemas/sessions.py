"""Pydantic contracts for Phase A 사전검토 세션/주소 (CMP-609).

DB 정본은 ``docs/plans/main-feature-db-schema-v0.1.md`` 의 Phase A 섹션
(``sessions``, ``session_addresses``) 이다. 본 스키마는 skeleton API 가
나중에 들어올 실 migration 과 충돌 없이 동작하도록 컬럼 이름을 그대로
사용한다. masking/PII redaction 정책은 별도 이슈에서 처리한다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SessionStatus = Literal[
    "draft",
    "address_ready",
    "floorplan_selected",
    "analyzing",
    "awaiting_overlay",
    "collecting_info",
    "ready_for_rule",
    "report_ready",
    "handoff",
    "expired",
    "deleted",
]


class SessionCreateRequest(BaseModel):
    """`POST /sessions` body.

    Skeleton 단계에서는 사용자가 명시할 만한 입력이 없으므로 빈 객체를 허용한다.
    추후 client 가 ``judgment_schema_version`` 을 지정하는 흐름이 생기면
    여기로 들어온다.
    """

    judgment_schema_version: str | None = Field(default=None)


class SessionAddressInput(BaseModel):
    """`PUT /sessions/{id}/address` body — `session_addresses` row 본문.

    모든 필드가 optional 이지만 partial upsert 시멘틱이 다르다 — 라우터는
    ``model_dump(exclude_unset=True)`` 를 써서 client 가 명시한 key 만 service
    레이어로 넘긴다. 두 번째 upsert 가 ``unit_ho`` 만 보내도 이미 저장된
    ``road_address`` 가 ``None`` 으로 덮이지 않는다 (board P2-1 회귀 가드).
    """

    road_address: str | None = None
    jibun_address: str | None = None
    apartment_name: str | None = None
    building_dong: str | None = None
    unit_ho: str | None = None
    floor_no: int | None = None
    exclusive_area_m2: Decimal | None = None
    size_type: str | None = None
    building_identity: dict[str, Any] | None = None
    address_provider: str | None = None


class SessionAddressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID
    road_address: str | None
    jibun_address: str | None
    apartment_name: str | None
    building_dong: str | None
    unit_ho: str | None
    floor_no: int | None
    exclusive_area_m2: Decimal | None
    size_type: str | None
    building_identity: dict[str, Any]
    address_provider: str | None
    normalized_at: datetime | None
    created_at: datetime


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    is_anonymous_owner: bool = Field(
        description=(
            "True 면 owner 가 Supabase Anonymous Sign-In 으로 만든 임시 사용자다."
            " conversion-only API (lead/report share) 에서는 차단되어야 한다."
        )
    )
    status: SessionStatus
    address_id: uuid.UUID | None
    selected_floorplan_id: uuid.UUID | None
    selected_floorplan_upload_id: uuid.UUID | None
    selected_floorplan_asset_id: uuid.UUID | None
    judgment_schema: dict[str, Any]
    judgment_schema_version: str | None
    completion_decision: str | None
    last_activity_at: datetime
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime
