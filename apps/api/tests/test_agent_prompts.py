"""시스템 프롬프트 불변식 — 운영 세션(32a62ac9)에서 드러난 네 가지 흐름 결함의 회귀 방지.

프롬프트는 자유 텍스트라 단위 테스트가 어렵지만, 코드(툴·세션 상태 블록)와 정합해야 하는
**규약 문구**는 존재 여부로 잠근다: (1) 선택 되풀이 금지·종합 판단, (2) 창호 경계는 VLM
판정 우선·미확정 창만 질문, (3) 대피공간·스프링클러 선질문 폐지, (4) 도면 재선택은 반드시
show_floorplan_overlay 도구.
"""

from __future__ import annotations

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
