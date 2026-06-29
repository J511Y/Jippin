"""사전검토 예상 견적 산출 (REPORT-003, SDD §4.9 REPORT.estimate) — CMP-DIRECT.

룰 판정 결과(rule-eval-result)를 입력으로 사전검토 단계의 **예상 견적 범위**를 산출한다.
법적 판단은 RULE 이, 견적 계산은 본 모듈이 담당해 책임을 분리한다(SDD §4.9).

단가 정본은 운영 비용 안내(``/faq?category=cost``)의 단가표다 — 본 모듈의
``PRICING_POLICY`` 는 그 목록을 미러링한 정책 스냅샷이며, ``policy_version`` 으로 산정
시점을 기록하고 ``source_url`` 로 사용자에게 상세를 연결한다. 단가는 운영 정책에 따라
변경 가능하다(특허 출원 설명과 동일하게 고정값이 아니라 정책 단가표로 표현).

핵심 — 견적은 **확정 청구액이 아니라 예비 안내**다. 현장 치수(방화판 길이 등)가 없는
항목은 단가/별도견적으로만 표기하고 합산에서 제외하며, 모든 결과에 변동 안내를 단다.
순수 함수(시계·DB·네트워크 없음)이며 입력이 견적 비대상(불가/보류)이면 None 을 돌린다.
"""

from __future__ import annotations

from typing import Any

#: 단가 정책 버전 — /faq?category=cost 의 현행 단가표 스냅샷(VAT 포함).
PRICING_POLICY_VERSION = "2026-06"

#: 비용 안내 FAQ — 사용자가 단가 상세를 확인할 정본 링크.
PRICING_SOURCE_URL = "/faq?category=cost"

#: 견적을 내는 판정 — 가능(ALLOW)/조건부(WARN)만. 불가(DENY)·보류(HOLD)는 견적이
#: 무의미하거나 시기상조라 산출하지 않는다.
_ESTIMABLE_VERDICTS: frozenset[str] = frozenset({"ALLOW", "WARN"})


def _item(
    code: str,
    label: str,
    *,
    amount_min: int | None = None,
    unit_amount: int | None = None,
    unit: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """견적 항목 1건. ``amount_min`` 은 합산되는 고정 최소액(없으면 변동/별도견적)."""

    return {
        "code": code,
        "label": label,
        "amount_min": amount_min,
        "unit_amount": unit_amount,
        "unit": unit,
        "note": note,
    }


def compute_estimate(rule_eval_result: dict[str, Any] | None) -> dict[str, Any] | None:
    """rule-eval-result → 예상 견적(EstimateResult). 견적 비대상이면 None.

    /faq?category=cost 단가표 기반:
    - 행위허가 대행(기본 패키지) 330,000원 — permit_required 일 때.
    - 입주민 동의서 대행 165,000원~ — 행위허가 동반(동 50% 동의) 시.
    - 방화판 시공 50,000원/m~ — 필요 방화시설에 방화판(FIRE_PANEL)이 있을 때(길이 미정).
    - 방화유리 시공 143,000원/m~ — 필요 방화시설에 방화유리(FIRE_GLASS)가 있을 때(길이 미정).
    - 방화문(AUTOMATIC_DOOR_CLOSER)·화재감지기(FIRE_DETECTOR)는 현장/별도 견적
      안내 항목으로만(금액 미산정).
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
    if permit_required:
        items.append(
            _item(
                "PERMIT_AGENCY",
                "행위허가 대행 (기본 패키지)",
                amount_min=330_000,
                note="행위허가 접수·확장 전후 도면 수정·구조안전확인서·사용검사 신청 포함",
            )
        )
        items.append(
            _item(
                "RESIDENT_CONSENT",
                "입주민 동의서 대행",
                amount_min=165_000,
                note="120세대 이하 기준 — 세대 수가 많으면 증가할 수 있어요",
            )
        )

    if "FIRE_PANEL" in codes:
        items.append(
            _item(
                "FIRE_PANEL",
                "방화판 시공",
                unit_amount=50_000,
                unit="원/m",
                note="설치 길이에 따라 달라져요(현장 확인 후 산정)",
            )
        )
    if "FIRE_GLASS" in codes:
        items.append(
            _item(
                "FIRE_GLASS",
                "방화유리 시공",
                unit_amount=143_000,
                unit="원/m",
                note="설치 길이에 따라 달라져요(현장 확인 후 산정)",
            )
        )
    if "AUTOMATIC_DOOR_CLOSER" in codes:
        items.append(
            _item(
                "FIRE_DOOR",
                "대피공간 방화문",
                note="대피공간 출입구 자동닫힘 방화문 — 현장 견적으로 안내해 드려요",
            )
        )
    if "FIRE_DETECTOR" in codes:
        items.append(
            _item(
                "FIRE_DETECTOR",
                "화재감지기 설치",
                note="설치 개소에 따라 달라져요 — 현장 견적으로 안내해 드려요",
            )
        )

    if not items:
        return None

    fixed_total_min = sum(
        i["amount_min"] for i in items if isinstance(i.get("amount_min"), int)
    )
    has_variable_items = any(i.get("amount_min") is None for i in items)

    return {
        "policy_version": PRICING_POLICY_VERSION,
        "currency": "KRW",
        "vat_included": True,
        "source_url": PRICING_SOURCE_URL,
        "items": items,
        "fixed_total_min": fixed_total_min if fixed_total_min > 0 else None,
        "has_variable_items": has_variable_items,
        "disclaimer": (
            "현장 조건(면적·구조·세대 수)에 따라 달라질 수 있는 예상 범위예요. "
            "무료 상담 후 정확한 견적을 안내해 드려요."
        ),
    }
