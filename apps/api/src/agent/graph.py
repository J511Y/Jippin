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
        model=_build_model(settings),
        tools=tools,
        instructions=SYSTEM_PROMPT,
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

        # store=True: 완성본을 OpenAI Platform 에 저장해 Logs 대시보드/평가에서 보이게 한다
        # (기본값은 미저장이라 usage 집계엔 잡혀도 Logs 엔 안 뜬다). metadata 로 앱/환경을
        # 태깅해 로컬·dev·prod 를 구분 필터링할 수 있게 한다.
        return ChatOpenAI(
            model=model_str.split(":", 1)[1],
            api_key=api_key,
            store=True,
            model_kwargs={
                "metadata": {"app": "jippin-agent", "env": str(settings.app_env)}
            },
        )
    return model_str
