"""RULE 룰엔진 결정론·분기·계약 정합 테스트 (CMP-DIRECT).

네 층위로 NFR-QUAL-002(동일 입력 결정성 100%)와 계약 정합을 고정한다:

1. 대표 corpus — 모든 규칙 분기를 덮는 입력을 2회 평가해 canonical JSON
   동일성을 단언한다.
2. 누락/비정상 edge — 규칙이 소비하는 필드가 빠지면 추측 없이 보류(HOLD +
   INSUFFICIENT_DATA)로 분류되고, 판정 미사용 필드(optional)는 누락이어도
   보류가 아님을 property-style 로 확인한다 (NFR-QUAL-003).
3. 계약 정합 — 입력은 ``common-judgment-schema.schema.json`` 의
   ``JudgmentValues`` 캐노니컬 필드명을, 출력은 ``rule-eval-result.schema.json``
   (생성된 zippin_contracts pydantic 모델로 검증)을 따른다.
4. golden snapshot — 베이스라인 룰셋의 corpus 출력 전체(캐노니컬
   RuleEvalResult + 내부 상세)를 ``tests/golden/rule_engine_baseline.json``
   과 비교한다. 룰 변경은 golden diff 로 리뷰 가능해야 한다. 갱신은
   ``RULE_GOLDEN_UPDATE=1 uv run pytest tests/test_rule_engine.py`` 로 한다.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.services.rule_engine import (
    _FACILITY_CONTRACT_CODES,
    CONTEXT_FIELDS,
    JUDGMENT_VALUE_FIELDS,
    RULE_EVAL_RESULT_SCHEMA_VERSION,
    FacilityType,
    HoldReason,
    PermitRequirement,
    RuleInput,
    RuleInputError,
    Verdict,
    WallType,
    WindowForm,
    evaluate,
    evaluate_judgment_values,
)
from src.services.rules import (
    BASELINE_RULESET,
    Ruleset,
    RulesetDefinitionError,
    RulesetParameters,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = Path(__file__).parent / "golden" / "rule_engine_baseline.json"
JUDGMENT_SCHEMA_PATH = (
    _REPO_ROOT
    / "packages"
    / "contracts"
    / "schemas"
    / "common-judgment-schema.schema.json"
)
RULE_EVAL_SCHEMA_PATH = (
    _REPO_ROOT / "packages" / "contracts" / "schemas" / "rule-eval-result.schema.json"
)

# 생성된 계약 pydantic 모델 (packages/contracts/python) — 추가 의존성 없이
# (pydantic 은 이미 런타임 의존성) 캐노니컬 출력 shape 를 검증한다.
sys.path.insert(0, str(_REPO_ROOT / "packages" / "contracts" / "python"))
from zippin_contracts.common_judgment_schema import (  # noqa: E402
    WallType as ContractWallType,
)
from zippin_contracts.common_judgment_schema import (  # noqa: E402
    WindowForm as ContractWindowForm,
)
from zippin_contracts.rule_eval_result import (  # noqa: E402
    Code as ContractFacilityCode,
)
from zippin_contracts.rule_eval_result import (  # noqa: E402
    RuleEvalResult as ContractRuleEvalResult,
)

#: 결정론 직렬화 검증용 고정 평가 시각 — evaluate() 는 시계를 갖지 않으므로
#: 호출자(테스트)가 주입한다 (NFR-QUAL-002).
FIXED_EVALUATED_AT = datetime(2026, 6, 11, 0, 0, 0, tzinfo=UTC)

#: 충분성(보류) 검사 대상 — 실제 규칙이 소비하는 필드 (엔진 _REQUIRED_FIELDS
#: 와 동일해야 한다). permit_history_known·balcony_attached 는 수집 대상이되
#: 판정 미사용이므로 누락이어도 보류가 아니다 (P2 수정).
REQUIRED_INPUT_FIELDS: tuple[str, ...] = (
    "wall_type",
    "floor_count",
    "has_sprinkler",
    "has_evacuation_space",
    "stairwell_count",
    "window_form",
    "fire_zone",
)
OPTIONAL_INPUT_FIELDS: tuple[str, ...] = ("balcony_attached", "permit_history_known")

# ---------------------------------------------------------------------------
# 대표 corpus — 모든 규칙 분기를 덮는다 (FR-RULE-004 수용 기준: 예외 케이스
# 단위 테스트). key 는 golden snapshot 의 case 이름이 된다.
# 필드명은 계약 JudgmentValues 정본 + 엔진 컨텍스트 키(wall_type/fire_zone).
# ---------------------------------------------------------------------------

_FULL_BASE: dict[str, object] = {
    "wall_type": "NON_LOAD_BEARING",
    "floor_count": 3,
    "has_sprinkler": False,
    "has_evacuation_space": True,
    "stairwell_count": 1,
    "window_form": "OPENABLE",
    "balcony_attached": True,
    "permit_history_known": False,
    "fire_zone": False,
}

CORPUS: dict[str, dict[str, object]] = {
    # 기본 ALLOW — 화재감지기 + 방화판 + 방화문 모두 필요.
    "allow_mid_floor_full_facilities": dict(_FULL_BASE),
    # 고정형(입면분할) 창호 → 방화판 대신 방화유리창.
    "allow_high_floor_fixed_window": {
        **_FULL_BASE,
        "floor_count": 5,
        "window_form": "FIXED",
    },
    # 자동 예외 — 스프링클러 살수범위 포함: 방화판·화재감지기 제외 (§2.8).
    "allow_sprinkler_exception": {
        **_FULL_BASE,
        "floor_count": 5,
        "has_sprinkler": True,
    },
    # 자동 예외 — 계단실 2개소 이상: 방화문 제외 (§2.8).
    "allow_staircase_exception": {
        **_FULL_BASE,
        "floor_count": 5,
        "stairwell_count": 2,
    },
    # 자동 예외 — 1층 세대: 화재감지기만 (§2.8).
    "allow_first_floor_exception": {**_FULL_BASE, "floor_count": 1},
    # 1층 + 스프링클러 → 필요 시설 없음.
    "allow_first_floor_sprinkler": {
        **_FULL_BASE,
        "floor_count": 1,
        "has_sprinkler": True,
    },
    # 4층 이상 + 대피공간 미확보 → WARN + 추가 확인, 방화문 산출 보류
    # (건축법 시행령 §46④ — 실재하지 않는 대피공간 출입구에 시설 산출 금지).
    "warn_no_evacuation_space_high_floor": {
        **_FULL_BASE,
        "floor_count": 4,
        "has_evacuation_space": False,
    },
    # 내력벽 — 다른 변수가 전부 누락이어도 DENY 확정 (R-WALL-01).
    "deny_load_bearing_only_wall_known": {"wall_type": "LOAD_BEARING"},
    # 내력벽 + 전체 입력 — 동일하게 DENY.
    "deny_load_bearing_full_input": {**_FULL_BASE, "wall_type": "LOAD_BEARING"},
    # 방화구획 포함 → RULE_EXCEPTION 보류 + 이후 평가 중단 (보수 분기,
    # CHAT-004) — 수동 검토 케이스에는 시설 목록을 산출하지 않는다.
    "hold_fire_zone": {**_FULL_BASE, "fire_zone": True},
    # 전체 누락 → INSUFFICIENT_DATA 보류 + 규칙 소비 7개 항목 안내
    # (판정 미사용 optional 필드는 안내하지 않는다).
    "hold_all_missing": {},
    # 벽체 종류만 누락 → 보류 (DENY 판단 자체가 불가).
    "hold_missing_wall_type": {
        key: value for key, value in _FULL_BASE.items() if key != "wall_type"
    },
    # 허용 어휘 밖의 값 → 추측 없이 보류 + 해당 항목 재확인 요청.
    "hold_invalid_values": {
        **_FULL_BASE,
        "wall_type": "concrete??",
        "has_sprinkler": 1,
        "floor_count": 0,
    },
}


def _evaluate_corpus() -> dict[str, dict[str, object]]:
    snapshot: dict[str, dict[str, object]] = {}
    for name, values in CORPUS.items():
        verdict = evaluate_judgment_values(values)
        snapshot[name] = {
            "rule_eval_result": verdict.to_contract_dict(
                evaluated_at=FIXED_EVALUATED_AT
            ),
            "internal": verdict.to_dict(),
        }
    return snapshot


# ---------------------------------------------------------------------------
# 1. 결정론 — 동일 입력 2회 평가 결과가 직렬화 수준에서 동일 (NFR-QUAL-002)
# ---------------------------------------------------------------------------


def test_corpus_is_deterministic_across_repeated_runs():
    first = json.dumps(_evaluate_corpus(), ensure_ascii=False, sort_keys=True)
    second = json.dumps(_evaluate_corpus(), ensure_ascii=False, sort_keys=True)
    assert first == second


def test_input_dict_key_order_does_not_change_result():
    forward = evaluate_judgment_values(dict(_FULL_BASE))
    reordered = evaluate_judgment_values(dict(reversed(list(_FULL_BASE.items()))))
    assert forward.to_canonical_json() == reordered.to_canonical_json()


def test_evaluate_does_not_mutate_input():
    rule_input = RuleInput.from_judgment_values(_FULL_BASE)
    before = rule_input
    evaluate(rule_input)
    evaluate(rule_input)
    assert rule_input == before  # frozen dataclass — 평가가 입력을 바꾸지 않음


# ---------------------------------------------------------------------------
# 2. 입력 계약 정합 — JudgmentValues 캐노니컬 필드명 (CMP-527 정본)
# ---------------------------------------------------------------------------


def test_parser_field_names_match_judgment_values_contract():
    """엔진이 소비하는 judgment 필드명 == 계약 JudgmentValues properties."""

    schema = json.loads(JUDGMENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    contract_fields = set(schema["$defs"]["JudgmentValues"]["properties"])
    assert set(JUDGMENT_VALUE_FIELDS) == contract_fields


def test_fully_populated_contract_payload_evaluates_without_hold():
    """계약 필드가 전부 채워지면 보류 없이 판정이 나와야 한다 (P1 수정)."""

    payload: dict[str, object] = {
        "floor_count": 5,
        "has_sprinkler": False,
        "has_evacuation_space": True,
        "stairwell_count": 1,
        "window_form": "SLIDING",
        "balcony_attached": True,
        "permit_history_known": True,
        # 엔진 컨텍스트 — wall_objects/selected_walls 분석에서 병합되는 키.
        "wall_type": "NON_LOAD_BEARING",
        "fire_zone": False,
    }
    assert set(payload) == set(JUDGMENT_VALUE_FIELDS) | set(CONTEXT_FIELDS)

    parsed = RuleInput.from_judgment_values(payload)
    assert parsed.invalid_fields == ()
    assert parsed.missing_fields() == ()

    result = evaluate(parsed).to_dict()
    assert result["verdict"] != Verdict.HOLD.value
    assert result["hold_reasons"] == []


def test_unknown_keys_are_rejected_like_additional_properties_false():
    """계약 additionalProperties=false 와 동일 — 옛 필드명도 거절된다."""

    with pytest.raises(RuleInputError, match="floor_number"):
        RuleInput.from_judgment_values({**_FULL_BASE, "floor_number": 3})
    with pytest.raises(RuleInputError):
        RuleInput.from_judgment_values({"sprinkler_coverage": True})


# ---------------------------------------------------------------------------
# 3. 분기 검증 — 자동 예외 조건 (FR-RULE-004) 및 판정 어휘 (RULE-003)
# ---------------------------------------------------------------------------


def _facility_types(result) -> list[str]:
    return [f["facility"] for f in result["required_facilities"]]


def test_allow_full_facilities():
    # _FULL_BASE 는 3층(저층)이라 대피공간·방화문은 불필요(v2 스코핑) — 감지기+방화판만.
    result = evaluate_judgment_values(_FULL_BASE).to_dict()
    assert result["verdict"] == "ALLOW"
    assert result["permit_requirement"] == "PERMIT_REQUIRED"
    assert _facility_types(result) == [
        FacilityType.FIRE_DETECTOR.value,
        FacilityType.FIRE_PANEL.value,
    ]
    # FR-RULE-006 — 결론 카드마다 근거 1개 이상.
    assert result["legal_basis"]
    for facility in result["required_facilities"]:
        assert facility["legal_basis"]["section"]


def test_high_floor_full_facilities_includes_fire_door():
    # 5층 + 대피공간 확보 → 감지기+방화판+방화문 (4층 이상 대피공간 출입구 방화문).
    result = evaluate_judgment_values({**_FULL_BASE, "floor_count": 5}).to_dict()
    assert result["verdict"] == "ALLOW"
    assert _facility_types(result) == [
        FacilityType.FIRE_DETECTOR.value,
        FacilityType.FIRE_PANEL.value,
        FacilityType.FIRE_DOOR.value,
    ]


def test_interior_wall_removal_skips_fire_safety():
    # 발코니 확장 아님(balcony_attached=False) → 화재안전 룰 미적용, 시설 0, 가능성 ALLOW.
    result = evaluate_judgment_values(
        {"wall_type": "NON_LOAD_BEARING", "balcony_attached": False}
    ).to_dict()
    assert result["verdict"] == "ALLOW"
    assert result["required_facilities"] == []
    assert result["hold_reasons"] == []
    assert any("내부 비내력벽" in r for r in result["reasons"])


def test_interior_wall_removal_load_bearing_still_denies():
    # 실내 철거여도 내력벽이면 DENY (벽체 판정은 분기와 무관).
    result = evaluate_judgment_values(
        {"wall_type": "LOAD_BEARING", "balcony_attached": False}
    ).to_dict()
    assert result["verdict"] == "DENY"


def test_interior_wall_in_fire_zone_holds():
    # 실내 철거여도 방화구획 포함이면 자동 판단 불가(RULE_EXCEPTION) — 실내 분기보다
    # 방화구획 판정이 먼저다(#fire-zone-before-interior).
    result = evaluate_judgment_values(
        {"wall_type": "NON_LOAD_BEARING", "balcony_attached": False, "fire_zone": True}
    ).to_dict()
    assert result["verdict"] == "HOLD"
    assert HoldReason.RULE_EXCEPTION.value in result["hold_reasons"]


def test_staircase_two_exempts_evacuation_space():
    # 계단실 2개소 이상 → 4층 이상이어도 별도 대피공간/방화문 불필요(v2).
    result = evaluate_judgment_values(
        {
            **_FULL_BASE,
            "floor_count": 5,
            "stairwell_count": 2,
            "has_evacuation_space": False,
        }
    ).to_dict()
    assert FacilityType.FIRE_DOOR.value not in _facility_types(result)
    # 대피공간 미확보 WARN 이 뜨지 않는다(계단실로 면제).
    assert result["verdict"] != "WARN" or all(
        "대피공간" not in c for c in result["additional_checks"]
    )
    rule_ids = [b["rule_id"] for b in result["legal_basis"]]
    assert "R-FIRE-05" in rule_ids  # 직통계단 2개소 예외 근거


def test_fixed_window_requires_fire_glass_instead_of_panel():
    result = evaluate_judgment_values(CORPUS["allow_high_floor_fixed_window"]).to_dict()
    types = _facility_types(result)
    assert FacilityType.FIRE_GLASS.value in types
    assert FacilityType.FIRE_PANEL.value not in types


@pytest.mark.parametrize("window_form", ["OPENABLE", "FOLDING", "SLIDING", "OTHER"])
def test_non_fixed_window_forms_map_to_fire_panel(window_form: str):
    result = evaluate_judgment_values(
        {**_FULL_BASE, "window_form": window_form}
    ).to_dict()
    types = _facility_types(result)
    assert FacilityType.FIRE_PANEL.value in types
    assert FacilityType.FIRE_GLASS.value not in types


def test_sprinkler_exception_removes_detector_and_spread_guard():
    result = evaluate_judgment_values(CORPUS["allow_sprinkler_exception"]).to_dict()
    types = _facility_types(result)
    assert FacilityType.FIRE_DETECTOR.value not in types
    assert FacilityType.FIRE_PANEL.value not in types
    assert FacilityType.FIRE_GLASS.value not in types
    assert types == [FacilityType.FIRE_DOOR.value]


def test_staircase_exception_removes_fire_door():
    result = evaluate_judgment_values(CORPUS["allow_staircase_exception"]).to_dict()
    assert FacilityType.FIRE_DOOR.value not in _facility_types(result)


def test_first_floor_exception_keeps_only_detector():
    result = evaluate_judgment_values(CORPUS["allow_first_floor_exception"]).to_dict()
    assert _facility_types(result) == [FacilityType.FIRE_DETECTOR.value]


def test_first_floor_with_sprinkler_requires_nothing():
    result = evaluate_judgment_values(CORPUS["allow_first_floor_sprinkler"]).to_dict()
    assert _facility_types(result) == []
    assert result["verdict"] == "ALLOW"


def test_high_floor_without_evacuation_space_warns_without_fire_door():
    """대피공간 미확보(4층+, 계단실 1개) 시 방화문을 산출하지 않고 WARN 으로 안내."""

    result = evaluate_judgment_values(
        CORPUS["warn_no_evacuation_space_high_floor"]
    ).to_dict()
    assert result["verdict"] == "WARN"
    assert FacilityType.FIRE_DOOR.value not in _facility_types(result)
    assert any("대피" in check for check in result["additional_checks"])


def test_fire_door_added_only_with_confirmed_evacuation_space():
    confirmed = evaluate_judgment_values(
        {**_FULL_BASE, "floor_count": 5, "has_evacuation_space": True}
    ).to_dict()
    assert FacilityType.FIRE_DOOR.value in _facility_types(confirmed)

    unconfirmed = evaluate_judgment_values(
        {**_FULL_BASE, "floor_count": 5, "has_evacuation_space": False}
    ).to_dict()
    assert FacilityType.FIRE_DOOR.value not in _facility_types(unconfirmed)


def test_load_bearing_wall_denies_even_with_missing_fields():
    result = evaluate_judgment_values(
        CORPUS["deny_load_bearing_only_wall_known"]
    ).to_dict()
    assert result["verdict"] == "DENY"
    assert result["hold_reasons"] == []
    assert result["required_facilities"] == []


def test_fire_zone_holds_and_short_circuits_remaining_rules():
    """P2 수정 — RULE_EXCEPTION 보류 시 시설·대피 평가를 건너뛴다."""

    result = evaluate_judgment_values(CORPUS["hold_fire_zone"]).to_dict()
    assert result["verdict"] == "HOLD"
    assert HoldReason.RULE_EXCEPTION.value in result["hold_reasons"]
    assert result["permit_requirement"] == PermitRequirement.UNDETERMINED.value
    # 수동 검토 케이스 — 실행 가능한 시설 목록을 산출하지 않는다.
    assert result["required_facilities"] == []
    # 시설 평가가 돌지 않았으므로 R-FIRE 근거도 누적되지 않는다.
    rule_ids = [basis["rule_id"] for basis in result["legal_basis"]]
    assert not any(rule_id.startswith("R-FIRE") for rule_id in rule_ids)
    assert "R-ZONE-01" in rule_ids


# ---------------------------------------------------------------------------
# 4. 누락/비정상 입력 — 추측 금지, 명시적 보류 (NFR-QUAL-003, FR-RULE-002)
# ---------------------------------------------------------------------------


def test_missing_wall_type_holds():
    # 벽 종류 미상은 철거 가능성 판단의 전제라 **유일하게 HOLD** 다.
    values = {k: v for k, v in _FULL_BASE.items() if k != "wall_type"}
    result = evaluate_judgment_values(values).to_dict()
    assert result["verdict"] == Verdict.HOLD.value
    assert HoldReason.INSUFFICIENT_DATA.value in result["hold_reasons"]
    assert result["required_facilities"] == []
    assert result["permit_requirement"] == PermitRequirement.UNDETERMINED.value


@pytest.mark.parametrize(
    "missing_field",
    [
        "floor_count",
        "has_sprinkler",
        "has_evacuation_space",
        "stairwell_count",
        "window_form",
        "fire_zone",
    ],
)
def test_missing_safety_field_is_conservative_not_hold(missing_field: str):
    # v2: 안전 변수 미확인은 HOLD 가 아니라 보수적 가정 + 미확인 caveat → WARN.
    values = {k: v for k, v in _FULL_BASE.items() if k != missing_field}
    result = evaluate_judgment_values(values).to_dict()
    assert result["verdict"] != Verdict.HOLD.value
    assert HoldReason.INSUFFICIENT_DATA.value not in result["hold_reasons"]
    # 미확인 항목이 추가 확인 목록에 첨부된다.
    assert result["additional_checks"]
    # 보수적 가정이 섞이면 확정(ALLOW) 대신 WARN 으로 낮춘다.
    assert result["verdict"] == Verdict.WARN.value
    assert result["user_message"] and "확인되지 않아" in result["user_message"]


@pytest.mark.parametrize("optional_field", sorted(OPTIONAL_INPUT_FIELDS))
def test_missing_optional_field_does_not_hold(optional_field: str):
    """P2 수정 — 판정 미사용 필드는 누락(None)이어도 보류가 아니다."""

    omitted = {k: v for k, v in _FULL_BASE.items() if k != optional_field}
    explicit_null = {**_FULL_BASE, optional_field: None}
    for values in (omitted, explicit_null):
        result = evaluate_judgment_values(values).to_dict()
        assert result["verdict"] != Verdict.HOLD.value
        assert result["hold_reasons"] == []


def test_required_field_set_matches_engine_and_contract():
    """테스트의 required/optional 분류 == 엔진 분류 == 계약 필드 전체."""

    assert set(REQUIRED_INPUT_FIELDS) | set(OPTIONAL_INPUT_FIELDS) == set(
        JUDGMENT_VALUE_FIELDS
    ) | set(CONTEXT_FIELDS)
    # 누락 보류는 required 만 트리거한다.
    all_missing = RuleInput.from_judgment_values({})
    assert set(all_missing.missing_fields()) == set(REQUIRED_INPUT_FIELDS)


def test_all_missing_holds_on_wall_type_only():
    # v2: 전부 누락이면 벽 종류 미상으로 HOLD 하고, 추가 확인은 벽 종류 1건만 묻는다
    # (나머지 안전 변수는 확장 경로의 보수적 가정 대상이라 HOLD 사유가 아니다).
    result = evaluate_judgment_values({}).to_dict()
    assert result["verdict"] == Verdict.HOLD.value
    assert len(result["additional_checks"]) == 1
    assert "내력벽" in result["additional_checks"][0]


def test_invalid_values_are_never_guessed():
    # bool 자리에 int, 알 수 없는 enum, 0층 — 전부 재확인 대상으로 강등.
    parsed = RuleInput.from_judgment_values(CORPUS["hold_invalid_values"])
    assert parsed.wall_type is None
    assert parsed.has_sprinkler is None
    assert parsed.floor_count is None
    assert parsed.invalid_fields == (
        "floor_count",
        "has_sprinkler",
        "wall_type",
    )
    result = evaluate(parsed).to_dict()
    assert result["verdict"] == Verdict.HOLD.value


def test_unknown_wall_type_vocabulary_is_demoted_not_guessed():
    # 계약 WallObject.wall_type 의 UNKNOWN — 보완 루프 트리거이므로 보류.
    parsed = RuleInput.from_judgment_values({**_FULL_BASE, "wall_type": "UNKNOWN"})
    assert parsed.wall_type is None
    assert "wall_type" in parsed.invalid_fields
    assert evaluate(parsed).verdict is Verdict.HOLD


def test_non_mapping_judgment_values_raise():
    with pytest.raises(RuleInputError):
        RuleInput.from_judgment_values(None)  # type: ignore[arg-type]


def test_enum_instances_accepted_same_as_strings():
    via_enum = evaluate(
        RuleInput.from_judgment_values(
            {
                **_FULL_BASE,
                "wall_type": WallType.NON_LOAD_BEARING,
                "window_form": WindowForm.OPENABLE,
            }
        )
    )
    via_str = evaluate(RuleInput.from_judgment_values(_FULL_BASE))
    assert via_enum.to_canonical_json() == via_str.to_canonical_json()


def test_generated_contract_enum_instances_accepted_same_as_strings():
    """P2 수정 — zippin_contracts 생성 모델의 plain Enum 인스턴스도 허용.

    호출자가 pydantic 모델 속성(예: ``judgment_values.window_form``)을
    그대로 병합해 넘기는 end-to-end 경로를 고정한다.
    """

    via_contract_enum = evaluate(
        RuleInput.from_judgment_values(
            {
                **_FULL_BASE,
                "wall_type": ContractWallType.NON_LOAD_BEARING,
                "window_form": ContractWindowForm.OPENABLE,
            }
        )
    )
    via_str = evaluate(RuleInput.from_judgment_values(_FULL_BASE))
    assert via_contract_enum.to_canonical_json() == via_str.to_canonical_json()
    # 캐노니컬 직렬화까지 동일해야 한다 (REPORT/스냅샷 경로).
    assert via_contract_enum.to_contract_dict(
        evaluated_at=FIXED_EVALUATED_AT
    ) == via_str.to_contract_dict(evaluated_at=FIXED_EVALUATED_AT)


def test_generated_contract_null_window_member_treated_as_missing():
    # 계약 WindowForm 의 null 멤버 — .value 가 None 이므로 미수집과 동일. v2 에선 창호
    # 미확인은 보수적 기본값(비고정형)으로 가정해 HOLD 가 아니라 WARN(미확인 caveat)이다.
    parsed = RuleInput.from_judgment_values(
        {**_FULL_BASE, "window_form": ContractWindowForm.NoneType_None}
    )
    assert parsed.window_form is None
    assert parsed.invalid_fields == ()
    assert evaluate(parsed).verdict is Verdict.WARN


def test_generated_contract_unknown_wall_type_instance_demoted():
    # 계약 WallType.UNKNOWN 인스턴스 — 문자열 "UNKNOWN" 과 동일하게 보류.
    parsed = RuleInput.from_judgment_values(
        {**_FULL_BASE, "wall_type": ContractWallType.UNKNOWN}
    )
    assert parsed.wall_type is None
    assert "wall_type" in parsed.invalid_fields
    assert evaluate(parsed).verdict is Verdict.HOLD


# ---------------------------------------------------------------------------
# 5. 출력 계약 정합 — RuleEvalResult 캐노니컬 직렬화 (CMP-527 정본)
# ---------------------------------------------------------------------------


def test_contract_dict_validates_against_rule_eval_result_contract():
    """모든 corpus 출력이 생성된 계약 모델(pydantic, extra=forbid)을 통과."""

    for name, values in CORPUS.items():
        payload = evaluate_judgment_values(values).to_contract_dict(
            evaluated_at=FIXED_EVALUATED_AT
        )
        validated = ContractRuleEvalResult.model_validate(payload)
        assert validated.schema_version == RULE_EVAL_RESULT_SCHEMA_VERSION, name


def test_fire_detector_serialized_canonically():
    """P1 수정 — 화재감지기(고시 §6)가 캐노니컬 직렬화에서 누락되지 않는다."""

    payload = evaluate_judgment_values(_FULL_BASE).to_contract_dict(
        evaluated_at=FIXED_EVALUATED_AT
    )
    codes = [item["code"] for item in payload["required_facilities"]]
    assert "FIRE_DETECTOR" in codes
    # 내부 시설 수 == 캐노니컬 시설 수 — 어떤 시설도 직렬화에서 빠지지 않는다.
    internal = evaluate_judgment_values(_FULL_BASE).to_dict()
    assert len(payload["required_facilities"]) == len(internal["required_facilities"])
    # 생성된 계약 모델(enum 포함)을 통과한다.
    validated = ContractRuleEvalResult.model_validate(payload)
    assert ContractFacilityCode.FIRE_DETECTOR in [
        item.code for item in validated.required_facilities
    ]


def test_every_engine_facility_type_has_contract_code():
    """엔진 FacilityType 전사가 계약 enum 으로 매핑된다 — 무단 누락 방지."""

    schema = json.loads(RULE_EVAL_SCHEMA_PATH.read_text(encoding="utf-8"))
    allowed = set(schema["$defs"]["RequiredFacility"]["properties"]["code"]["enum"])
    for facility_type in FacilityType:
        code = _FACILITY_CONTRACT_CODES[facility_type]
        assert code in allowed, facility_type


def test_contract_schema_version_matches_published_const():
    schema = json.loads(RULE_EVAL_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert (
        RULE_EVAL_RESULT_SCHEMA_VERSION
        == schema["properties"]["schema_version"]["const"]
    )


def test_contract_dict_shape_and_required_keys():
    schema = json.loads(RULE_EVAL_SCHEMA_PATH.read_text(encoding="utf-8"))
    payload = evaluate_judgment_values(_FULL_BASE).to_contract_dict(
        evaluated_at=FIXED_EVALUATED_AT
    )
    # required 키 전부 포함 + additionalProperties=false (정의된 키만).
    assert set(schema["required"]) <= set(payload)
    assert set(payload) <= set(schema["properties"])
    assert payload["schema_version"] == RULE_EVAL_RESULT_SCHEMA_VERSION
    assert isinstance(payload["permit_required"], bool)
    assert payload["evaluated_at"] == FIXED_EVALUATED_AT.isoformat()
    facility_codes = {item["code"] for item in payload["required_facilities"]}
    allowed_codes = set(
        schema["$defs"]["RequiredFacility"]["properties"]["code"]["enum"]
    )
    assert facility_codes <= allowed_codes


def test_permit_required_boolean_projection():
    allow = evaluate_judgment_values(_FULL_BASE)
    assert allow.permit_required is True
    hold = evaluate_judgment_values({})
    # UNDETERMINED(보류)는 보수적으로 True — 절차 필요 가능성을 숨기지 않는다.
    assert hold.permit_requirement is PermitRequirement.UNDETERMINED
    assert hold.permit_required is True


def test_contract_dict_rejects_naive_evaluated_at():
    verdict = evaluate_judgment_values(_FULL_BASE)
    with pytest.raises(ValueError, match="timezone-aware"):
        verdict.to_contract_dict(evaluated_at=datetime(2026, 6, 11))


def test_evaluate_stays_pure_evaluated_at_is_injected():
    """결정론 — evaluated_at 주입값만 바뀌고 나머지 결과는 불변 (시계 없음)."""

    verdict = evaluate_judgment_values(_FULL_BASE)
    later = datetime(2027, 1, 1, 12, 30, 0, tzinfo=UTC)
    first = verdict.to_contract_dict(evaluated_at=FIXED_EVALUATED_AT)
    second = verdict.to_contract_dict(evaluated_at=later)
    assert first.pop("evaluated_at") == FIXED_EVALUATED_AT.isoformat()
    assert second.pop("evaluated_at") == later.isoformat()
    assert first == second


# ---------------------------------------------------------------------------
# 6. 룰셋 버전/정의 로딩 (FR-RULE-001/007 — 버전 관리, 핫스왑 대비)
# ---------------------------------------------------------------------------


def test_ruleset_definition_round_trip():
    definition = BASELINE_RULESET.to_definition()
    loaded = Ruleset.from_definition(definition)
    assert loaded == BASELINE_RULESET


def test_ruleset_rejects_unknown_parameter_keys():
    definition = BASELINE_RULESET.to_definition()
    definition["parameters"]["typo_paramter"] = 3  # type: ignore[index]
    with pytest.raises(RulesetDefinitionError):
        Ruleset.from_definition(definition)


@pytest.mark.parametrize("field_name", ["version", "law_reference", "verified_on"])
def test_ruleset_requires_metadata(field_name: str):
    definition = BASELINE_RULESET.to_definition()
    definition[field_name] = "  "
    with pytest.raises(RulesetDefinitionError):
        Ruleset.from_definition(definition)


def test_parameter_override_changes_behavior_and_version_is_reported():
    # 대피공간 기준층을 2층으로 내린 가상 개정 룰셋 — 같은 입력이 WARN 으로.
    revised = Ruleset(
        version="2018-775.v2-test",
        law_reference=BASELINE_RULESET.law_reference,
        verified_on="2026-06-11",
        parameters=RulesetParameters(evacuation_space_min_floor=2),
    )
    values = {**_FULL_BASE, "has_evacuation_space": False}  # floor 3
    baseline = evaluate_judgment_values(values).to_dict()
    overridden = evaluate_judgment_values(values, revised).to_dict()
    assert baseline["verdict"] == Verdict.ALLOW.value
    assert overridden["verdict"] == Verdict.WARN.value
    assert overridden["ruleset_version"] == "2018-775.v2-test"


# ---------------------------------------------------------------------------
# 7. BRAND 어휘 가드 — 확정/보장형 표현 금지 (BRAND.md §4.4)
# ---------------------------------------------------------------------------

_FORBIDDEN_PHRASES = ("확정", "보장", "100%", "통과합니다", "철거 가능합니다")


def test_no_forbidden_brand_phrases_in_user_facing_text():
    for name, values in CORPUS.items():
        result = evaluate_judgment_values(values).to_dict()
        texts = [
            result["possibility_label"],
            result["user_message"],
            *result["reasons"],
            *result["additional_checks"],
        ]
        for text in texts:
            for phrase in _FORBIDDEN_PHRASES:
                assert phrase not in text, f"{name}: 금지 표현 '{phrase}' — {text}"


# ---------------------------------------------------------------------------
# 8. Golden snapshot — 룰 변경은 리뷰 가능한 diff 로 드러나야 한다
# ---------------------------------------------------------------------------


def test_baseline_ruleset_matches_golden_snapshot():
    actual = _evaluate_corpus()
    serialized = json.dumps(actual, ensure_ascii=False, sort_keys=True, indent=2) + "\n"

    if os.environ.get("RULE_GOLDEN_UPDATE") == "1":
        GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN_PATH.write_text(serialized, encoding="utf-8")

    assert (
        GOLDEN_PATH.exists()
    ), "golden snapshot 이 없습니다. RULE_GOLDEN_UPDATE=1 로 생성하세요."
    expected = GOLDEN_PATH.read_text(encoding="utf-8")
    assert serialized == expected, (
        "룰엔진 출력이 golden snapshot 과 다릅니다. 의도한 룰 변경이라면 "
        "룰셋 버전을 올리고 RULE_GOLDEN_UPDATE=1 로 snapshot 을 갱신한 뒤 "
        "diff 를 리뷰하세요."
    )
