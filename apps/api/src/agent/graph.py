"""deep agent 조립 — create_deep_agent 팩토리(CMP-DIRECT).

deepagents 는 LangGraph 런타임 위에서 동작한다. 모델/체크포인터는 재사용하되,
도구는 런별 세션 컨텍스트에 바인딩되므로 에이전트는 런마다 조립한다(저렴). deepagents
는 함수 내부에서 lazy import 한다.

deepagents 0.0.5 의 ``create_deep_agent`` 시그니처(검증됨): ``(tools, instructions,
model, subagents, state_schema, builtin_tools, interrupt_config, config_schema,
checkpointer, post_model_hook)``. 시스템 프롬프트 인자명은 ``instructions`` 다.
라이브러리 업그레이드 시 본 시그니처와 ``astream(stream_mode=[...])`` 동작을 재검증한다.
"""

from __future__ import annotations

from typing import Any

from ..config import get_settings
from .prompts import SYSTEM_PROMPT


def build_agent(*, tools: list[Any], checkpointer: Any) -> Any:
    """우리집 체크 deep agent 를 조립해 반환한다(compiled LangGraph)."""

    from deepagents import create_deep_agent

    settings = get_settings()
    return create_deep_agent(
        model=settings.agent_model,
        tools=tools,
        instructions=SYSTEM_PROMPT,
        checkpointer=checkpointer,
    )
