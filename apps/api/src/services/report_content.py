"""사전검토 PDF 리포트의 **고정 안내 콘텐츠** (CMP-DIRECT).

리포트 PDF 에 들어가는 설명·일정·상담 안내 중 **판정과 무관하게 고정**인 문구를
한곳에 모은다. 정본은 ``/faq``([집핀] QnA) 의 답변들이며, 본 모듈은 그 내용을
리포트 톤으로 다듬은 스냅샷이다. 룰 판정에서 나온 ``required_facilities`` 코드별로
어떤 고정 설명을 보여줄지 매핑하고, 일정/상담은 통째로 고정값을 제공한다.

순수 모듈 — 시계·DB·네트워크 없음. URL 만 ``origin`` 인자로 절대경로를 만든다.
"""

from __future__ import annotations

from typing import Any

# ── 판정(verdict) 표기 ────────────────────────────────────────────────────────
# rule-eval-result.verdict → (라벨, 톤). 톤은 템플릿 CSS 클래스(tone-*)로 매핑된다.
_VERDICT_META: dict[str, tuple[str, str]] = {
    "ALLOW": ("철거 가능성 있음", "success"),
    "WARN": ("조건부 가능", "warning"),
    "HOLD": ("추가 확인 필요", "info"),
    "DENY": ("철거 어려움", "danger"),
}

# ── 벽체 종류(wall_type) 설명 ──────────────────────────────────────────────────
_WALL_TYPE_META: dict[str, dict[str, str]] = {
    "NON_LOAD_BEARING": {
        "label": "비내력벽(가벽) 후보",
        "tone": "success",
        "description": (
            "건물 하중을 직접 받지 않고 공간을 나누는 비내력벽으로 보여 "
            "철거 검토 대상이 됩니다. 다만 도면상 비내력벽으로 보여도 실제 "
            "시공·현장 조건에 따라 다를 수 있어, 최종 가부는 구조안전확인서로 "
            "확정합니다."
        ),
    },
    "LOAD_BEARING": {
        "label": "내력벽 후보",
        "tone": "danger",
        "description": (
            "위층·지붕·바닥의 무게를 떠받아 건물 기초로 전달하는 내력벽으로 "
            "보입니다. 구조를 지탱하는 벽이라 원칙적으로 철거할 수 없습니다."
        ),
    },
    "UNKNOWN": {
        "label": "추가 확인 필요",
        "tone": "info",
        "description": (
            "도면만으로는 내력벽/비내력벽을 단정하기 어려운 벽체입니다. "
            "전문가 정밀 검토로 종류를 확정한 뒤 철거 여부를 판단합니다."
        ),
    },
}

#: 내력벽 vs 비내력벽 차이 설명(리포트 도면 섹션 교육 박스). /faq?category=glossary 정본.
#: 사용자는 도면에서 비내력벽 후보만 선택할 수 있어, 개별 반복 설명 대신 차이를 보여준다.
WALL_EDU: list[dict[str, str]] = [
    {
        "label": "비내력벽 (가벽)",
        "tone": "success",
        "desc": (
            "공간을 나누기 위한 벽으로 건물 하중을 직접 받지 않아요. 그래서 철거·"
            "변경의 사전검토 대상이 되는 경우가 많아, 도면에서 선택할 수 있어요."
        ),
    },
    {
        "label": "내력벽",
        "tone": "danger",
        "desc": (
            "위층·지붕·바닥의 무게를 떠받아 건물 기초로 전달하는 벽이에요. 구조를 "
            "지탱하기 때문에 원칙적으로 철거할 수 없어, 선택 대상에서 제외돼요."
        ),
    },
]

#: 벽체 판단 공통 주의(개별 벽마다 반복하지 않고 섹션에 한 번만 단다).
WALL_CAVEAT = (
    "도면상 비내력벽으로 보여도 실제 시공·현장 조건에 따라 다를 수 있어, 최종 철거 "
    "가부는 전문가 정밀 검토와 구조안전확인서로 확정합니다."
)


# ── 방화·안전시설(required_facilities) 코드별 고정 설명 ─────────────────────────
# 각 항목: 리포트에 노출할 헤드라인 + 챙겨야 할 포인트(불릿). /faq?category=fireproofing
# 의 답변(방화판 90cm·스프링클러 면제·자동화재탐지기 등)을 정본으로 한다.
_FACILITY_CONTENT: dict[str, dict[str, Any]] = {
    "FIRE_PANEL": {
        "label": "방화판 설치",
        "headline": "확장 발코니 경계에 방화판을 설치해야 해요",
        "points": [
            "불에 타지 않는 불연보드로 세대 간 화염 확산을 막는 안전 조치예요.",
            "설치 높이는 바닥판 두께를 포함해 90cm 이상이어야 해요.",
            "위치는 난간과 샤시(창호) 사이입니다.",
            "방화판 대신 방화유리를 선택할 수도 있어요(관리규약에 따라 선택).",
        ],
    },
    "FIRE_GLASS": {
        "label": "방화유리 설치",
        "headline": "방화판 대신 방화유리로 채광·시야를 확보할 수 있어요",
        "points": [
            "화재 시 일정 시간 열과 불길을 견디는 유리(KS F 2845 비차열 30분 이상)예요.",
            "방화판과 같은 안전 기능을 하면서 채광과 시야를 함께 확보해요.",
            "시공은 m당 143,000원부터예요 — 설치 길이에 따라 현장 확인 후 산정해요.",
        ],
    },
    "FIRE_DETECTOR": {
        "label": "화재감지기 설치",
        "headline": "자동화재탐지기 설치가 필요할 수 있어요",
        "points": [
            "스프링클러 살수 범위 밖을 거실로 사용할 때 설치가 필요해요(단독주택 제외).",
            "설치 개소는 현장 조건에 따라 달라져, 현장 확인 후 안내해 드려요.",
        ],
    },
    "AUTOMATIC_DOOR_CLOSER": {
        "label": "대피공간 방화문",
        "headline": "대피공간 출입구에 자동닫힘 방화문이 필요해요",
        "points": [
            "대피공간 출입구는 화재 시 자동으로 닫히는 방화문으로 보호해야 해요.",
            "규격·설치 조건은 현장 견적으로 안내해 드려요.",
        ],
    },
    "EVACUATION_SPACE": {
        "label": "대피공간 확보",
        "headline": "세대 내 대피공간을 확보·유지해야 해요",
        "points": [
            "화재 시 잠시 머무를 수 있는 대피공간이 기준 면적으로 확보돼야 해요.",
            "확장 계획이 대피공간을 침범하지 않는지 함께 검토해 드려요.",
        ],
    },
    "SPRINKLER": {
        "label": "스프링클러 확인",
        "headline": "스프링클러 살수 범위를 확인해요",
        "points": [
            "확장 발코니가 스프링클러 살수 범위 안에 들면 방화판·방화유리 의무가 "
            "면제될 수 있어요.",
            "살수 범위 밖을 거실로 쓰면 방화시설과 자동화재탐지기가 필요할 수 있어요.",
        ],
    },
}

#: 법적 고지 — AGENTS.md §4.6 정본(프론트 LegalNotice 와 동일 문구 유지).
LEGAL_NOTICE = (
    "본 서비스는 AI 기반 사전 검토 시스템입니다. 최종 행위허가 여부는 관할 "
    "행정기관 판단에 따라 달라질 수 있습니다."
)

#: 필요 방화시설이 비었을 때 리포트에 보여줄 안내.
FACILITIES_EMPTY_NOTE = (
    "현재 판정 기준으로는 추가로 요구되는 방화·안전시설이 확인되지 않았어요. "
    "다만 현장 조건에 따라 달라질 수 있어 상담에서 다시 확인해 드려요."
)

# ── 진행 일정 (고정) ───────────────────────────────────────────────────────────
# /faq?category=act_permit · use_inspection 의 단계·소요기간을 정본으로 한다.
SCHEDULE: list[dict[str, Any]] = [
    {
        "step": "STEP 1",
        "phase": "공사 전",
        "items": [
            "입주민 동의서 수령(해당 동 50% 이상)",
            "행위허가 서류 접수(신청서·확장 전후 도면·구조안전확인서)",
            "관청 검토 후 행위허가증 교부",
        ],
        "duration": "접수까지 약 7영업일(처리 2주~6개월)",
    },
    {
        "step": "STEP 2",
        "phase": "공사 중",
        "items": [
            "발코니 확장",
            "방화판·방화유리 등 방화시설 설치",
            "인테리어·창호 시공",
        ],
        "duration": "현장 일정에 따라",
    },
    {
        "step": "STEP 3",
        "phase": "공사 후",
        "items": [
            "사용검사 신청",
            "주무관 검토 후 사용검사필증 교부",
            "건축물대장 등재(법적 공사 완료)",
        ],
        "duration": "약 15영업일",
    },
]


def verdict_view(rule_eval_result: dict[str, Any]) -> dict[str, Any]:
    """rule-eval-result → 리포트 헤더용 판정 표기(label/tone/summary/permit_text)."""

    code = rule_eval_result.get("verdict")
    label, tone = _VERDICT_META.get(
        code if isinstance(code, str) else "",
        (code if isinstance(code, str) else "판정", "neutral"),
    )
    # HOLD(데이터 부족)는 엔진이 permit_required 를 보수적으로 직렬화하므로 '필요'로
    # 단정하지 않는다(리포트 화면 page.tsx 와 동일 규칙).
    if code == "HOLD":
        permit_text = "행위허가 미정 (추가 확인 필요)"
    elif rule_eval_result.get("permit_required"):
        permit_text = "행위허가 필요"
    else:
        permit_text = "행위허가 불요(또는 신고 대상)"
    summary = rule_eval_result.get("user_message")
    return {
        "code": code,
        "label": label,
        "tone": tone,
        "summary": summary if isinstance(summary, str) and summary else None,
        "permit_text": permit_text,
    }


def wall_view(wall_type: str | None) -> dict[str, str]:
    """wall_type → 벽체 카드용 라벨/톤/설명. 알 수 없으면 UNKNOWN 처리."""

    meta = _WALL_TYPE_META.get(
        wall_type if isinstance(wall_type, str) else "", _WALL_TYPE_META["UNKNOWN"]
    )
    return dict(meta)


def facility_views(rule_eval_result: dict[str, Any]) -> list[dict[str, Any]]:
    """required_facilities → 코드별 고정 설명 목록. 룰의 라벨이 있으면 우선 사용한다."""

    facilities = rule_eval_result.get("required_facilities")
    if not isinstance(facilities, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in facilities:
        if not isinstance(f, dict):
            continue
        code = f.get("code")
        if not isinstance(code, str) or code in seen:
            continue
        content = _FACILITY_CONTENT.get(code)
        if content is None:
            continue
        seen.add(code)
        rule_label = f.get("label")
        out.append(
            {
                "code": code,
                "label": rule_label
                if isinstance(rule_label, str) and rule_label
                else content["label"],
                "headline": content["headline"],
                "points": list(content["points"]),
            }
        )
    return out


def consultation_view(origin: str) -> dict[str, str]:
    """상담 안내(고정). ``origin`` 으로 절대 링크를 만든다(예: https://jippin.ai)."""

    base = origin.rstrip("/")
    site = base.split("://", 1)[-1] if "://" in base else base
    return {
        "headline": "전문가 상담은 100% 무료예요",
        "body": (
            "리포트를 보시고 궁금한 점이 있으면 무료로 전문가 상담을 받아보세요. "
            "사전검토 · 전문가 상담 · 행위허가 대행 · 방화 시공 중 필요한 단계만 "
            "골라 진행할 수 있어요. 2007년부터 행위허가 분야 전문성을 쌓아온 팀이 "
            "처음부터 끝까지 함께합니다."
        ),
        "url": f"{base}/leads/new",
        "site": site,
    }


def faq_cost_url(origin: str) -> str:
    """비용 안내 FAQ 절대 링크."""

    return f"{origin.rstrip('/')}/faq?category=cost"
