"""예상 견적 산출(REPORT-003) 테스트 — services.estimate.compute_estimate."""

from __future__ import annotations

from src.services.estimate import compute_estimate


def _rule_result(
    *, verdict: str, permit_required: bool, facility_codes: list[str]
) -> dict:
    return {
        "verdict": verdict,
        "permit_required": permit_required,
        "required_facilities": [{"code": c, "label": c} for c in facility_codes],
    }


def test_allow_with_permit_and_fire_panel() -> None:
    est = compute_estimate(
        _rule_result(
            verdict="ALLOW", permit_required=True, facility_codes=["FIRE_PANEL"]
        )
    )
    assert est is not None
    codes = [i["code"] for i in est["items"]]
    assert codes == ["PERMIT_AGENCY", "RESIDENT_CONSENT", "FIRE_PANEL"]
    # 고정 합계 = 행위허가 330k + 동의서 165k.
    assert est["fixed_total_min"] == 495_000
    assert est["has_variable_items"] is True  # 방화판은 길이 미정(변동)
    panel = next(i for i in est["items"] if i["code"] == "FIRE_PANEL")
    assert panel["unit_amount"] == 50_000 and panel["amount_min"] is None
    assert est["source_url"] == "/faq?category=cost"
    assert est["vat_included"] is True


def test_warn_is_estimable() -> None:
    est = compute_estimate(
        _rule_result(verdict="WARN", permit_required=True, facility_codes=[])
    )
    assert est is not None
    assert est["fixed_total_min"] == 495_000
    assert est["has_variable_items"] is False


def test_fire_glass_and_door_are_quote_only() -> None:
    est = compute_estimate(
        _rule_result(
            verdict="ALLOW",
            permit_required=True,
            facility_codes=["FIRE_GLASS", "AUTOMATIC_DOOR_CLOSER", "FIRE_DETECTOR"],
        )
    )
    assert est is not None
    by_code = {i["code"]: i for i in est["items"]}
    for code in ("FIRE_GLASS", "FIRE_DOOR", "FIRE_DETECTOR"):
        assert by_code[code]["amount_min"] is None
    assert est["has_variable_items"] is True


def test_deny_returns_none() -> None:
    assert (
        compute_estimate(
            _rule_result(verdict="DENY", permit_required=True, facility_codes=[])
        )
        is None
    )


def test_hold_returns_none() -> None:
    assert (
        compute_estimate(
            _rule_result(verdict="HOLD", permit_required=False, facility_codes=[])
        )
        is None
    )


def test_no_permit_no_facilities_returns_none() -> None:
    # 가능 판정이지만 행위허가도 시설도 없으면 견적 항목이 없어 None.
    assert (
        compute_estimate(
            _rule_result(verdict="ALLOW", permit_required=False, facility_codes=[])
        )
        is None
    )


def test_malformed_input_returns_none() -> None:
    assert compute_estimate(None) is None
    assert compute_estimate({}) is None
    assert compute_estimate({"verdict": "ALLOW"}) is None  # permit 없음 → 항목 0
