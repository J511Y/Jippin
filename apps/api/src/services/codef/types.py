"""CODEF 세움터 집합건축물대장 클라이언트 — 공개 타입 정본 (ADR-0008).

이 모듈의 정의는 Round2 서비스(``home_check`` 오케스트레이터)가 그대로 import 하는
인터페이스 계약이다. 시그니처/필드명을 임의로 바꾸지 마라.

PII 정책(ADR-0008 §2.3): 소유자명·주민번호(``resOwnerList``)와 설계자/시공자 면허
정보(``resLicenseClassList``)는 구조화 저장하지 않으며, 결과 dataclass 에 의도적으로
노출하지 않는다. 원본 PDF(``original_pdf_base64``)에만 존재한다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class BuildingRegisterQuery:
    """우리집 체크 1건의 사용자 입력(건물 단위 도로명 + 동/호)."""

    road_addr: str  # 도로명주소(건물 단위, 동·호 제외)
    dong: str  # 동 (없으면 "")
    ho: str  # 호
    jibun_addr: str | None = None


@dataclass
class ExclusivePartResult:
    """전유부(`aggregate-buildings`) 파싱 결과 — 호 단위."""

    res_doc_no: str | None
    comm_unique_no: str | None
    addr_dong: str | None
    addr_ho: str | None
    res_user_addr: str | None
    road_addr: str | None
    jibun_addr: str | None
    owned: list[dict]  # resOwnedList 원소 그대로
    change_list: list[dict]  # resChangeList
    price_list: list[dict]  # resPriceList
    violation_status: str | None  # resViolationStatus
    issue_date: str | None
    issue_org: str | None
    original_pdf_base64: str | None


@dataclass
class BuildingHeadingResult:
    """표제부(`building-ledger-heading`) 파싱 결과 — 건물 단위."""

    res_doc_no: str | None
    comm_unique_no: str | None
    res_user_addr: str | None
    detail_list: list[dict]  # resDetailList
    building_status_list: list[dict]  # resBuildingStatusList
    change_list: list[dict]  # resChangeList
    violation_status: str | None
    issue_date: str | None
    issue_org: str | None
    original_pdf_base64: str | None
    # resOwnerList / resLicenseClassList (PII) 는 의도적으로 미노출 — 파싱하지 마라.


class CodefError(Exception):
    """CODEF 연동 오류의 베이스. ``code`` 는 CODEF result.code(있으면)."""

    def __init__(self, message: str = "", *, code: str | None = None):
        super().__init__(message)
        self.code = code
        self.message = message


class CodefAuthError(CodefError):
    """자격증명/계정잠금 — 서킷 카운트, 재시도 금지."""


class CodefCircuitOpen(CodefError):
    """서킷브레이커 open — 단일 세움터 계정 보호 차단 중."""


class CodefUpstreamError(CodefError):
    """세움터 점검/timeout/5xx 등 상류 일시 오류."""


class CodefNotFound(CodefError):
    """대장/주소 매칭 최종 실패."""


class CodefInvalidInput(CodefError):
    """입력 오류(주소 형식 등)."""


class CodefNeedsUserInput(CodefError):
    """2-way 자동매칭 실패 → 사용자 추가 입력 필요.

    ``kind`` 가 "dong_ho" 면 주소·동·호 선택, "secure_no" 면 보안문자 입력이 필요하다.
    ``resume_token`` 으로 1차 결과를 복원해 2차를 이어 호출한다(``resume_*``).

    ``field``/``options`` 는 dong_ho 일 때 **사용자에게 보여줄 후보 목록**이다(주소/동/호 중
    하나). CODEF 가 돌려준 후보를 그대로 버리지 않고 프론트가 드롭다운으로 제시하게 한다.
    ``options`` 원소는 contract NeedsInputOption shape: ``{value, label, area?}``.
    """

    def __init__(
        self,
        kind: Literal["dong_ho", "secure_no"],
        resume_token: str,
        message: str = "",
        *,
        field: Literal["address", "dong", "ho"] | None = None,
        options: list[dict] | None = None,
    ):
        super().__init__(message)
        self.kind = kind
        self.resume_token = resume_token
        self.field = field
        self.options = options
