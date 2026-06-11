"""RULE 룰엔진 결정론·분기 테스트 (CMP-DIRECT).

세 층위로 NFR-QUAL-002(동일 입력 결정성 100%)를 고정한다:

1. 대표 corpus — 모든 규칙 분기를 덮는 입력을 2회 평가해 canonical JSON
   동일성을 단언한다.
2. 누락/비정상 edge — 어떤 필드가 빠져도 추측 없이 보류(HOLD +
   INSUFFICIENT_DATA)로 분류되는지 property-style 로 확인한다 (NFR-QUAL-003).
3. golden snapshot — 베이스라인 룰셋의 corpus 출력 전체를
   ``tests/golden/rule_engine_baseline.json`` 과 비교한다. 룰 변경은 golden
   diff 로 리뷰 가능해야 한다. 갱신은 ``RULE_GOLDEN_UPDATE=1 uv run pytest
   tests/test_rule_engine.py`` 로 한다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from src.services.rule_engine import (
    FacilityType,
    HoldReason,
    PermitRequirement,
    RuleInput,
    RuleInputError,
    Verdict,
    WallType,
    WindowType,
    evaluate,
    evaluate_judgment_values,
)
from src.services.rules import (
    BASELINE_RULESET,
    Ruleset,
    RulesetDefinitionError,
    RulesetParameters,
)

GOLDEN_PATH = Path(__file__).parent / "golden" / "rule_engine_baseline.json"

# ---------------------------------------------------------------------------
# 대표 corpus — 모든 규칙 분기를 덮는다 (FR-RULE-004 수용 기준: 예외 케이스
# 단위 테스트). key 는 golden snapshot 의 case 이름이 된다.
# ---------------------------------------------------------------------------

_FULL_BASE: dict[str, object] = {
    "wall_type": "non_load_bearing",
    "floor_number": 3,
    "sprinkler_coverage": False,
    "exit_space_exists": True,
    "staircase_count": 1,
    "window_type": "operable",
    "fire_zone": False,
}

CORPUS: dict[str, dict[str, object]] = {
    # 기본 ALLOW — 화재감지기 + 방화판 + 방화문 모두 필요.
    "allow_mid_floor_full_facilities": dict(_FULL_BASE),
    # 고정형(입면분할) 창호 → 방화판 대신 방화유리창.
    "allow_high_floor_fixed_window": {
        **_FULL_BASE,
        "floor_number": 5,
        "window_type": "fixed",
    },
    # 자동 예외 — 스프링클러 살수범위 포함: 방화판·화재감지기 제외 (§2.8).
    "allow_sprinkler_exception": {
        **_FULL_BASE,
        "floor_number": 5,
        "sprinkler_coverage": True,
    },
    # 자동 예외 — 계단실 2개소 이상: 방화문 제외 (§2.8).
    "allow_staircase_exception": {
        **_FULL_BASE,
        "floor_number": 5,
        "staircase_count": 2,
    },
    # 자동 예외 — 1층 세대: 화재감지기만 (§2.8).
    "allow_first_floor_exception": {**_FULL_BASE, "floor_number": 1},
    # 1층 + 스프링클러 → 필요 시설 없음.
    "allow_first_floor_sprinkler": {
        **_FULL_BASE,
        "floor_number": 1,
        "sprinkler_coverage": True,
    },
    # 4층 이상 + 대피공간 미확보 → WARN + 추가 확인 (건축법 시행령 §46④).
    "warn_no_exit_space_high_floor": {
        **_FULL_BASE,
        "floor_number": 4,
        "exit_space_exists": False,
    },
    # 내력벽 — 다른 변수가 전부 누락이어도 DENY 확정 (R-WALL-01).
    "deny_load_bearing_only_wall_known": {"wall_type": "load_bearing"},
    # 내력벽 + 전체 입력 — 동일하게 DENY.
    "deny_load_bearing_full_input": {**_FULL_BASE, "wall_type": "load_bearing"},
    # 방화구획 포함 → RULE_EXCEPTION 보류 (보수 분기, CHAT-004).
    "hold_fire_zone": {**_FULL_BASE, "fire_zone": True},
    # 전체 누락 → INSUFFICIENT_DATA 보류 + 7개 항목 전부 안내.
    "hold_all_missing": {},
    # 벽체 종류만 누락 → 보류 (DENY 판단 자체가 불가).
    "hold_missing_wall_type": {
        key: value for key, value in _FULL_BASE.items() if key != "wall_type"
    },
    # 허용 어휘 밖의 값 → 추측 없이 보류 + 해당 항목 재확인 요청.
    "hold_invalid_values": {
        **_FULL_BASE,
        "wall_type": "concrete??",
        "sprinkler_coverage": 1,
        "floor_number": 0,
    },
}


def _evaluate_corpus() -> dict[str, dict[str, object]]:
    return {
        name: evaluate_judgment_values(values).to_dict()
        for name, values in CORPUS.items()
    }


# ---------------------------------------------------------------------------
# 1. 결정론 — 동일 입력 2회 평가 결과가 직렬화 수준에서 동일 (NFR-QUAL-002)
# ---------------------------------------------------------------------------


def test_corpus_is_deterministic_across_repeated_runs():
    first = {
        name: evaluate_judgment_values(values).to_canonical_json()
        for name, values in CORPUS.items()
    }
    second = {
        name: evaluate_judgment_values(values).to_canonical_json()
        for name, values in CORPUS.items()
    }
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
# 2. 분기 검증 — 자동 예외 조건 (FR-RULE-004) 및 판정 어휘 (RULE-003)
# ---------------------------------------------------------------------------


def _facility_types(result) -> list[str]:
    return [f["facility"] for f in result["required_facilities"]]


def test_allow_full_facilities():
    result = evaluate_judgment_values(_FULL_BASE).to_dict()
    assert result["verdict"] == "ALLOW"
    assert result["permit_requirement"] == "PERMIT_REQUIRED"
    assert _facility_types(result) == [
        FacilityType.FIRE_DETECTOR.value,
        FacilityType.FIRE_PANEL.value,
        FacilityType.FIRE_DOOR.value,
    ]
    # FR-RULE-006 — 결론 카드마다 근거 1개 이상.
    assert result["legal_basis"]
    for facility in result["required_facilities"]:
        assert facility["legal_basis"]["section"]


def test_fixed_window_requires_fire_glass_instead_of_panel():
    result = evaluate_judgment_values(CORPUS["allow_high_floor_fixed_window"]).to_dict()
    types = _facility_types(result)
    assert FacilityType.FIRE_GLASS.value in types
    assert FacilityType.FIRE_PANEL.value not in types


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


def test_high_floor_without_exit_space_warns():
    result = evaluate_judgment_values(CORPUS["warn_no_exit_space_high_floor"]).to_dict()
    assert result["verdict"] == "WARN"
    assert any("대피" in check for check in result["additional_checks"])


def test_load_bearing_wall_denies_even_with_missing_fields():
    result = evaluate_judgment_values(
        CORPUS["deny_load_bearing_only_wall_known"]
    ).to_dict()
    assert result["verdict"] == "DENY"
    assert result["hold_reasons"] == []
    assert result["required_facilities"] == []


def test_fire_zone_holds_with_rule_exception():
    result = evaluate_judgment_values(CORPUS["hold_fire_zone"]).to_dict()
    assert result["verdict"] == "HOLD"
    assert HoldReason.RULE_EXCEPTION.value in result["hold_reasons"]
    assert result["permit_requirement"] == PermitRequirement.UNDETERMINED.value


# ---------------------------------------------------------------------------
# 3. 누락/비정상 입력 — 추측 금지, 명시적 보류 (NFR-QUAL-003, FR-RULE-002)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_field", sorted(_FULL_BASE))
def test_any_single_missing_field_yields_explicit_hold(missing_field: str):
    values = {k: v for k, v in _FULL_BASE.items() if k != missing_field}
    result = evaluate_judgment_values(values).to_dict()
    assert result["verdict"] == Verdict.HOLD.value
    assert HoldReason.INSUFFICIENT_DATA.value in result["hold_reasons"]
    # 누락 항목이 추가 확인 목록에 명시된다 — 시설 추측 산출 금지.
    assert result["additional_checks"]
    assert result["required_facilities"] == []
    assert result["permit_requirement"] == PermitRequirement.UNDETERMINED.value


def test_all_missing_lists_every_required_field():
    result = evaluate_judgment_values({}).to_dict()
    assert result["verdict"] == Verdict.HOLD.value
    assert len(result["additional_checks"]) == len(_FULL_BASE)


def test_invalid_values_are_never_guessed():
    # bool 자리에 int, 알 수 없는 enum, 0층 — 전부 재확인 대상으로 강등.
    parsed = RuleInput.from_judgment_values(CORPUS["hold_invalid_values"])
    assert parsed.wall_type is None
    assert parsed.sprinkler_coverage is None
    assert parsed.floor_number is None
    assert parsed.invalid_fields == (
        "floor_number",
        "sprinkler_coverage",
        "wall_type",
    )
    result = evaluate(parsed).to_dict()
    assert result["verdict"] == Verdict.HOLD.value


def test_non_mapping_judgment_values_raise():
    with pytest.raises(RuleInputError):
        RuleInput.from_judgment_values(None)  # type: ignore[arg-type]


def test_enum_instances_accepted_same_as_strings():
    via_enum = evaluate(
        RuleInput.from_judgment_values(
            {
                **_FULL_BASE,
                "wall_type": WallType.NON_LOAD_BEARING,
                "window_type": WindowType.OPERABLE,
            }
        )
    )
    via_str = evaluate(RuleInput.from_judgment_values(_FULL_BASE))
    assert via_enum.to_canonical_json() == via_str.to_canonical_json()


# ---------------------------------------------------------------------------
# 4. 룰셋 버전/정의 로딩 (FR-RULE-001/007 — 버전 관리, 핫스왑 대비)
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
    values = {**_FULL_BASE, "exit_space_exists": False}  # floor 3
    baseline = evaluate_judgment_values(values).to_dict()
    overridden = evaluate_judgment_values(values, revised).to_dict()
    assert baseline["verdict"] == Verdict.ALLOW.value
    assert overridden["verdict"] == Verdict.WARN.value
    assert overridden["ruleset_version"] == "2018-775.v2-test"


# ---------------------------------------------------------------------------
# 5. BRAND 어휘 가드 — 확정/보장형 표현 금지 (BRAND.md §4.4)
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
# 6. Golden snapshot — 룰 변경은 리뷰 가능한 diff 로 드러나야 한다
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
