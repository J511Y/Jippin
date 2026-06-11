"""행위허가 사전검토 룰엔진 (RULE 모듈, CMP-DIRECT).

공통 판단 스키마(소프트웨어설계문서 §5.2)의 ``judgment_values`` 를 입력으로
국토부 고시 규칙(``services/rules.py`` 카탈로그)을 평가해 철거 가능성·필요
방화시설·행위허가 필요 여부를 산출한다 (기능명세서 §2.8 RULE-001~003).

결정론 계약 (NFR-QUAL-002 — 동일 입력 결정성 100%):

- :func:`evaluate` 는 **순수 함수**다. 시계·난수·네트워크·DB 접근이 없고,
  출력 목록의 순서는 카탈로그 등재 순서로 고정된다.
- 판단값이 누락되면 추측하지 않는다. ``HOLD`` + ``INSUFFICIENT_DATA`` 와
  누락 항목 목록을 반환해 FLOW_GUARD 의 ASK_MORE 보완 루프(기능명세서
  §2.7 FLOW_GUARD-002)로 되돌린다 (NFR-QUAL-003).
- 사용자 문구는 BRAND.md §4 어휘를 따른다 — "확정/보장/통과" 금지,
  "가능성/근거/추가 확인 필요" 사용.

판정 집계 우선순위는 소프트웨어설계문서 §4.8 의 ``DENY > WARN > ALLOW`` 에
보류를 더해 ``DENY > HOLD > WARN > ALLOW`` 로 둔다. 단 벽체 종류조차 모르면
DENY 판단 자체가 불가능하므로 wall_type 누락은 항상 HOLD 다.
"""

from __future__ import annotations

import enum
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from .rules import (
    BASELINE_RULESET,
    LEGAL_EVACUATION_SPACE,
    LEGAL_FIRE_DETECTOR,
    LEGAL_FIRE_DOOR,
    LEGAL_FIRE_DOOR_STAIRCASE_EXCEPTION,
    LEGAL_FIRE_SPREAD_GUARD,
    LEGAL_FIRE_SPRINKLER_EXCEPTION,
    LEGAL_FIRE_ZONE_REVIEW,
    LEGAL_FIRST_FLOOR_EXCEPTION,
    LEGAL_PERMIT_PROCEDURE,
    LEGAL_WALL_LOAD_BEARING_PROHIBITED,
    LEGAL_WALL_NON_LOAD_BEARING,
    LegalBasis,
    Ruleset,
    sort_legal_basis,
)


class WallType(enum.StrEnum):
    """기능명세서 §2.8 RULE-002 ``wall_type``."""

    NON_LOAD_BEARING = "non_load_bearing"
    LOAD_BEARING = "load_bearing"


class WindowType(enum.StrEnum):
    """기능명세서 §2.8 RULE-002 ``window_type``."""

    OPERABLE = "operable"
    FIXED = "fixed"


class Verdict(enum.StrEnum):
    """소프트웨어설계문서 §4.8 RuleEvalResult.verdict."""

    ALLOW = "ALLOW"
    WARN = "WARN"
    DENY = "DENY"
    HOLD = "HOLD"


class PermitRequirement(enum.StrEnum):
    """기능명세서 §2.8 RULE-003 행위허가 필요 여부 (행위허가/신고/불필요)."""

    PERMIT_REQUIRED = "PERMIT_REQUIRED"
    REPORT_REQUIRED = "REPORT_REQUIRED"
    NOT_REQUIRED = "NOT_REQUIRED"
    UNDETERMINED = "UNDETERMINED"


class HoldReason(enum.StrEnum):
    """기능명세서 §2.6 CHAT-004 보류 사유 코드 중 RULE 이 산출하는 부분집합."""

    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    RULE_EXCEPTION = "RULE_EXCEPTION"


class FacilityType(enum.StrEnum):
    """기능명세서 §2.8 RULE-003 필요 방화시설 종류 (FR-RULE-003)."""

    FIRE_DETECTOR = "fire_detector"
    FIRE_PANEL = "fire_panel"
    FIRE_GLASS = "fire_glass"
    FIRE_DOOR = "fire_door"


#: RULE-002 핵심 판단 변수 — 전부 채워져야 시설·가능성 평가가 가능하다.
#: 누락 시 '판단 불가(보류)' + 사유 반환이 수용 기준이다 (FR-RULE-002).
_REQUIRED_FIELDS: tuple[str, ...] = (
    "wall_type",
    "floor_number",
    "sprinkler_coverage",
    "exit_space_exists",
    "staircase_count",
    "window_type",
    "fire_zone",
)

#: 기능명세서 §2.6 CHAT-003 의 생활 언어 질문 — 추가 확인 항목 문구로 재사용.
_FIELD_CHECK_LABELS: dict[str, str] = {
    "wall_type": "철거하려는 벽이 내력벽인지 비내력벽인지 확인이 필요합니다.",
    "floor_number": "세대가 몇 층인지 확인이 필요합니다.",
    "sprinkler_coverage": "발코니 천장에 스프링클러가 있는지 확인이 필요합니다.",
    "exit_space_exists": (
        "비상시 대피할 수 있는 대피공간(또는 옆 세대로 통하는 경량칸막이)이 "
        "있는지 확인이 필요합니다."
    ),
    "staircase_count": "건물의 계단실이 몇 개인지 확인이 필요합니다.",
    "window_type": "외부 창호가 여닫이형인지 고정형(입면분할창)인지 확인이 필요합니다.",
    "fire_zone": "철거 부위가 방화구획에 포함되는지 확인이 필요합니다.",
}


class RuleInputError(ValueError):
    """RuleInput 파싱 단계에서 복구 불가능한 형식 오류."""


@dataclass(frozen=True, slots=True)
class RuleInput:
    """RULE 모듈 입력 — 공통 판단 스키마 ``judgment_values`` 의 정규화 뷰.

    모든 필드는 미수집(None)을 허용한다. 미수집·비정상 값은 평가 단계에서
    추측 없이 보류(HOLD)로 흐른다 (NFR-QUAL-003).
    """

    wall_type: WallType | None = None
    floor_number: int | None = None
    sprinkler_coverage: bool | None = None
    exit_space_exists: bool | None = None
    staircase_count: int | None = None
    window_type: WindowType | None = None
    fire_zone: bool | None = None
    #: 파싱 단계에서 허용 어휘를 벗어나 무시된 필드 — 추가 확인 항목으로 노출.
    invalid_fields: tuple[str, ...] = ()

    @classmethod
    def from_judgment_values(cls, values: Mapping[str, object]) -> "RuleInput":
        """``judgment_values`` dict 를 엄격 파싱한다.

        - 알 수 없는 enum 값/타입 불일치 값은 **추측 없이** 미수집으로
          강등하고 ``invalid_fields`` 에 기록한다 → 평가 결과는 보류가 된다.
        - dict key 순서에 의존하지 않으므로 입력 직렬화 순서가 달라도 결과가
          동일하다 (NFR-QUAL-002).
        """

        if not isinstance(values, Mapping):
            raise RuleInputError("judgment_values 는 object(dict) 여야 합니다.")

        invalid: list[str] = []

        def _enum(name: str, enum_cls: type[enum.StrEnum]) -> enum.StrEnum | None:
            raw = values.get(name)
            if raw is None:
                return None
            if isinstance(raw, enum_cls):
                return raw
            if isinstance(raw, str):
                try:
                    return enum_cls(raw)
                except ValueError:
                    pass
            invalid.append(name)
            return None

        def _bool(name: str) -> bool | None:
            raw = values.get(name)
            if raw is None:
                return None
            if isinstance(raw, bool):
                return raw
            invalid.append(name)
            return None

        def _int(name: str, *, minimum: int) -> int | None:
            raw = values.get(name)
            if raw is None:
                return None
            if isinstance(raw, int) and not isinstance(raw, bool) and raw >= minimum:
                return raw
            invalid.append(name)
            return None

        wall_type = _enum("wall_type", WallType)
        window_type = _enum("window_type", WindowType)
        return cls(
            wall_type=wall_type,  # type: ignore[arg-type]
            floor_number=_int("floor_number", minimum=1),
            sprinkler_coverage=_bool("sprinkler_coverage"),
            exit_space_exists=_bool("exit_space_exists"),
            staircase_count=_int("staircase_count", minimum=0),
            window_type=window_type,  # type: ignore[arg-type]
            fire_zone=_bool("fire_zone"),
            invalid_fields=tuple(sorted(invalid)),
        )

    def missing_fields(self) -> tuple[str, ...]:
        """미수집 필드 목록 — ``_REQUIRED_FIELDS`` 등재 순서로 고정."""

        return tuple(name for name in _REQUIRED_FIELDS if getattr(self, name) is None)


@dataclass(frozen=True, slots=True)
class RequiredFacility:
    """필요 방화시설 1건 — 목록·위치·수량 단위·법령 근거 (FR-RULE-003)."""

    facility: FacilityType
    label: str
    location: str
    quantity_unit: str
    legal_basis: LegalBasis
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "facility": self.facility.value,
            "label": self.label,
            "location": self.location,
            "quantity_unit": self.quantity_unit,
            "legal_basis": self.legal_basis.to_dict(),
            "note": self.note,
        }


@dataclass(frozen=True, slots=True)
class RuleVerdict:
    """RULE 평가 결과 — 소프트웨어설계문서 §4.8 RuleEvalResult 컨트랙트."""

    verdict: Verdict
    permit_requirement: PermitRequirement
    #: BRAND.md §4 어휘의 가능성 단계 라벨 (확정/보장 표현 금지).
    possibility_label: str
    user_message: str
    reasons: tuple[str, ...]
    additional_checks: tuple[str, ...]
    hold_reasons: tuple[HoldReason, ...]
    required_facilities: tuple[RequiredFacility, ...]
    legal_basis: tuple[LegalBasis, ...]
    ruleset_version: str
    law_reference: str
    law_verified_on: str

    def to_dict(self) -> dict[str, object]:
        """REPORT 모듈/스냅샷 테스트용 직렬화 — 순서·키가 모두 고정이다."""

        return {
            "verdict": self.verdict.value,
            "permit_requirement": self.permit_requirement.value,
            "possibility_label": self.possibility_label,
            "user_message": self.user_message,
            "reasons": list(self.reasons),
            "additional_checks": list(self.additional_checks),
            "hold_reasons": [reason.value for reason in self.hold_reasons],
            "required_facilities": [
                facility.to_dict() for facility in self.required_facilities
            ],
            "legal_basis": [basis.to_dict() for basis in self.legal_basis],
            "ruleset_version": self.ruleset_version,
            "law_reference": self.law_reference,
            "law_verified_on": self.law_verified_on,
        }

    def to_canonical_json(self) -> str:
        """결정론 비교용 canonical JSON (정렬 키, 비ASCII 보존)."""

        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------------------
# 내부 평가 단계 — 규칙 정의 / 개별 평가 / 집계 / 메시지 빌드 분리 (§4.8)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class _Evaluation:
    """평가 도중 누적되는 가변 상태. evaluate() 밖으로 노출되지 않는다."""

    reasons: list[str] = field(default_factory=list)
    additional_checks: list[str] = field(default_factory=list)
    hold_reasons: list[HoldReason] = field(default_factory=list)
    facilities: list[RequiredFacility] = field(default_factory=list)
    legal_basis: set[LegalBasis] = field(default_factory=set)
    deny: bool = False
    warn: bool = False


def _hold_for_missing(evaluation: _Evaluation, rule_input: RuleInput) -> None:
    """누락·비정상 입력 → 추측 없이 보류 (FR-RULE-002 수용 기준)."""

    missing = rule_input.missing_fields()
    flagged = tuple(
        dict.fromkeys(missing + rule_input.invalid_fields)
    )  # 등재 순서 유지 + 중복 제거
    if not flagged:
        return
    evaluation.hold_reasons.append(HoldReason.INSUFFICIENT_DATA)
    evaluation.reasons.append(
        "판단에 필요한 정보가 아직 모두 확인되지 않았습니다. 아래 항목을 "
        "확인해 주시면 다시 검토할 수 있습니다."
    )
    for name in flagged:
        evaluation.additional_checks.append(_FIELD_CHECK_LABELS[name])


def _evaluate_wall(evaluation: _Evaluation, rule_input: RuleInput) -> None:
    """R-WALL-01/02 — 내력벽 금지, 비내력벽 확인."""

    if rule_input.wall_type is WallType.LOAD_BEARING:
        evaluation.deny = True
        evaluation.legal_basis.add(LEGAL_WALL_LOAD_BEARING_PROHIBITED)
        evaluation.reasons.append(
            "철거를 검토하신 벽이 내력벽으로 확인되었습니다. 내력벽의 "
            "철거·변경은 구조 안전과 직결되어 사전검토 단계에서는 진행이 "
            "어렵습니다."
        )
        evaluation.additional_checks.append(
            "구조 도면과 함께 관할 행정기관·구조 전문가 상담을 진행해 주세요."
        )
    elif rule_input.wall_type is WallType.NON_LOAD_BEARING:
        evaluation.legal_basis.add(LEGAL_WALL_NON_LOAD_BEARING)
        evaluation.reasons.append(
            "철거 대상 벽이 비내력벽으로 확인되어, 행위허가 절차를 전제로 "
            "검토를 진행할 수 있습니다."
        )


def _evaluate_fire_zone(evaluation: _Evaluation, rule_input: RuleInput) -> None:
    """R-ZONE-01 — 방화구획 포함 시 자동 판단 불가 (보수 분기).

    고시·건축법은 방화구획 변경 시 별도의 성능 검토를 요구하지만 그 판단
    기준을 사전검토에서 수치화할 수 없다. 명세(기능명세서 §2.6 CHAT-004
    RULE_EXCEPTION)에 따라 불가 단정 대신 보류 + 전문가 확인으로 분기한다.
    """

    if rule_input.fire_zone is True:
        evaluation.hold_reasons.append(HoldReason.RULE_EXCEPTION)
        evaluation.legal_basis.add(LEGAL_FIRE_ZONE_REVIEW)
        evaluation.reasons.append(
            "철거 부위가 방화구획에 포함되어 있어 자동 검토 범위를 "
            "벗어납니다. 방화구획 성능 유지 여부는 별도 확인이 필요합니다."
        )
        evaluation.additional_checks.append(
            "방화구획 변경 가능 여부를 관할 행정기관 또는 건축 전문가와 "
            "확인해 주세요."
        )


def _evaluate_evacuation(
    evaluation: _Evaluation, rule_input: RuleInput, ruleset: Ruleset
) -> None:
    """R-EVAC-01 — 4층 이상 세대의 대피공간 확보 (건축법 시행령 §46④)."""

    assert rule_input.floor_number is not None  # 누락은 사전에 HOLD 처리됨
    if rule_input.floor_number < ruleset.parameters.evacuation_space_min_floor:
        return
    if rule_input.exit_space_exists is True:
        evaluation.legal_basis.add(LEGAL_EVACUATION_SPACE)
        evaluation.reasons.append(
            "대피공간(또는 경량칸막이)이 확인되어 대피 경로 요건을 충족할 "
            "가능성이 있습니다."
        )
    else:
        # 대피공간 미확보 — 확장 자체가 불가능한 것은 아니고 대체 시설
        # (경량칸막이·하향식 피난구 등) 설치로 충족할 수 있어, 불가 단정
        # 대신 WARN + 추가 확인으로 분기한다 (보수 분기, 건축법 시행령
        # 제46조 제4항 각 호의 대체 수단을 자동 판별할 수 없음).
        evaluation.warn = True
        evaluation.legal_basis.add(LEGAL_EVACUATION_SPACE)
        evaluation.reasons.append(
            "4층 이상 세대는 발코니 확장 시 대피공간 등 대피 경로 확보가 "
            "필요한데, 현재 정보로는 확인되지 않았습니다."
        )
        evaluation.additional_checks.append(
            "대피공간·경량칸막이 등 대체 대피 경로 확보 방안을 확인해 주세요."
        )


def _evaluate_facilities(
    evaluation: _Evaluation, rule_input: RuleInput, ruleset: Ruleset
) -> None:
    """R-FIRE-01~06 — 필요 방화시설 산출과 자동 예외 적용 (FR-RULE-003/004).

    기능명세서 §2.8 자동 예외 조건:
    - 1층 세대: 화재감지기만 설치 (방화판·방화문 제외)
    - 계단실 2개소 이상: 방화문 설치 제외
    - 스프링클러 살수 범위 포함: 방화판·화재감지기 제외
    """

    params = ruleset.parameters
    assert rule_input.floor_number is not None
    assert rule_input.sprinkler_coverage is not None
    assert rule_input.staircase_count is not None
    assert rule_input.window_type is not None

    is_first_floor = rule_input.floor_number <= params.first_floor_exception_max_floor
    sprinkler = rule_input.sprinkler_coverage

    # ── 화재감지기 (R-FIRE-01) — 기본 필요, 스프링클러 예외 (R-FIRE-03).
    if sprinkler:
        evaluation.legal_basis.add(LEGAL_FIRE_SPRINKLER_EXCEPTION)
        evaluation.reasons.append(
            "발코니가 스프링클러 살수범위에 포함되어 방화판·방화유리창과 "
            "화재감지기 설치 의무가 제외될 가능성이 있습니다."
        )
    else:
        evaluation.legal_basis.add(LEGAL_FIRE_DETECTOR)
        evaluation.facilities.append(
            RequiredFacility(
                facility=FacilityType.FIRE_DETECTOR,
                label="화재감지기",
                location="확장되는 발코니 부분",
                quantity_unit="개소",
                legal_basis=LEGAL_FIRE_DETECTOR,
            )
        )

    # ── 방화판/방화유리창 (R-FIRE-02) — 아래층 화재 확산 방지.
    # 1층 세대 예외(R-FIRE-06) 및 스프링클러 예외(R-FIRE-03) 적용.
    # 명세서 §2.8 의 스프링클러 예외 문구는 "방화판·감지기 제외"만 적지만,
    # 고시 제5조 제1항 원문은 "방화판 또는 방화유리창"을 한 묶음으로 다루므로
    # 방화유리창도 함께 제외한다 (조문 원문 우선).
    if is_first_floor:
        evaluation.legal_basis.add(LEGAL_FIRST_FLOOR_EXCEPTION)
        evaluation.reasons.append(
            "1층 세대 예외가 적용되어 방화판·방화문 설치 의무가 제외될 "
            "가능성이 있습니다."
        )
    elif (
        rule_input.floor_number >= params.fire_spread_guard_min_floor and not sprinkler
    ):
        evaluation.legal_basis.add(LEGAL_FIRE_SPREAD_GUARD)
        if rule_input.window_type is WindowType.FIXED:
            # 입면분할창 등 고정형 창호 — 창호 일체형 방화유리창으로 산출.
            evaluation.facilities.append(
                RequiredFacility(
                    facility=FacilityType.FIRE_GLASS,
                    label="방화유리창",
                    location="아래층 세대와 접하는 발코니 외부 창호 부위",
                    quantity_unit="m (창호 가로 길이)",
                    legal_basis=LEGAL_FIRE_SPREAD_GUARD,
                    note="고정형(입면분할) 창호 기준 산출",
                )
            )
        else:
            evaluation.facilities.append(
                RequiredFacility(
                    facility=FacilityType.FIRE_PANEL,
                    label="방화판",
                    location="아래층 세대와 접하는 발코니 창호 하부 외벽",
                    quantity_unit="m (가로 길이)",
                    legal_basis=LEGAL_FIRE_SPREAD_GUARD,
                    note="여닫이형(난간형) 창호 기준 산출",
                )
            )

    # ── 방화문 (R-FIRE-04) — 대피공간 출입구.
    # 예외: 1층 세대(R-FIRE-06), 계단실 2개소 이상(R-FIRE-05).
    if is_first_floor:
        pass  # 1층 예외 사유는 위에서 이미 기록.
    elif rule_input.staircase_count >= params.staircase_exception_min_count:
        evaluation.legal_basis.add(LEGAL_FIRE_DOOR_STAIRCASE_EXCEPTION)
        evaluation.reasons.append(
            "계단실이 2개소 이상으로 확인되어 방화문 설치 의무가 제외될 "
            "가능성이 있습니다."
        )
    else:
        evaluation.legal_basis.add(LEGAL_FIRE_DOOR)
        evaluation.facilities.append(
            RequiredFacility(
                facility=FacilityType.FIRE_DOOR,
                label="방화문",
                location="대피공간 출입구",
                quantity_unit="개소",
                legal_basis=LEGAL_FIRE_DOOR,
            )
        )


def _aggregate_verdict(evaluation: _Evaluation) -> Verdict:
    """판정 집계 — DENY > HOLD > WARN > ALLOW (소프트웨어설계문서 §4.8)."""

    if evaluation.deny:
        return Verdict.DENY
    if evaluation.hold_reasons:
        return Verdict.HOLD
    if evaluation.warn:
        return Verdict.WARN
    return Verdict.ALLOW


def _permit_requirement(verdict: Verdict) -> PermitRequirement:
    """행위허가 필요 여부 (FR-RULE-005).

    비내력벽 철거를 동반한 발코니 구조변경은 공동주택관리법 제35조의 행위허가
    대상이다. 일부 지자체는 경미한 행위를 신고로 처리하지만 그 경계를 자동
    판별할 수 없어 보수적으로 '행위허가 필요'로 분류한다 (보수 분기,
    기능명세서 §2.8 RULE-003). 보류 시에는 절차 분류도 미확정으로 둔다.
    """

    if verdict is Verdict.HOLD:
        return PermitRequirement.UNDETERMINED
    return PermitRequirement.PERMIT_REQUIRED


# BRAND.md §4.3 권장 표현 — 확정/보장/통과 금지, 가능성/근거/추가 확인 사용.
_POSSIBILITY_LABELS: dict[Verdict, str] = {
    Verdict.ALLOW: "가능성 있음",
    Verdict.WARN: "가능성 있음 (추가 확인 필요)",
    Verdict.DENY: "어려움",
    Verdict.HOLD: "추가 확인 필요",
}

_USER_MESSAGES: dict[Verdict, str] = {
    Verdict.ALLOW: (
        "지금 정보 기준으로는 가능성이 있습니다. 아래 근거와 필요 시설을 "
        "확인해 주세요."
    ),
    Verdict.WARN: (
        "지금 정보 기준으로는 가능성이 있지만, 아래 항목을 추가로 확인해 "
        "주셔야 합니다."
    ),
    Verdict.DENY: "제출하신 정보로는 어렵습니다. 사유는 다음과 같습니다.",
    Verdict.HOLD: (
        "지금 정보만으로는 판단이 어렵습니다. 다음 항목을 추가로 확인해 " "주세요."
    ),
}


def evaluate(rule_input: RuleInput, ruleset: Ruleset = BASELINE_RULESET) -> RuleVerdict:
    """공통 판단 스키마 입력을 평가해 :class:`RuleVerdict` 를 산출한다.

    순수·결정적 함수 — 동일 ``(rule_input, ruleset)`` 에 대해 항상 동일한
    결과를 반환한다 (NFR-QUAL-002). FLOW_GUARD 가 PROCEED_RULE 을 반환한
    완성 스키마를 전제로 하지만, 방어적으로 누락 입력도 보류로 처리한다.
    """

    evaluation = _Evaluation()

    # 1단계 — 벽체 판정. 내력벽이 확인되면 다른 변수가 누락이어도 DENY 가
    # 확정적이다 (내력벽 금지는 다른 변수와 무관, R-WALL-01).
    _evaluate_wall(evaluation, rule_input)

    if not evaluation.deny:
        # 2단계 — 입력 충분성. 하나라도 누락/비정상이면 추측 없이 보류.
        _hold_for_missing(evaluation, rule_input)

        if not evaluation.hold_reasons:
            # 3단계 — 개별 규칙 평가 (입력이 모두 확보된 경우에만).
            _evaluate_fire_zone(evaluation, rule_input)
            _evaluate_evacuation(evaluation, rule_input, ruleset)
            _evaluate_facilities(evaluation, rule_input, ruleset)

    verdict = _aggregate_verdict(evaluation)
    permit = _permit_requirement(verdict)
    if verdict is not Verdict.HOLD:
        evaluation.legal_basis.add(LEGAL_PERMIT_PROCEDURE)

    return RuleVerdict(
        verdict=verdict,
        permit_requirement=permit,
        possibility_label=_POSSIBILITY_LABELS[verdict],
        user_message=_USER_MESSAGES[verdict],
        reasons=tuple(evaluation.reasons),
        additional_checks=tuple(evaluation.additional_checks),
        hold_reasons=tuple(dict.fromkeys(evaluation.hold_reasons)),
        required_facilities=tuple(evaluation.facilities),
        legal_basis=sort_legal_basis(evaluation.legal_basis),
        ruleset_version=ruleset.version,
        law_reference=ruleset.law_reference,
        law_verified_on=ruleset.verified_on,
    )


def evaluate_judgment_values(
    judgment_values: Mapping[str, object],
    ruleset: Ruleset = BASELINE_RULESET,
) -> RuleVerdict:
    """FLOW_GUARD/CHAT 연동용 얇은 헬퍼 — dict 입력을 파싱 후 평가한다.

    공통 판단 스키마(§5.2)의 ``judgment_values`` 필드를 그대로 받는다.
    라우터에 노출하지 않는 내부 서비스 함수다.
    """

    return evaluate(RuleInput.from_judgment_values(judgment_values), ruleset)
