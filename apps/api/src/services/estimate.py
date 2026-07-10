"""사전검토 예상 견적 산출 (REPORT-003, SDD §4.9 REPORT.estimate) — CMP-DIRECT.

룰 판정 결과(rule-eval-result)를 입력으로 사전검토 단계의 **예상 견적 범위**를 산출한다.
법적 판단은 RULE 이, 견적 계산은 본 모듈이 담당해 책임을 분리한다(SDD §4.9).

출력은 ``packages/contracts/schemas/estimate-result.schema.json``(1.1.0) 정본 shape 다 —
필수: schema_version/total_range/assumptions/policy_version/consultation_required,
표시용: items/vat_included/source_url/disclaimer. 현장 치수(방화판 길이 등)가 없는 항목은
**운영 전제(assumptions)** 로 범위를 만들고 그 전제를 결과에 명시한다(SDD §4.9 — 항목
미산정 시 총액 폭이 넓어질 수 있음). 전제조차 둘 수 없는 항목(방화문·감지기)은 합산에서
제외하고 variance_notes + consultation_required=true 로 상담을 권고한다
(PRICING_POLICY_MISSING 경로).

단가 정본은 운영 비용 안내(``/faq?category=cost``)의 단가표다 — 본 모듈의 단가는 그
목록을 미러링한 정책 스냅샷이며, ``policy_version`` 으로 산정 시점을 기록하고
``source_url`` 로 사용자에게 상세를 연결한다. 순수 함수(시계·DB·네트워크 없음)이며
입력이 견적 비대상(불가/보류)이면 None 을 돌린다.
"""

from __future__ import annotations

from typing import Any

#: estimate-result.schema.json 의 ``schema_version`` const.
ESTIMATE_RESULT_SCHEMA_VERSION = "1.1.0"

#: 단가 정책 버전 — /faq?category=cost 의 현행 단가표 스냅샷(VAT 포함).
PRICING_POLICY_VERSION = "2026-06"

#: 비용 안내 FAQ — 사용자가 단가 상세를 확인할 정본 링크.
PRICING_SOURCE_URL = "/faq?category=cost"

#: 견적을 내는 판정 — 가능(ALLOW)/조건부(WARN)만. 불가(DENY)·보류(HOLD)는 견적이
#: 무의미하거나 시기상조라 산출하지 않는다.
_ESTIMABLE_VERDICTS: frozenset[str] = frozenset({"ALLOW", "WARN"})

# --- 운영 전제(assumptions) — 치수 미수집 항목의 범위 산정 기준 ----------------
#: 방화판/방화유리 설치 길이 전제(m). 국내 아파트 발코니 창호 가로 폭의 통상 범위 —
#: 침실 발코니(약 2.4m)~대형 거실 발코니(약 4.8m). 현장 실측 전 예비 범위 산정용.
_FIRE_GUARD_LENGTH_MIN_M = 2.4
_FIRE_GUARD_LENGTH_MAX_M = 4.8
#: 입주민 동의서 대행 상한 배수 전제 — 기본 단가는 120세대 이하 기준이며, 세대 수가
#: 많으면 증가한다. 예비 범위 상한은 기본가의 2배로 가정한다.
_CONSENT_MAX_MULTIPLIER = 2

_LENGTH_ASSUMPTION = (
    f"방화판·방화유리 설치 길이는 발코니 창호 가로 {_FIRE_GUARD_LENGTH_MIN_M}m(침실)"
    f"~{_FIRE_GUARD_LENGTH_MAX_M}m(대형 거실)로 가정했어요 — 실측 후 달라질 수 있어요."
)
_CONSENT_ASSUMPTION = (
    "입주민 동의서 대행은 120세대 이하 기준 단가로 시작해, 세대 수가 많은 단지는 "
    "최대 2배까지로 가정했어요."
)


def _money_range(min_won: int, max_won: int, basis: str) -> dict[str, Any]:
    """계약 $defs/MoneyRange 1건."""

    return {"currency": "KRW", "min": min_won, "max": max_won, "basis": basis}


def _item(
    code: str,
    label: str,
    *,
    amount_min: int | None = None,
    amount_max: int | None = None,
    unit_amount: int | None = None,
    unit: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """견적 항목 1건 (계약 $defs/EstimateItem). amount 가 모두 None 이면 현장 견적."""

    return {
        "code": code,
        "label": label,
        "amount_min": amount_min,
        "amount_max": amount_max,
        "unit_amount": unit_amount,
        "unit": unit,
        "note": note,
    }


def compute_estimate(rule_eval_result: dict[str, Any] | None) -> dict[str, Any] | None:
    """rule-eval-result → 예상 견적(EstimateResult 계약 1.1.0). 견적 비대상이면 None.

    /faq?category=cost 단가표 기반:
    - 행위허가 대행(기본 패키지) 330,000원(정액) — permit_required 일 때.
    - 입주민 동의서 대행 165,000원~ — 행위허가 동반(동 50% 동의) 시. 상한은 2배 가정.
    - 방화판 시공 50,000원/m — FIRE_PANEL 필요 시. 길이는 2.4~4.8m 전제 범위.
    - 방화유리 시공 143,000원/m — FIRE_GLASS 필요 시. 길이는 2.4~4.8m 전제 범위.
    - 방화문(AUTOMATIC_DOOR_CLOSER)·화재감지기(FIRE_DETECTOR)는 현장/별도 견적
      항목(금액 미산정) — variance_notes + consultation_required=true.
    """

    if not isinstance(rule_eval_result, dict):
        return None
    verdict = rule_eval_result.get("verdict")
    if verdict not in _ESTIMABLE_VERDICTS:
        return None

    permit_required = bool(rule_eval_result.get("permit_required"))
    facilities = rule_eval_result.get("required_facilities")
    codes = {
        f.get("code")
        for f in (facilities if isinstance(facilities, list) else [])
        if isinstance(f, dict)
    }

    items: list[dict[str, Any]] = []
    assumptions: list[str] = []
    variance_notes: list[str] = []
    named_ranges: dict[str, dict[str, Any]] = {}

    if permit_required:
        permit_range = _money_range(
            330_000, 330_000, "행위허가 대행 기본 패키지 정액(330,000원)"
        )
        named_ranges["permit_agency_fee_estimate"] = permit_range
        items.append(
            _item(
                "PERMIT_AGENCY",
                "행위허가 대행 (기본 패키지)",
                amount_min=330_000,
                amount_max=330_000,
                note="행위허가 접수·확장 전후 도면 수정·구조안전확인서·사용검사 신청 포함",
            )
        )
        items.append(
            _item(
                "RESIDENT_CONSENT",
                "입주민 동의서 대행",
                amount_min=165_000,
                amount_max=165_000 * _CONSENT_MAX_MULTIPLIER,
                note="120세대 이하 기준 — 세대 수가 많으면 증가할 수 있어요",
            )
        )
        assumptions.append(_CONSENT_ASSUMPTION)

    fire_guard_used = False
    if "FIRE_PANEL" in codes:
        panel_min = int(50_000 * _FIRE_GUARD_LENGTH_MIN_M)
        panel_max = int(50_000 * _FIRE_GUARD_LENGTH_MAX_M)
        named_ranges["fire_panel_estimate"] = _money_range(
            panel_min,
            panel_max,
            f"가로 길이 {_FIRE_GUARD_LENGTH_MIN_M}~{_FIRE_GUARD_LENGTH_MAX_M}m 가정 "
            "× 50,000원/m",
        )
        items.append(
            _item(
                "FIRE_PANEL",
                "방화판 시공",
                amount_min=panel_min,
                amount_max=panel_max,
                unit_amount=50_000,
                unit="원/m",
                note="설치 길이 가정 범위 — 현장 실측 후 확정돼요",
            )
        )
        fire_guard_used = True
    if "FIRE_GLASS" in codes:
        glass_min = int(143_000 * _FIRE_GUARD_LENGTH_MIN_M)
        glass_max = int(143_000 * _FIRE_GUARD_LENGTH_MAX_M)
        named_ranges["fire_glass_estimate"] = _money_range(
            glass_min,
            glass_max,
            f"가로 길이 {_FIRE_GUARD_LENGTH_MIN_M}~{_FIRE_GUARD_LENGTH_MAX_M}m 가정 "
            "× 143,000원/m",
        )
        items.append(
            _item(
                "FIRE_GLASS",
                "방화유리 시공",
                amount_min=glass_min,
                amount_max=glass_max,
                unit_amount=143_000,
                unit="원/m",
                note="설치 길이 가정 범위 — 현장 실측 후 확정돼요",
            )
        )
        fire_guard_used = True
    if fire_guard_used:
        assumptions.append(_LENGTH_ASSUMPTION)

    unpriced_labels: list[str] = []
    if "AUTOMATIC_DOOR_CLOSER" in codes:
        items.append(
            _item(
                "FIRE_DOOR",
                "대피공간 방화문",
                note="대피공간 출입구 자동닫힘 방화문 — 현장 견적으로 안내해 드려요",
            )
        )
        unpriced_labels.append("대피공간 방화문")
    if "FIRE_DETECTOR" in codes:
        items.append(
            _item(
                "FIRE_DETECTOR",
                "화재감지기 설치",
                note="설치 개소에 따라 달라져요 — 현장 견적으로 안내해 드려요",
            )
        )
        unpriced_labels.append("화재감지기")

    if not items:
        return None

    priced = [i for i in items if isinstance(i.get("amount_min"), int)]
    total_min = sum(i["amount_min"] for i in priced)
    total_max = sum(
        i["amount_max"] if isinstance(i.get("amount_max"), int) else i["amount_min"]
        for i in priced
    )
    total_basis = (
        f"산정 가능 항목 {len(priced)}건 합산 (전제 기반 범위)"
        if priced
        else "산정 가능한 항목이 없어 범위를 내지 못했어요"
    )

    consultation_required = bool(unpriced_labels) or not priced
    if unpriced_labels:
        variance_notes.append(
            f"단가표에 없는 현장 견적 항목 {len(unpriced_labels)}건"
            f"({', '.join(unpriced_labels)})은 합산에서 제외했어요 — 상담으로 정확한 "
            "금액을 안내해 드려요."
        )

    return {
        "schema_version": ESTIMATE_RESULT_SCHEMA_VERSION,
        **named_ranges,
        "total_range": _money_range(total_min, total_max, total_basis),
        "assumptions": assumptions,
        "policy_version": PRICING_POLICY_VERSION,
        "variance_notes": variance_notes,
        "consultation_required": consultation_required,
        "items": items,
        "vat_included": True,
        "source_url": PRICING_SOURCE_URL,
        "disclaimer": (
            "현장 조건(면적·구조·세대 수)에 따라 달라질 수 있는 예상 범위예요. "
            "무료 상담 후 정확한 견적을 안내해 드려요."
        ),
    }
