"""행위허가 사전검토 룰엔진 (RULE 모듈, CMP-DIRECT).

공통 판단 스키마(소프트웨어설계문서 §5.2, ``packages/contracts/schemas/
common-judgment-schema.schema.json``)의 ``judgment_values`` 를 입력으로
국토부 고시 규칙(``services/rules.py`` 카탈로그)을 평가해 철거 가능성·필요
방화시설·행위허가 필요 여부를 산출한다 (기능명세서 §2.8 RULE-001~003).

입력 컨트랙트 (CMP-527 정본):

- ``JudgmentValues`` 의 캐노니컬 필드명(``floor_count``, ``has_sprinkler``,
  ``has_evacuation_space``, ``stairwell_count``, ``window_form``,
  ``balcony_attached``, ``permit_history_known``)을 그대로 받는다. 단,
  충분성(보류) 검사는 규칙이 실제 소비하는 ``_REQUIRED_FIELDS`` 에만
  적용한다 — 판정 미사용 필드는 ``_OPTIONAL_FIELDS`` 참고.
- ``wall_type``/``fire_zone`` 은 ``judgment_values`` 가 아니라
  CommonJudgmentSchema 의 ``wall_objects``·``selected_walls`` 분석에서
  유도되는 **엔진 컨텍스트 키**다. 호출자(CHAT/FLOW_GUARD 연동 계층)가
  병합해 전달하며, 어휘는 계약의 ``WallObject.wall_type`` 을 따른다.
- 그 밖의 알 수 없는 key 는 계약의 ``additionalProperties: false`` 와
  동일하게 거절한다 (:class:`RuleInputError`).

출력 컨트랙트:

- :meth:`RuleVerdict.to_contract_dict` 가 ``rule-eval-result.schema.json``
  (RuleEvalResult) 정본 shape 를 직렬화한다. REPORT/스냅샷은 이 결과를
  소비한다. ``evaluated_at`` 은 평가가 아니라 **영속화 시점에 호출자가
  주입**한다 — evaluate() 내부에는 시계가 없다 (NFR-QUAL-002).

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
from dataclasses import dataclass, field, replace
from datetime import datetime

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

#: rule-eval-result.schema.json 의 ``schema_version`` const (ADR-0001/CMP-527).
RULE_EVAL_RESULT_SCHEMA_VERSION = "1.0.0"


class WallType(enum.StrEnum):
    """계약 ``WallObject.wall_type`` 어휘 (common-judgment-schema §$defs).

    계약의 ``UNKNOWN`` 은 보완 루프 트리거이므로 엔진 어휘에 두지 않는다 —
    파싱 단계에서 ``invalid_fields`` 로 강등되어 보류(HOLD)로 흐른다.
    """

    NON_LOAD_BEARING = "NON_LOAD_BEARING"
    LOAD_BEARING = "LOAD_BEARING"


class WindowForm(enum.StrEnum):
    """계약 ``JudgmentValues.window_form`` 어휘 (창호 형태)."""

    FIXED = "FIXED"
    OPENABLE = "OPENABLE"
    FOLDING = "FOLDING"
    SLIDING = "SLIDING"
    OTHER = "OTHER"


class Verdict(enum.StrEnum):
    """rule-eval-result.schema.json ``verdict`` enum."""

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


#: RuleEvalResult 계약 ``RequiredFacility.code`` enum 으로의 **전사** 매핑 —
#: 엔진이 산출하는 모든 시설은 캐노니컬 직렬화에 빠짐없이 나타나야 한다
#: (고시 §6 화재감지기 포함, FR-RULE-003).
#: - 방화문(대피공간 출입구)은 자동 닫힘 구조가 요건이므로 계약 코드
#:   ``AUTOMATIC_DOOR_CLOSER`` 로 표기한다.
_FACILITY_CONTRACT_CODES: dict[FacilityType, str] = {
    FacilityType.FIRE_DETECTOR: "FIRE_DETECTOR",
    FacilityType.FIRE_PANEL: "FIRE_PANEL",
    FacilityType.FIRE_GLASS: "FIRE_GLASS",
    FacilityType.FIRE_DOOR: "AUTOMATIC_DOOR_CLOSER",
}

#: 계약 JudgmentValues 의 캐노니컬 필드명 (common-judgment-schema §$defs).
JUDGMENT_VALUE_FIELDS: tuple[str, ...] = (
    "floor_count",
    "has_sprinkler",
    "has_evacuation_space",
    "stairwell_count",
    "window_form",
    "balcony_attached",
    "permit_history_known",
)

#: judgment_values 밖에서 유도되는 엔진 컨텍스트 키 (모듈 docstring 참고).
CONTEXT_FIELDS: tuple[str, ...] = ("wall_type", "fire_zone")

#: RULE-002 핵심 판단 변수 — 실제 규칙(R-WALL/R-ZONE/R-EVAC/R-FIRE)이
#: 소비하는 필드만 충분성 검사 대상이다. 전부 채워져야 시설·가능성 평가가
#: 가능하며, 누락 시 '판단 불가(보류)' + 사유 반환이 수용 기준이다
#: (FR-RULE-002).
_REQUIRED_FIELDS: tuple[str, ...] = (
    "wall_type",
    "floor_count",
    "has_sprinkler",
    "has_evacuation_space",
    "stairwell_count",
    "window_form",
    "fire_zone",
)

#: 수집은 하되(기술명세 JudgmentValues) 현행 규칙이 판정에 사용하지 않는
#: 필드 — 미수집(None)이어도 보류(HOLD) 사유가 되지 않는다.
#: - ``balcony_attached``: 확장 대상 식별용 메타데이터. 어느 R-* 규칙도
#:   분기에 사용하지 않는다.
#: - ``permit_history_known``: 행위허가 이력 인지 여부. 절차 안내 참고용일
#:   뿐 판정 분기 입력이 아니다.
#: 값이 *제공되었는데* 형식이 비정상이면 다른 필드와 동일하게
#: ``invalid_fields`` 로 강등되어 재확인을 요청한다 (추측 금지 원칙 유지).
_OPTIONAL_FIELDS: tuple[str, ...] = tuple(
    name for name in JUDGMENT_VALUE_FIELDS if name not in _REQUIRED_FIELDS
)

_ACCEPTED_KEYS: frozenset[str] = frozenset(JUDGMENT_VALUE_FIELDS) | frozenset(
    CONTEXT_FIELDS
)

#: 기능명세서 §2.6 CHAT-003 의 생활 언어 질문 — 추가 확인 항목 문구로 재사용.
_FIELD_CHECK_LABELS: dict[str, str] = {
    "wall_type": "철거하려는 벽이 내력벽인지 비내력벽인지 확인이 필요합니다.",
    "floor_count": "세대가 몇 층인지 확인이 필요합니다.",
    "has_sprinkler": "발코니 천장에 스프링클러가 있는지 확인이 필요합니다.",
    "has_evacuation_space": (
        "비상시 대피할 수 있는 대피공간(또는 옆 세대로 통하는 경량칸막이)이 "
        "있는지 확인이 필요합니다."
    ),
    "stairwell_count": "건물의 계단실이 몇 개인지 확인이 필요합니다.",
    "window_form": "외부 창호가 여닫이형인지 고정형(입면분할창)인지 확인이 필요합니다.",
    "balcony_attached": "확장하려는 공간이 발코니와 접해 있는지 확인이 필요합니다.",
    "permit_history_known": (
        "이 건물에 기존 행위허가(또는 신고) 이력이 있는지 확인이 필요합니다."
    ),
    "fire_zone": "철거 부위가 방화구획에 포함되는지 확인이 필요합니다.",
}


#: 발코니 확장 경로에서 안전 변수가 미확인(None)일 때 쓰는 **보수적(안전측) 기본값**.
#: 운영자 결정(2026-06-26): 미확인 항목은 HOLD 로 막지 말고, "면제받지 못함 / 시설·대피
#: 공간 필요" 방향으로 가정해 리포트를 내고 해당 항목을 미확인 caveat 로 첨부한다. 그래야
#: 평면도/사용자가 못 준 정보 때문에 리포트가 영영 안 나오는 일을 막는다.
#: - floor_count: 1층 예외 X·4층 대피공간 O 가 되도록 5 로 가정(요건 최대).
#: - fire_zone: True 면 RULE_EXCEPTION 으로 자동판단 불가가 되어 리포트가 막히므로,
#:   미확인은 False 로 가정(생성 우선) + caveat 로 "포함 시 별도 검토" 안내.
_CONSERVATIVE_DEFAULTS: dict[str, object] = {
    "floor_count": 5,
    "has_sprinkler": False,
    "has_evacuation_space": False,
    "stairwell_count": 1,
    "window_form": WindowForm.OTHER,
    "fire_zone": False,
}

#: 미확인으로 보수적 가정한 필드를 리포트에 첨부할 생활어 라벨(추가 확인 항목).
_UNCONFIRMED_CHECK_LABELS: dict[str, str] = {
    "floor_count": "세대 층수가 확인되지 않아 보수적으로 가정했어요(정확한 층수를 알려 주시면 더 정확해져요).",
    "has_sprinkler": "스프링클러 설치 여부가 확인되지 않아, 없는 것으로 보고 방화시설이 필요하다고 판단했어요.",
    "has_evacuation_space": "대피공간·경량칸막이 확보 여부가 확인되지 않아, 없는 것으로 보고 판단했어요.",
    "stairwell_count": "이용 가능한 계단실 수가 확인되지 않아, 예외(2개소 이상)에 해당하지 않는 것으로 보았어요.",
    "window_form": "외부 창호 형태가 확인되지 않아, 일반(비고정형) 기준으로 보았어요.",
    "fire_zone": "방화구획 포함 여부가 확인되지 않았어요. 포함되는 경우 별도 검토가 필요해요.",
}

#: user_message 한 줄에 묶어 넣을 미확인 항목 짧은 이름.
_UNCONFIRMED_FIELD_NAMES: dict[str, str] = {
    "floor_count": "층수",
    "has_sprinkler": "스프링클러 유무",
    "has_evacuation_space": "대피공간 유무",
    "stairwell_count": "계단실 수",
    "window_form": "창호 형태",
    "fire_zone": "방화구획 포함 여부",
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
    floor_count: int | None = None
    has_sprinkler: bool | None = None
    has_evacuation_space: bool | None = None
    stairwell_count: int | None = None
    window_form: WindowForm | None = None
    balcony_attached: bool | None = None
    permit_history_known: bool | None = None
    fire_zone: bool | None = None
    #: 파싱 단계에서 허용 어휘를 벗어나 무시된 필드 — 추가 확인 항목으로 노출.
    invalid_fields: tuple[str, ...] = ()

    @classmethod
    def from_judgment_values(cls, values: Mapping[str, object]) -> "RuleInput":
        """계약 ``JudgmentValues``(+엔진 컨텍스트 키)를 엄격 파싱한다.

        - 계약 밖의 알 수 없는 key 는 ``additionalProperties: false`` 와
          동일하게 :class:`RuleInputError` 로 거절한다.
        - 알 수 없는 enum 값/타입 불일치 값은 **추측 없이** 미수집으로
          강등하고 ``invalid_fields`` 에 기록한다 → 평가 결과는 보류가 된다.
        - dict key 순서에 의존하지 않으므로 입력 직렬화 순서가 달라도 결과가
          동일하다 (NFR-QUAL-002).
        """

        if not isinstance(values, Mapping):
            raise RuleInputError("judgment_values 는 object(dict) 여야 합니다.")

        unknown = sorted(set(values) - _ACCEPTED_KEYS)
        if unknown:
            raise RuleInputError(
                "계약(JudgmentValues, additionalProperties=false)에 없는 key 가 "
                f"있습니다: {unknown}"
            )

        invalid: list[str] = []

        def _enum(name: str, enum_cls: type[enum.StrEnum]) -> enum.StrEnum | None:
            raw = values.get(name)
            if isinstance(raw, enum.Enum) and not isinstance(raw, enum_cls):
                # zippin_contracts 생성 모델의 plain Enum 인스턴스 허용 —
                # 호출자가 pydantic 모델 속성을 그대로 넘기는 경우 .value 로
                # 강등해 문자열 어휘와 동일하게 매칭한다 (계약 WindowForm 의
                # null 멤버는 .value 가 None 이라 미수집으로 흐른다).
                raw = raw.value
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
        window_form = _enum("window_form", WindowForm)
        return cls(
            wall_type=wall_type,  # type: ignore[arg-type]
            floor_count=_int("floor_count", minimum=1),
            has_sprinkler=_bool("has_sprinkler"),
            has_evacuation_space=_bool("has_evacuation_space"),
            stairwell_count=_int("stairwell_count", minimum=0),
            window_form=window_form,  # type: ignore[arg-type]
            balcony_attached=_bool("balcony_attached"),
            permit_history_known=_bool("permit_history_known"),
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

    @property
    def contract_code(self) -> str:
        """RuleEvalResult 계약 ``RequiredFacility.code`` — 전사 매핑."""

        return _FACILITY_CONTRACT_CODES[self.facility]

    def to_contract_dict(self) -> dict[str, object]:
        """계약 ``RequiredFacility`` item (code/label/measurement_basis)."""

        return {
            "code": self.contract_code,
            "label": self.label,
            "measurement_basis": f"{self.location} — {self.quantity_unit}",
        }


@dataclass(frozen=True, slots=True)
class RuleVerdict:
    """RULE 평가 결과 — 소프트웨어설계문서 §4.8 RuleEvalResult 컨트랙트."""

    verdict: Verdict
    permit_requirement: PermitRequirement
    #: BRAND.md §4.3 어휘의 가능성 단계 라벨 (확정/보장 표현 금지).
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

    @property
    def permit_required(self) -> bool:
        """계약 ``permit_required`` boolean (행위허가 필요 여부).

        NOT_REQUIRED 만 False 다. UNDETERMINED(보류)는 보수적으로 True 로
        직렬화한다 — 절차 필요 가능성을 숨기지 않는다 (보수 분기).
        """

        return self.permit_requirement is not PermitRequirement.NOT_REQUIRED

    def to_dict(self) -> dict[str, object]:
        """내부 상세 직렬화 — REPORT 본문 메시지·감사용. 순서·키 고정."""

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

    def to_contract_dict(self, *, evaluated_at: datetime) -> dict[str, object]:
        """캐노니컬 ``RuleEvalResult``(rule-eval-result.schema.json) 직렬화.

        REPORT/영속화(스냅샷)가 소비하는 정본 shape 다. ``evaluated_at`` 은
        **호출자가 영속화 시점에 주입**한다 — evaluate() 는 순수 함수로
        남아야 하므로 평가 내부에 시계를 두지 않는다 (NFR-QUAL-002).
        """

        if evaluated_at.tzinfo is None:
            raise ValueError(
                "evaluated_at 은 timezone-aware datetime 이어야 합니다 "
                "(계약 format: ISO-8601 date-time)."
            )
        return {
            "schema_version": RULE_EVAL_RESULT_SCHEMA_VERSION,
            "verdict": self.verdict.value,
            "required_facilities": [
                facility.to_contract_dict() for facility in self.required_facilities
            ],
            "permit_required": self.permit_required,
            "legal_basis": [
                {
                    "statute": basis.source,
                    "article": basis.section,
                    "summary": basis.summary,
                    "url": basis.link,
                }
                for basis in self.legal_basis
            ],
            "ruleset_version": self.ruleset_version,
            "evaluated_at": evaluated_at.isoformat(),
            "user_message": self.user_message,
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


def _hold_for_unknown_wall(evaluation: _Evaluation, rule_input: RuleInput) -> bool:
    """벽 종류 미상/비정상이면 보류 — **유일하게 HOLD 로 막는 전제 조건**.

    나머지 안전 변수(층수·스프링클러·대피공간·계단실·창호·방화구획)는 발코니 확장
    경로에서 보수적 기본값으로 채워 평가하므로 HOLD 사유가 아니다(운영 스코핑). 단,
    벽 종류는 철거 가능성 판단의 전제라 모르면 판단 자체가 불가능하다.
    """

    wall_unknown = (
        rule_input.wall_type is None or "wall_type" in rule_input.invalid_fields
    )
    if not wall_unknown:
        return False
    evaluation.hold_reasons.append(HoldReason.INSUFFICIENT_DATA)
    evaluation.reasons.append(
        "철거하려는 벽이 내력벽인지 비내력벽인지부터 확인이 필요합니다."
    )
    evaluation.additional_checks.append(_FIELD_CHECK_LABELS["wall_type"])
    return True


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
    이 보류가 설정되면 evaluate() 가 이후 평가(대피공간·시설 산출)를
    건너뛴다 — 수동 검토 대상에 실행 가능한 시설 목록을 산출하지 않는다.
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


def _evacuation_required(rule_input: RuleInput, ruleset: Ruleset) -> bool:
    """별도 대피공간 구획이 **필요한지** 여부 (건축법 시행령 §46④ + 운영 스코핑).

    아래 중 하나라도 해당하면 대피공간을 별도로 구획하지 않아도 된다(불필요):
    - 저층(3층 이하): ``floor_count < evacuation_space_min_floor``.
    - 직통계단(계단실) 2개소 이상: ``stairwell_count >= staircase_exception_min_count``.
    - 경량칸막이/대피공간 이미 확보: ``has_evacuation_space is True`` (호출부에서 처리).

    여기서는 층수·계단실만으로 '필요 여부'를 본다(경량칸막이 확보는 호출부에서 충족
    처리). 미확인 입력은 호출 전에 보수적 기본값으로 채워진다(확장 경로).
    """

    assert rule_input.floor_count is not None
    if rule_input.floor_count < ruleset.parameters.evacuation_space_min_floor:
        return False
    if (
        rule_input.stairwell_count is not None
        and rule_input.stairwell_count
        >= ruleset.parameters.staircase_exception_min_count
    ):
        return False
    return True


def _evaluate_evacuation(
    evaluation: _Evaluation, rule_input: RuleInput, ruleset: Ruleset
) -> None:
    """R-EVAC-01 — 대피공간 확보 (건축법 시행령 §46④ + 면제 스코핑).

    저층(3층 이하)·계단실 2개소 이상·경량칸막이 보유 중 하나면 별도 대피공간이
    불필요하다. 모두 아닌데 대피공간/경량칸막이도 확인되지 않으면 WARN + 추가 확인.
    """

    assert rule_input.floor_count is not None
    if rule_input.floor_count < ruleset.parameters.evacuation_space_min_floor:
        return  # 저층 — 별도 대피공간 불필요.

    if not _evacuation_required(rule_input, ruleset):
        # 4층 이상이지만 계단실 2개소 이상으로 별도 대피공간이 면제될 가능성.
        evaluation.legal_basis.add(LEGAL_FIRE_DOOR_STAIRCASE_EXCEPTION)
        evaluation.reasons.append(
            "이용 가능한 직통계단(계단실)이 2개소 이상으로 확인되어, 별도 "
            "대피공간을 구획하지 않아도 될 가능성이 있습니다."
        )
        return

    if rule_input.has_evacuation_space is True:
        evaluation.legal_basis.add(LEGAL_EVACUATION_SPACE)
        evaluation.reasons.append(
            "대피공간(또는 경량칸막이)이 확인되어 대피 경로 요건을 충족할 "
            "가능성이 있습니다."
        )
    else:
        # 대피공간 미확보 — 확장 자체가 불가능한 것은 아니고 대체 시설
        # (경량칸막이·하향식 피난구 등) 설치로 충족할 수 있어, 불가 단정
        # 대신 WARN + 추가 확인으로 분기한다 (보수 분기).
        evaluation.warn = True
        evaluation.legal_basis.add(LEGAL_EVACUATION_SPACE)
        evaluation.reasons.append(
            "4층 이상 세대는 발코니 확장 시 대피공간 등 대피 경로 확보가 "
            "필요한데, 현재 정보로는 확인되지 않았습니다."
        )
        evaluation.additional_checks.append(
            "대피공간·경량칸막이 등 대체 대피 경로 확보 방안을 확인해 "
            "주세요. 직통계단이 2개소 이상이면 별도 대피공간 없이도 가능할 수 "
            "있습니다."
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
    assert rule_input.floor_count is not None
    assert rule_input.has_sprinkler is not None
    assert rule_input.stairwell_count is not None
    assert rule_input.window_form is not None

    is_first_floor = rule_input.floor_count <= params.first_floor_exception_max_floor
    sprinkler = rule_input.has_sprinkler

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
    elif rule_input.floor_count >= params.fire_spread_guard_min_floor and not sprinkler:
        evaluation.legal_basis.add(LEGAL_FIRE_SPREAD_GUARD)
        if rule_input.window_form is WindowForm.FIXED:
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
            # OPENABLE/FOLDING/SLIDING/OTHER — 비고정형은 방화판 기준 산출.
            evaluation.facilities.append(
                RequiredFacility(
                    facility=FacilityType.FIRE_PANEL,
                    label="방화판",
                    location="아래층 세대와 접하는 발코니 창호 하부 외벽",
                    quantity_unit="m (가로 길이)",
                    legal_basis=LEGAL_FIRE_SPREAD_GUARD,
                    note="비고정형(여닫이·접이·미닫이 등) 창호 기준 산출",
                )
            )

    # ── 방화문 (R-FIRE-04) — 대피공간 출입구 (자동 닫힘 구조).
    # 대피공간이 **실제로 필요하고(_evacuation_required) 확보된 경우에만** 그 출입구에
    # 산출한다. 1층 예외, 그리고 계단실 2개소 이상 면제(대피공간 자체가 불필요)이면
    # 방화문도 불필요하다 — 면제 판단은 _evacuation_required 가 단일 소유한다(중복 분기 제거).
    if (
        not is_first_floor
        and _evacuation_required(rule_input, ruleset)
        and rule_input.has_evacuation_space is True
    ):
        evaluation.legal_basis.add(LEGAL_FIRE_DOOR)
        evaluation.facilities.append(
            RequiredFacility(
                facility=FacilityType.FIRE_DOOR,
                label="방화문(대피공간 출입구)",
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


def _build_user_message(verdict: Verdict, unconfirmed: tuple[str, ...]) -> str:
    """판정별 기본 문구에 미확인 항목 안내를 한 줄로 덧붙인다(리포트에 첨부 — 운영 스코핑).

    엄격한 rule-eval-result 계약을 건드리지 않고 미확인 항목을 사용자에게 노출하는
    채널이다(리포트 화면이 user_message 를 그대로 보여 준다).
    """

    base = _USER_MESSAGES[verdict]
    if unconfirmed:
        labels = ", ".join(_UNCONFIRMED_FIELD_NAMES[name] for name in unconfirmed)
        base += (
            f" 다만 {labels}은(는) 확인되지 않아 보수적으로 가정했어요 — 현장 확인 시 "
            "결과가 달라질 수 있어요."
        )
    return base


def evaluate(rule_input: RuleInput, ruleset: Ruleset = BASELINE_RULESET) -> RuleVerdict:
    """공통 판단 스키마 입력을 평가해 :class:`RuleVerdict` 를 산출한다.

    순수·결정적 함수 — 동일 ``(rule_input, ruleset)`` 에 대해 항상 동일한 결과를
    반환한다 (NFR-QUAL-002).

    스코핑(운영자 결정 2026-06-26):
    - **실내 비내력벽 철거(발코니 확장 아님 = balcony_attached False)** 는 발코니 확장
      방화시설·대피공간 룰을 **적용하지 않는다** — 구조/행위허가 위주.
    - **발코니 확장** 경로에서 안전 변수(층수·스프링클러·대피공간·계단실·창호·방화구획)가
      미확인이면 HOLD 로 막지 않고 **보수적 기본값으로 가정 + 미확인 caveat 첨부**.
    - **벽 종류(wall_type)만** 미상이면 HOLD — 철거 가능성 판단의 전제이기 때문.
    """

    evaluation = _Evaluation()
    unconfirmed: tuple[str, ...] = ()

    # 1단계 — 벽체 판정. 내력벽이 확인되면 다른 변수와 무관하게 DENY (R-WALL-01).
    _evaluate_wall(evaluation, rule_input)

    if evaluation.deny:
        pass  # 내력벽 → DENY 확정.
    elif _hold_for_unknown_wall(evaluation, rule_input):
        pass  # 벽 종류 미상 → HOLD (유일한 HOLD 전제).
    else:
        # 방화구획(fire_zone)은 발코니 확장/실내 철거와 **무관하게** 철거 부위가 방화구획에
        # 포함되면 자동 판단 불가(RULE_EXCEPTION)다 — 실내 철거 분기보다 먼저 본다(#fire-zone-
        # before-interior). 미확인(None)·미포함(False)이면 통과하고, 확장 경로의 미확인은
        # 아래에서 보수적 가정 + caveat 로 첨부한다.
        _evaluate_fire_zone(evaluation, rule_input)
        if evaluation.hold_reasons:
            pass  # 방화구획 포함(RULE_EXCEPTION) → 이후 평가 스킵, HOLD.
        elif rule_input.balcony_attached is False:
            # 발코니 확장이 아닌 실내 비내력벽 철거 — 확장 화재안전 룰 미적용.
            evaluation.legal_basis.add(LEGAL_WALL_NON_LOAD_BEARING)
            evaluation.reasons.append(
                "발코니 확장이 아닌 세대 내부 비내력벽 철거로 보입니다. 이 경우 발코니 "
                "확장에 따른 방화판·방화유리·대피공간 요건은 해당되지 않으며, 구조 안전과 "
                "행위허가 절차를 중심으로 확인하면 됩니다."
            )
        else:
            # 발코니 확장 경로 — 미확인 안전 변수를 보수적 기본값으로 채우고 caveat 로 첨부.
            overrides: dict[str, object] = {}
            defaulted: list[str] = []
            for field_name, default in _CONSERVATIVE_DEFAULTS.items():
                if getattr(rule_input, field_name) is None:
                    overrides[field_name] = default
                    defaulted.append(field_name)
            effective = replace(rule_input, **overrides) if overrides else rule_input
            unconfirmed = tuple(defaulted)

            if rule_input.balcony_attached is None:
                evaluation.reasons.append(
                    "발코니 확장(발코니 접합) 여부가 확인되지 않아, 보수적으로 발코니 확장 "
                    "기준으로 검토했습니다."
                )

            # fire_zone 은 분기 전에 이미 평가했다(미확인이면 통과). 나머지 안전 변수만 평가.
            _evaluate_evacuation(evaluation, effective, ruleset)
            _evaluate_facilities(evaluation, effective, ruleset)

            for field_name in defaulted:
                evaluation.additional_checks.append(
                    _UNCONFIRMED_CHECK_LABELS[field_name]
                )

    verdict = _aggregate_verdict(evaluation)
    # 보수적 가정이 섞였으면 확정(ALLOW) 대신 '추가 확인 필요(WARN)' 로 낮춘다.
    if verdict is Verdict.ALLOW and unconfirmed:
        verdict = Verdict.WARN

    permit = _permit_requirement(verdict)
    if verdict is not Verdict.HOLD:
        evaluation.legal_basis.add(LEGAL_PERMIT_PROCEDURE)

    return RuleVerdict(
        verdict=verdict,
        permit_requirement=permit,
        possibility_label=_POSSIBILITY_LABELS[verdict],
        user_message=_build_user_message(verdict, unconfirmed),
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

    공통 판단 스키마(§5.2)의 ``judgment_values`` 필드(캐노니컬 계약 필드명)
    에 호출자가 ``wall_type``/``fire_zone`` 컨텍스트 키를 병합해 넘긴다.
    라우터에 노출하지 않는 내부 서비스 함수다.
    """

    return evaluate(RuleInput.from_judgment_values(judgment_values), ruleset)
