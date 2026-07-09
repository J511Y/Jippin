"""워커 HTTP 계약(요청/응답).

응답 필드는 CODEF 결과(`ExclusivePartResult`/`BuildingHeadingResult`)와 **같은 키 형태**로
설계한다 — main-api 클라이언트가 그대로 매핑하도록. 오류는 category 로 분류해 api 가
올바른 CODEF 예외(CodefAuthError/CodefNotFound/…)로 승격하게 한다.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

RegisterKind = Literal["exclusive", "heading"]
ErrorCategory = Literal["auth", "not_found", "invalid", "upstream", "needs_input"]


class BuildingRegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    road_addr: str = Field(min_length=1, max_length=255)
    dong: str = Field(default="", max_length=50)
    ho: str = Field(default="", max_length=50)
    jibun_addr: str | None = Field(default=None, max_length=255)
    register_kind: RegisterKind
    # 현재는 발급(issue)만 구현. 열람(read)은 미구현이라 필드로 노출하지 않는다
    # (advertising 하고 반대로 발급하는 혼동 방지 — 필요 시 후속 구현).


class ExtractionMeta(BaseModel):
    model_config = ConfigDict(extra="allow")

    # 위반 판정을 무엇으로 했는지: report_text(리포트 텍스트) / none(미확인)
    violation_source: str | None = None
    report_text_len: int = 0
    pdf_source: str | None = None  # "pdf_button" | "print" | None
    warnings: list[str] = Field(default_factory=list)


class BuildingRegisterResult(BaseModel):
    """CODEF 결과와 동형(同型) 필드. exclusive/heading 공용 봉투."""

    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    register_kind: RegisterKind

    # 식별/메타
    comm_unique_no: str | None = None
    res_doc_no: str | None = None
    addr_dong: str | None = None
    addr_ho: str | None = None
    res_user_addr: str | None = None
    road_addr: str | None = None
    jibun_addr: str | None = None
    issue_date: str | None = None
    issue_org: str | None = None

    # 핵심 신호 — "위반건축물" 또는 None.
    violation_status: str | None = None

    # 전유부분/공용부분(전유부): [{resType:"0"|"1", resArea, resUseType, resStructure, resFloor}]
    owned: list[dict[str, Any]] = Field(default_factory=list)
    # 변동사항: [{resChangeDate, resChangeReason}]
    change_list: list[dict[str, Any]] = Field(default_factory=list)
    # 공동주택가격: [{resReferenceDate, resBasePrice}]
    price_list: list[dict[str, Any]] = Field(default_factory=list)

    # 표제부 상세: [{resType(항목명), resContents}] (주용도/층수/사용승인일/허가일)
    detail_list: list[dict[str, Any]] = Field(default_factory=list)
    building_status_list: list[dict[str, Any]] = Field(default_factory=list)

    # 원본 PDF(base64). main-api 가 그대로 ExclusivePartResult.original_pdf_base64 로 넣으면
    # 기존 home_check._store_pdfs 가 Supabase 에 저장한다(무변경).
    original_pdf_base64: str | None = None

    extraction: ExtractionMeta = Field(default_factory=ExtractionMeta)


class BuildingRegisterError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = False
    category: ErrorCategory
    message: str
    # needs_input 일 때만: 자동매칭 실패 축과 후보(main-api 가 사용자에게 되물음).
    field: str | None = None
    options: list[dict[str, Any]] | None = None
