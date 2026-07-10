"""예상 견적 산출(REPORT-003) 테스트 — services.estimate.compute_estimate.

출력은 estimate-result.schema.json(1.1.0) 계약 정본 shape 다 — 생성된 pydantic 모델
(zippin_contracts.estimate_result)로 캐노니컬 검증한다(MEMORY: contracts 스키마가
인터페이스 정본).
"""

from __future__ import annotations

import sys
from pathlib import Path

from src.services.estimate import compute_estimate

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "packages" / "contracts" / "python"))
from zippin_contracts.estimate_result import EstimateResult  # noqa: E402


def _rule_result(
    *, verdict: str, permit_required: bool, facility_codes: list[str]
) -> dict:
    return {
        "verdict": verdict,
        "permit_required": permit_required,
        "required_facilities": [{"code": c, "label": c} for c in facility_codes],
    }


def test_allow_with_permit_and_fire_panel_matches_contract() -> None:
    est = compute_estimate(
        _rule_result(
            verdict="ALLOW", permit_required=True, facility_codes=["FIRE_PANEL"]
        )
    )
    assert est is not None
    EstimateResult.model_validate(est)  # 계약 정본 shape 검증

    codes = [i["code"] for i in est["items"]]
    assert codes == ["PERMIT_AGENCY", "RESIDENT_CONSENT", "FIRE_PANEL"]
    # 합산 범위 = 행위허가 330k(정액) + 동의서 165k~330k + 방화판 120k~240k (전제 기반).
    assert est["total_range"]["min"] == 330_000 + 165_000 + 120_000
    assert est["total_range"]["max"] == 330_000 + 330_000 + 240_000
    assert est["total_range"]["currency"] == "KRW"
    # 계약 명명 필드 — 행위허가/방화판 MoneyRange.
    assert est["permit_agency_fee_estimate"]["min"] == 330_000
    assert est["fire_panel_estimate"] == {
        "currency": "KRW",
        "min": 120_000,
        "max": 240_000,
        "basis": "가로 길이 2.4~4.8m 가정 × 50,000원/m",
    }
    # 길이 전제가 assumptions 로 명시된다.
    assert any("2.4" in a for a in est["assumptions"])
    # 미산정 항목이 없으므로 상담 필수는 아니다.
    assert est["consultation_required"] is False
    assert est["policy_version"]
    assert est["source_url"] == "/faq?category=cost"
    assert est["vat_included"] is True


def test_warn_is_estimable() -> None:
    est = compute_estimate(
        _rule_result(verdict="WARN", permit_required=True, facility_codes=[])
    )
    assert est is not None
    EstimateResult.model_validate(est)
    assert est["total_range"]["min"] == 495_000
    assert est["total_range"]["max"] == 330_000 + 330_000
    assert est["consultation_required"] is False


def test_fire_glass_range_and_unpriced_items_require_consultation() -> None:
    est = compute_estimate(
        _rule_result(
            verdict="ALLOW",
            permit_required=True,
            facility_codes=["FIRE_GLASS", "AUTOMATIC_DOOR_CLOSER", "FIRE_DETECTOR"],
        )
    )
    assert est is not None
    EstimateResult.model_validate(est)
    by_code = {i["code"]: i for i in est["items"]}
    # 방화유리는 m당 143,000원 — 길이 전제(2.4~4.8m)로 범위 산정.
    assert by_code["FIRE_GLASS"]["unit_amount"] == 143_000
    assert by_code["FIRE_GLASS"]["amount_min"] == int(143_000 * 2.4)
    assert by_code["FIRE_GLASS"]["amount_max"] == int(143_000 * 4.8)
    assert est["fire_glass_estimate"]["min"] == int(143_000 * 2.4)
    # 방화문·화재감지기는 현장/별도 견적(금액 미산정) → 합산 제외 + 상담 권고.
    for code in ("FIRE_DOOR", "FIRE_DETECTOR"):
        assert by_code[code]["amount_min"] is None
        assert by_code[code]["unit_amount"] is None
    assert est["consultation_required"] is True
    assert est["variance_notes"]
    # 미산정 항목은 total_range 에 포함되지 않는다.
    assert est["total_range"]["max"] == 330_000 + 330_000 + int(143_000 * 4.8)


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
