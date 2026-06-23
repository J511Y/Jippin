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

from pydantic import BaseModel, ConfigDict, Field, model_validator

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


class SessionReportResponse(BaseModel):
    """`GET /sessions/{id}/report` — 세션에 영속된 룰 판정(rule-eval-result) 기반 리포트.

    ``rule_eval_result`` 는 rule-eval-result 계약 그대로의 객체(verdict/
    required_facilities/permit_required/legal_basis/user_message/evaluated_at 등)다.
    판정이 아직 없으면 본 응답 대신 404 REPORT_NOT_READY 가 나간다(라우터).

    법적 고지는 별도 필드로 내려보내지 않는다 — 리포트 화면이 봉인된
    ``<LegalNotice>``(AGENTS.md §4.6 정본 문구)를 직접 렌더한다(문구 중복/불일치 방지).
    """

    schema_version: Literal["1.0.0"] = "1.0.0"
    session_id: uuid.UUID
    status: SessionStatus
    rule_eval_result: dict[str, Any]
    evaluated_at: datetime | None
    address: SessionAddressResponse | None


class SessionResponse(BaseModel):
    """DB-shaped ``sessions`` row.

    Phase A DB 모델에 실제 존재하는 컬럼만 노출한다. ``is_anonymous_owner`` 처럼
    Supabase ``auth.users.is_anonymous`` 에서 derive 되는 값은 본 response 에
    포함하지 않는다 — DB row 에 없는 속성을 ``from_attributes=True`` 로 직접
    읽으면 ORM-backed repo 로 swap 시 검증 실패가 난다 (board round-3 #1).
    Anonymous owner 여부는 클라이언트가 자신의 Supabase 토큰에서 직접 확인하거나
    ``expires_at`` 의 존재로 판단할 수 있다 — 익명 owner 세션은 TTL 정책에 따라
    ``expires_at`` 이 설정되고, permanent owner 는 ``None`` 이다.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    status: SessionStatus
    address_id: uuid.UUID | None
    selected_floorplan_id: uuid.UUID | None
    selected_floorplan_upload_id: uuid.UUID | None
    selected_floorplan_asset_id: uuid.UUID | None
    judgment_schema: dict[str, Any]
    judgment_schema_version: str | None
    completion_decision: str | None
    # 리포트 준비 신호 — verdict(rule_eval_result) 영속 여부로만 판정한다. 클라이언트는
    # 이 값으로 리포트 단계 완료를 표시해야 한다(completion_decision 은 ASK_MORE 등에도
    # 채워져 report-ready 와 무관하므로 쓰면 안 됨, #report-readiness).
    has_report: bool = False
    last_activity_at: datetime
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="before")
    @classmethod
    def _derive_has_report(cls, data: Any) -> Any:
        # 세션 row dict 의 rule_eval_result 존재로 has_report 를 파생한다(main_flow 는
        # 항상 dict 를 넘긴다). dict 가 아니면 기본 False 로 둔다.
        if isinstance(data, dict) and "has_report" not in data:
            return {**data, "has_report": data.get("rule_eval_result") is not None}
        return data
