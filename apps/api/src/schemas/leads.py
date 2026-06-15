"""상담 리드(consultation leads) Pydantic 계약 (CMP-DIRECT).

DB 정본은 ``supabase/migrations/..._0009_consultation_leads.sql`` 의
``consultation_leads`` / ``consultation_lead_attachments`` 다.

두 진입점:

- 메인페이지 간소화 폼(``source_form='main_page'``): 신청 구분 / 이름 / 연락처 /
  상담 내용만 필수.
- 상담 신청 페이지 전체 폼(``source_form='lead_page'``): 위 + 도로명 주소(part1/
  detail) + 확장 위치 + 상태 구분이 필수, 그 외(공사 기간 / 유입경로 / 첨부)는 optional.

조건부 필수는 ``model_validator`` 로 강제하며, DB 의 ``ck_consultation_leads_full_form_required``
CHECK 제약과 정합한다(이중 방어).
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SourceForm = Literal["main_page", "lead_page", "property_check"]
ApplicantKind = Literal["individual", "company"]
OwnershipStatus = Literal["in_transaction", "owner"]
InflowSource = Literal["naver_search", "blog", "acquaintance", "cafe", "etc"]
LeadStatus = Literal["new", "contacted", "in_progress", "closed", "spam"]

# 한국 휴대폰(010/011/016/017/018/019) 또는 일반 전화(0으로 시작, 9~11자리). 입력에서
# 공백/하이픈/점/괄호는 제거 후 검증한다. 프론트(`lib/leads/validation.ts`)와 동일 규칙.
_PHONE_NON_DIGIT_RE = re.compile(r"[^\d]")
_MOBILE_RE = re.compile(r"^01[016789]\d{7,8}$")
_GENERAL_PHONE_RE = re.compile(r"^0\d{8,10}$")


def normalize_korean_phone(raw: str) -> str:
    """연락처를 정규화한다. 유효하지 않으면 ``ValueError``.

    휴대폰은 ``010-1234-5678`` 형태로 하이픈 정규화하고, 그 외 번호는 숫자만 보존한다.
    """

    digits = _PHONE_NON_DIGIT_RE.sub("", raw or "")
    if _MOBILE_RE.match(digits):
        if len(digits) == 11:
            return f"{digits[:3]}-{digits[3:7]}-{digits[7:]}"
        # 10자리 휴대폰(예: 011-XXX-XXXX).
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    if _GENERAL_PHONE_RE.match(digits):
        return digits
    raise ValueError(
        "연락처 형식이 올바르지 않습니다. 휴대폰(010-1234-5678) 또는 "
        "지역번호 포함 전화번호를 입력해 주세요."
    )


# 익명 제출도 허용되므로 무제한 입력으로 DB/처리 자원을 소모하지 못하게 상한을 둔다.
_MAX_MESSAGE_LEN = 5000
_MAX_TEXT_LEN = 255
_MAX_ATTACHMENTS = 5


class LeadAttachmentInput(BaseModel):
    """리드 첨부 한 건 — 프론트가 Supabase Storage 업로드 후 넘기는 object metadata."""

    object_path: str = Field(min_length=1, max_length=1024)
    bucket: str | None = Field(default=None, max_length=255)
    file_name: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=255)
    byte_size: int | None = Field(default=None, ge=0)


class LeadCreateRequest(BaseModel):
    """``POST /leads`` 요청 본문.

    ``source_form`` 으로 간소화/전체 폼을 구분한다. 전체 폼 조건부 필수는
    ``model_validator`` 가 강제한다.
    """

    source_form: SourceForm
    applicant_kind: ApplicantKind = "individual"
    applicant_name: str = Field(min_length=1, max_length=100)
    applicant_phone: str = Field(min_length=1, max_length=40)
    road_addr_part1: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    road_addr_part2: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    road_addr_detail: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    expansion_location: str | None = Field(default=None, max_length=_MAX_TEXT_LEN)
    ownership_status: OwnershipStatus | None = None
    construction_start_date: date | None = None
    construction_end_date: date | None = None
    inflow_source: InflowSource | None = None
    message: str | None = Field(default=None, max_length=_MAX_MESSAGE_LEN)
    # 우리집 체크(home-check) 인입이면 원천 잡 id — 생성 후 home_checks.consultation_lead_id
    # 를 채워 귀속을 연결한다(ADR-0008). 그 외 신청은 None.
    home_check_id: uuid.UUID | None = None
    attachments: list[LeadAttachmentInput] = Field(
        default_factory=list, max_length=_MAX_ATTACHMENTS
    )

    @field_validator("applicant_name", "applicant_phone", mode="before")
    @classmethod
    def _strip_required_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("applicant_phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return normalize_korean_phone(value)

    @model_validator(mode="after")
    def _validate_form_completeness(self) -> "LeadCreateRequest":
        if self.source_form == "lead_page":
            missing: list[str] = []
            if not (self.road_addr_part1 or "").strip():
                missing.append("road_addr_part1")
            if not (self.road_addr_detail or "").strip():
                missing.append("road_addr_detail")
            if not (self.expansion_location or "").strip():
                missing.append("expansion_location")
            if self.ownership_status is None:
                missing.append("ownership_status")
            if missing:
                raise ValueError(
                    "상담 신청 전체 폼에는 다음 항목이 필수입니다: "
                    + ", ".join(missing)
                )
        if (
            self.construction_start_date is not None
            and self.construction_end_date is not None
            and self.construction_end_date < self.construction_start_date
        ):
            raise ValueError("공사 종료일은 시작일보다 빠를 수 없습니다.")
        return self


class LeadResponse(BaseModel):
    """제출 확인용 최소 응답 — PII 는 반환하지 않는다."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_form: SourceForm
    status: LeadStatus
    created_at: datetime


class MyLeadItem(BaseModel):
    """마이페이지 상담 현황 한 건 — 본인 리드만 반환한다(타인 PII 노출 없음)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_form: SourceForm
    status: LeadStatus
    applicant_name: str
    road_addr_part1: str | None = None
    road_addr_part2: str | None = None
    expansion_location: str | None = None
    created_at: datetime


class MyLeadsResponse(BaseModel):
    items: list[MyLeadItem]


class AssigneeNotificationRequest(BaseModel):
    """담당자 배정 알림톡 발송 요청 — 관리자 콘솔(apps/admin) 전용.

    ``assignee_name`` 은 "{회사명} {이름}" 조합으로 들어온다 (회사명 ≤60 + 이름 ≤40).
    """

    assignee_name: str = Field(min_length=1, max_length=101)

    @field_validator("assignee_name")
    @classmethod
    def _strip_assignee_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("assignee_name 은 비어 있을 수 없습니다.")
        return stripped


class AssigneeNotificationResponse(BaseModel):
    sent: bool


class AddressSearchItem(BaseModel):
    """도로명주소 API(addrLinkApi.do) 결과 한 건의 정규화 형태."""

    road_addr: str
    road_addr_part1: str
    road_addr_part2: str
    jibun_addr: str | None = None
    zip_no: str | None = None
    bd_nm: str | None = None
    si_nm: str | None = None
    sgg_nm: str | None = None
    emd_nm: str | None = None


class AddressSearchResponse(BaseModel):
    total_count: int
    page: int
    per_page: int
    items: list[AddressSearchItem]
