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


def build_agent(
    *, tools: list[Any], checkpointer: Any, session_context: str | None = None
) -> Any:
    """우리집 체크 deep agent 를 조립해 반환한다(compiled LangGraph).

    ``session_context`` 가 주어지면 system prompt 끝에 '현재 세션 상태' 스냅샷을 덧붙인다 —
    에이전트가 REST 로 갱신된 선택(selected_walls)·확정 주소·도면 분석 상태를 알게 해
    선택을 모르거나 이미 받은 정보를 또 묻는 문제를 막는다(런마다 최신 상태 재주입).
    """

    from deepagents import create_deep_agent

    settings = get_settings()
    instructions = SYSTEM_PROMPT
    if session_context:
        instructions = f"{SYSTEM_PROMPT}\n\n{session_context}"
    return create_deep_agent(
        model=_build_model(settings),
        tools=tools,
        instructions=instructions,
        checkpointer=checkpointer,
    )


def _build_model(settings: Any) -> Any:
    """모델 인스턴스/문자열을 만든다.

    pydantic ``env_file`` 로 읽은 OPENAI_API_KEY 는 os.environ 에 export 되지 않으므로,
    deepagents 에 모델 문자열만 넘기면 LangChain/OpenAI 가 키를 못 본다(.env 로컬/dev
    부팅 실패). openai 모델이면 키를 명시적으로 주입한 ChatOpenAI 인스턴스를 만든다.
    """

    model_str = settings.agent_model
    api_key = settings.openai_api_key
    if model_str.startswith("openai:") and api_key:
        from langchain_openai import ChatOpenAI

        # store: 완성본을 OpenAI Platform Logs 에 저장(평가/디버깅). 프리체크 대화는 주소
        # 등 PII 를 담을 수 있어 **openai_store_logs 가 켜진 경우에만** 저장한다(기본 미저장,
        # 프로덕션 보호). metadata 로 앱/환경을 태깅해 환경별 필터링이 가능하게 한다.
        return ChatOpenAI(
            model=model_str.split(":", 1)[1],
            api_key=api_key,
            store=settings.openai_store_logs,
            model_kwargs={
                "metadata": {"app": "jippin-agent", "env": str(settings.app_env)}
            },
        )
    return model_str
