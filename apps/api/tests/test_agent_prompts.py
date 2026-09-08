"""시스템 프롬프트 불변식 — 운영 세션(32a62ac9)에서 드러난 네 가지 흐름 결함의 회귀 방지.

프롬프트는 자유 텍스트라 단위 테스트가 어렵지만, 코드(툴·세션 상태 블록)와 정합해야 하는
**규약 문구**는 존재 여부로 잠근다: (1) 선택 되풀이 금지·종합 판단, (2) 창호 경계는 VLM
판정 우선·미확정 창만 질문, (3) 대피공간·스프링클러 선질문 폐지, (4) 도면 재선택은 반드시
show_floorplan_overlay 도구, (5) 내부 보유 도면 조회 도구 미등록·미언급 + 단위세대 평면도
업로드 안내(2026-09).
"""

from __future__ import annotations

import uuid

import pytest

from src.agent.prompts import SYSTEM_PROMPT
from src.agent.tools import TOOL_KINDS


def test_prompt_references_only_registered_tools() -> None:
    # 프롬프트가 언급하는 도구 이름은 전부 실제 등록된 도구여야 한다(오타/폐지 도구 방지).
    for name in (
        "show_floorplan_overlay",
        "emit_floorplan_request",
        "segment_floorplan",
        "evaluate_rules",
        "emit_judgment_summary",
        "set_completion_decision",
    ):
        assert name in SYSTEM_PROMPT
        assert name in TOOL_KINDS


def test_internal_floorplan_lookup_is_disabled() -> None:
    # #internal-floorplan-lookup-disabled: 사내 도면 카탈로그가 0건인 동안 조회 도구를
    # 등록·언급하면 에이전트가 "보유 도면 없음"을 단정해 상담 인력("도면 있어요")과
    # 어긋난다. 도구 레지스트리·프롬프트 양쪽에서 사라졌는지 잠근다.
    assert "lookup_floorplan_candidates" not in TOOL_KINDS
    assert "lookup_floorplan_candidates" not in SYSTEM_PROMPT
    assert "보유 도면이 있는지 찾습니다" not in SYSTEM_PROMPT
    # 대신 "보유 도면을 찾거나 있다/없다고 말하지 않는다"는 지침이 있어야 한다.
    assert "내부 보유 도면" in SYSTEM_PROMPT
    assert "직접 올려 주신" in SYSTEM_PROMPT


def test_build_tools_does_not_register_internal_floorplan_lookup() -> None:
    # 실제 langchain 래핑 결과에서도 빠져 있어야 한다(TOOL_KINDS 와 등록 목록의 정합).
    pytest.importorskip("langchain_core")
    from src.agent.tools import RunContext, build_tools
    from src.config import Settings

    tools = build_tools(
        session_id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        owner_is_anonymous=True,
        run_context=RunContext(),
        run_id=uuid.uuid4(),
        settings=Settings(),
    )
    names = {t.name for t in tools}
    assert "lookup_floorplan_candidates" not in names
    assert names == set(TOOL_KINDS)


def test_prompt_guides_unit_floorplan_upload() -> None:
    # 업로드 카드가 단위세대 평면도 예시 2장 + 촬영 안내를 띄우고, 에이전트는 본문에서
    # "예시처럼 단위세대 평면도를 전체가 보이게·선명하게" 를 한두 문장으로 덧붙인다.
    assert "단위세대 평면도" in SYSTEM_PROMPT
    assert "예시" in SYSTEM_PROMPT
    assert "선명하게" in SYSTEM_PROMPT
    # 재요청(벽 후보 0·평면도 아님)도 같은 안내로 흐른다.
    assert "부동산 앱" in SYSTEM_PROMPT


def test_prompt_forbids_parroting_selection() -> None:
    assert "앵무새 금지" in SYSTEM_PROMPT
    assert "어디에 있는 벽인지" in SYSTEM_PROMPT


def test_prompt_uses_vlm_window_verdict_first() -> None:
    assert "VLM 판정을 기본으로" in SYSTEM_PROMPT
    assert "판단이 어려운 창에 대해서만" in SYSTEM_PROMPT
    # 사용자 정정은 VLM 판정보다 우선(단, 관찰과 달랐다는 점은 알림).
    assert "VLM 판정과 다르게 말하면" in SYSTEM_PROMPT


def test_prompt_drops_pre_report_confirmation_round() -> None:
    # 대피공간·스프링클러는 가부 조건이 아니라 결과와 함께 주는 안내 항목.
    assert "리포트 전 확인 라운드" not in SYSTEM_PROMPT
    assert "확인 라운드를 건너뛰고" not in SYSTEM_PROMPT
    assert "미리 묻지 않습니다" in SYSTEM_PROMPT
    assert "함께 챙길 것" in SYSTEM_PROMPT


def test_prompt_requires_overlay_tool_for_reselection() -> None:
    assert "도면에서 다시/추가로 고르게 하기" in SYSTEM_PROMPT
    assert "show_floorplan_overlay(reason=...)" in SYSTEM_PROMPT
