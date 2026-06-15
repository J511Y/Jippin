"""우리집 체크(home-check) Pydantic 계약 (ADR-0008).

응답 정본 shape 는 ``packages/contracts/schemas/home-check.schema.json`` (생성 모델
``zippin_contracts.home_check``)다. 다만 런타임 이미지(``apps/api/Dockerfile``)는 ``src`` 만
복사하고 ``packages/contracts/python`` 을 포함하지 않으므로(rule_engine 과 동일 정책),
런타임 src 는 ``zippin_contracts`` 를 import 하지 않는다. 대신 동일 shape 를 여기에 정의하고,
**테스트가 응답 payload 를 ``zippin_contracts`` 로 검증**해 계약 일치를 보장한다.

요청 본문(HomeCheckCreateRequest/ContinueRequest)과 응답(HomeCheckJob 외)을 모두 둔다.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# 익명 제출도 허용되므로 무제한 입력으로 자원을 소모하지 못하게 상한을 둔다(leads 와 동일 정책).
_MAX_ADDR_LEN = 255
_MAX_DONG_HO_LEN = 50
_MAX_SECURE_NO_LEN = 50

Status = Literal["pending", "querying", "needs_input", "completed", "failed"]
Signal = Literal["violation", "caution", "normal"]
Kind = Literal["dong_ho", "secure_no"]
Source = Literal["exclusive", "heading"]
DocKind = Literal["exclusive_part", "building_heading"]


# ---------------------------------------------------------------------------
# 요청 본문
# ---------------------------------------------------------------------------
class HomeCheckCreateRequest(BaseModel):
    """``POST /home-check`` 요청 본문 — 도로명주소(건물 단위) + 동/호."""

    road_addr: str = Field(min_length=1, max_length=_MAX_ADDR_LEN)
    jibun_addr: str | None = Field(default=None, max_length=_MAX_ADDR_LEN)
    dong: str = Field(default="", max_length=_MAX_DONG_HO_LEN)
    ho: str = Field(min_length=1, max_length=_MAX_DONG_HO_LEN)

    @field_validator("road_addr", "ho", mode="before")
    @classmethod
    def _strip_required(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("dong", mode="before")
    @classmethod
    def _strip_dong(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        if value is None:
            return ""
        return value


class HomeCheckContinueRequest(BaseModel):
    """``POST /home-check/{id}/continue`` 요청 본문 — needs_input 재개 입력."""

    dong: str | None = Field(default=None, max_length=_MAX_DONG_HO_LEN)
    ho: str | None = Field(default=None, max_length=_MAX_DONG_HO_LEN)
    secure_no: str | None = Field(default=None, max_length=_MAX_SECURE_NO_LEN)

    @field_validator("dong", "ho", "secure_no", mode="before")
    @classmethod
    def _strip_optional(cls, value: object) -> object:
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


# ---------------------------------------------------------------------------
# 응답 모델 — zippin_contracts.home_check 와 1:1 shape (extra="forbid").
# ---------------------------------------------------------------------------
class ErrorInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class NeedsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Kind
    message: str


class Violation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_violation: bool
    exclusive: bool | None = None
    heading: bool | None = None
    raw: str | None = None


class AddressInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    road_addr: str | None = None
    jibun_addr: str | None = None
    dong: str | None = None
    ho: str | None = None


class ExclusivePart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_m2: float | None = None
    use_type: str | None = None
    structure: str | None = None
    floor: str | None = None


class BuildingHeading(BaseModel):
    model_config = ConfigDict(extra="forbid")

    main_use: str | None = None
    floors: str | None = None
    approval_date: str | None = None
    permit_date: str | None = None
    comm_unique_no: str | None = None


class ChangeEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date: str | None = None
    reason: str
    source: Source


class PriceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference_date: str | None = None
    base_price: int | None = None


class DocumentRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: DocKind
    url: str | None = None


class ReportMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comm_unique_no: str | None = None
    res_doc_no: str | None = None
    issue_date: str | None = None
    issue_org: str | None = None
    queried_at: str | None = None


class HomeCheckReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal: Signal
    violation: Violation
    address: AddressInfo
    exclusive_part: ExclusivePart | None = None
    building: BuildingHeading | None = None
    change_history: list[ChangeEntry] | None = None
    prices: list[PriceEntry] | None = None
    documents: list[DocumentRef] | None = None
    caution_reasons: list[str] | None = None
    meta: ReportMeta | None = None
    disclaimer: str


class HomeCheckJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = Field(default="1.0.0", pattern=r"^\d+\.\d+\.\d+$")
    id: str
    status: Status
    signal: Signal | None = None
    created_at: str | None = None
    updated_at: str | None = None
    error: ErrorInfo | None = None
    needs_input: NeedsInput | None = None
    report: HomeCheckReport | None = None


class MyHomeChecksResponse(BaseModel):
    """``GET /home-check/mine`` 응답 — 본인 우리집 체크 이력 목록."""

    items: list[HomeCheckJob]
