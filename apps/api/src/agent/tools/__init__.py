"""우리집 체크 플로우 도구 모음 — CMP-DIRECT.

도구 구현(impl)은 langchain 없이 단위 테스트 가능한 순수 async 함수다. langchain
``@tool`` 래핑은 ``build_tools()`` 에서 lazy 하게 수행한다(graph 조립 시점). 런별
세션 컨텍스트(session_id/owner_user_id)는 closure 로 도구에 바인딩한다.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from .domain import (
    RunContext,
    check_building_register_impl,
    confirm_address_impl,
    emit_address_candidates_impl,
    emit_floorplan_request_impl,
    emit_judgment_summary_impl,
    emit_ui_component_impl,
    evaluate_rules_impl,
    lookup_floorplan_candidates_impl,
    search_address_impl,
    set_completion_decision_impl,
)
from .segmentation import segment_session_floorplan

if TYPE_CHECKING:
    from ...config import Settings

# 도구 이름 → chat_tool_calls.tool_kind 매핑. 런너의 투영 writer 가 ledger row 의
# tool_kind 를 채울 때 참조한다(astream tool 이벤트엔 kind 가 없으므로).
TOOL_KINDS: dict[str, str] = {
    "search_address": "external_api",
    "confirm_address": "external_api",
    "lookup_floorplan_candidates": "external_api",
    "segment_floorplan": "ai_model",
    "check_building_register": "external_api",
    "evaluate_rules": "rule_engine",
    "emit_ui_component": "render",
    "emit_floorplan_request": "render",
    "emit_address_candidates": "render",
    "emit_judgment_summary": "render",
    "set_completion_decision": "rule_engine",
}

__all__ = ["TOOL_KINDS", "RunContext", "build_tools"]


def build_tools(
    *,
    session_id: uuid.UUID,
    owner_user_id: uuid.UUID,
    owner_is_anonymous: bool,
    run_context: RunContext,
    run_id: uuid.UUID,
    settings: "Settings",
) -> list[Any]:
    """impl 함수를 langchain ``@tool`` 로 래핑(런별 세션 컨텍스트 closure 바인딩).

    langchain 은 여기서만 lazy import 한다 — agent_enabled 가 꺼진 환경에서 본
    패키지 import 가 깨지지 않도록.
    """

    from langchain_core.tools import tool

    @tool
    async def search_address(keyword: str) -> dict[str, Any]:
        """도로명주소 API로 주소 후보를 검색한다. 사용자가 정확한 주소를 모를 때 사용."""
        return await search_address_impl(keyword=keyword)

    @tool
    async def lookup_floorplan_candidates() -> dict[str, Any]:
        """확정된 주소(아파트명)로 **내부 보유 도면**을 검색한다. 주소 확정 후 도면 단계
        진입 전에 호출하라. count>0 이면 후보가 있으니 사용자가 고르게 하고, count==0 이면
        보유 도면이 없으니 emit_floorplan_request 로 업로드를 요청하라."""
        return await lookup_floorplan_candidates_impl(session_id=session_id)

    @tool
    async def confirm_address(
        road_address: str | None = None,
        jibun_address: str | None = None,
        apartment_name: str | None = None,
        building_dong: str | None = None,
        unit_ho: str | None = None,
        floor_no: int | None = None,
        exclusive_area_m2: float | None = None,
    ) -> dict[str, Any]:
        """사용자의 주소/동·호/전용면적을 세션에 확정한다. 충분하면 분석 단계로 진행 가능."""
        return await confirm_address_impl(
            session_id=session_id,
            owner_user_id=owner_user_id,
            owner_is_anonymous=owner_is_anonymous,
            road_address=road_address,
            jibun_address=jibun_address,
            apartment_name=apartment_name,
            building_dong=building_dong,
            unit_ho=unit_ho,
            floor_no=floor_no,
            exclusive_area_m2=exclusive_area_m2,
        )

    @tool
    async def segment_floorplan() -> dict[str, Any]:
        """세션에 업로드된 평면도를 세그멘테이션한다(벽/공간 분류). 도면 출처는 세션에
        선택된 asset 으로 고정된다(인자 없음). 도면 미업로드/엔드포인트 실패 시 ok=false."""
        return await segment_session_floorplan(
            session_id=session_id,
            owner_user_id=owner_user_id,
            owner_is_anonymous=owner_is_anonymous,
            settings=settings,
            run_context=run_context,
            run_id=run_id,
        )

    @tool
    async def check_building_register(
        road_addr: str,
        dong: str,
        ho: str,
        jibun_addr: str | None = None,
    ) -> dict[str, Any]:
        """집합건축물대장(전유부+표제부)을 조회해 위반건축물 여부를 확인한다(다소 느릴 수 있음)."""
        return await check_building_register_impl(
            owner_user_id=owner_user_id,
            owner_is_anonymous=owner_is_anonymous,
            road_addr=road_addr,
            dong=dong,
            ho=ho,
            jibun_addr=jibun_addr,
        )

    @tool
    async def evaluate_rules(judgment_values: dict[str, Any]) -> dict[str, Any]:
        """수집된 판단값(wall_type/floor_count/has_sprinkler 등)으로 리모델링 룰을 평가한다.
        결과는 세션 리포트에 자동 저장된다."""
        return await evaluate_rules_impl(
            session_id=session_id,
            judgment_values=judgment_values,
            run_context=run_context,
        )

    @tool
    async def emit_ui_component(
        components: list[dict[str, Any]],
        judgment_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """다음 답변에 첨부할 A2UI 컴포넌트/판단 스냅샷을 등록한다(자유 텍스트로 렌더하지 말 것)."""
        return await emit_ui_component_impl(
            run_context=run_context,
            run_id=run_id,
            components=components,
            judgment_snapshot=judgment_snapshot,
        )

    @tool
    async def emit_floorplan_request(reason: str | None = None) -> dict[str, Any]:
        """평면도가 필요한데 아직 첨부되지 않았을 때, 사용자에게 **도면 업로드 카드**를 띄운다.
        본문에 업로드 방법을 텍스트로 설명하지 말고 이 도구를 호출하라. reason 에 왜 도면이
        필요한지 한 문장."""
        return await emit_floorplan_request_impl(
            run_context=run_context,
            run_id=run_id,
            reason=reason,
        )

    @tool
    async def emit_address_candidates(
        candidates: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """search_address 후보가 여럿이라 사용자가 골라야 할 때 **주소 선택 카드**를 띄운다.
        본문에 후보를 글로 나열하지 말고 이 도구를 호출하라. candidates 각 원소:
        {id, road_address, jibun_address?, building_name?}."""
        return await emit_address_candidates_impl(
            run_context=run_context,
            run_id=run_id,
            candidates=candidates,
        )

    @tool
    async def emit_judgment_summary(
        decision: str,
        title: str,
        summary: str,
        risks: list[str] | None = None,
    ) -> dict[str, Any]:
        """최종 판단을 정리해 **결과 카드**로 보여 준다. decision 은
        possible|conditional|not_possible|needs_expert 중 하나. title 짧은 결론,
        summary 생활어 설명, risks 주의/위험 항목 목록(선택)."""
        return await emit_judgment_summary_impl(
            run_context=run_context,
            run_id=run_id,
            session_id=session_id,
            decision=decision,
            title=title,
            summary=summary,
            risks=risks,
        )

    @tool
    async def set_completion_decision(
        completion_decision: str, reason: str | None = None
    ) -> dict[str, Any]:
        """플로우 결정을 기록한다: ASK_MORE/REQUEST_OVERLAY_REVIEW/PROCEED_RULE/HOLD_OR_HANDOFF."""
        return await set_completion_decision_impl(
            session_id=session_id,
            completion_decision=completion_decision,
            reason=reason,
        )

    return [
        search_address,
        lookup_floorplan_candidates,
        confirm_address,
        segment_floorplan,
        check_building_register,
        evaluate_rules,
        emit_ui_component,
        emit_floorplan_request,
        emit_address_candidates,
        emit_judgment_summary,
        set_completion_decision,
    ]
