"""대화형 에이전트 모델 조립 계약."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from src.agent.graph import _build_model


def test_build_openai_model_uses_responses_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(
        sys.modules,
        "langchain_openai",
        SimpleNamespace(ChatOpenAI=_FakeChatOpenAI),
    )
    settings = SimpleNamespace(
        agent_model="openai:gpt-5.6-luna",
        openai_api_key="test-key",
        openai_store_logs=False,
        app_env="test",
    )

    _build_model(settings)

    assert captured["model"] == "gpt-5.6-luna"
    assert captured["use_responses_api"] is True
    assert captured["output_version"] == "responses/v1"
    assert captured["include"] == ["reasoning.encrypted_content"]
    assert captured["store"] is False
    assert captured["extra_body"] == {
        "metadata": {"app": "jippin-agent", "env": "test"}
    }
    assert "use_previous_response_id" not in captured


def test_responses_v1_payload_preserves_ordered_reasoning_items() -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    from langchain_openai import ChatOpenAI

    model = ChatOpenAI(
        model="gpt-5.6-luna",
        api_key="test-key",
        use_responses_api=True,
        output_version="responses/v1",
        include=["reasoning.encrypted_content"],
        store=False,
    )
    assistant = AIMessage(
        id="resp_test",
        content=[
            {
                "type": "reasoning",
                "id": "rs_first",
                "encrypted_content": "encrypted-first",
                "summary": [],
            },
            {
                "type": "text",
                "id": "msg_preamble",
                "text": "확인해볼게요.",
                "annotations": [],
            },
            {
                "type": "reasoning",
                "id": "rs_second",
                "encrypted_content": "encrypted-second",
                "summary": [],
            },
            {
                "type": "function_call",
                "id": "fc_decision",
                "call_id": "call_decision",
                "name": "set_completion_decision",
                "arguments": '{"decision":"ASK_MORE"}',
                "status": "completed",
            },
        ],
        tool_calls=[
            {
                "name": "set_completion_decision",
                "args": {"decision": "ASK_MORE"},
                "id": "call_decision",
                "type": "tool_call",
            }
        ],
    )
    payload = model._get_request_payload(  # noqa: SLF001 - outbound replay contract
        [
            assistant,
            ToolMessage(content='{"ok":true}', tool_call_id="call_decision"),
            HumanMessage(content="스프링클러가 있어요."),
        ]
    )

    assert payload["include"] == ["reasoning.encrypted_content"]
    assert payload["store"] is False
    assert [item["type"] for item in payload["input"][:4]] == [
        "reasoning",
        "message",
        "reasoning",
        "function_call",
    ]
    reasoning = [item for item in payload["input"] if item.get("type") == "reasoning"]
    assert [(item["id"], item["encrypted_content"]) for item in reasoning] == [
        ("rs_first", "encrypted-first"),
        ("rs_second", "encrypted-second"),
    ]


def test_build_model_preserves_non_openai_provider_string() -> None:
    settings = SimpleNamespace(
        agent_model="anthropic:claude-example",
        openai_api_key=None,
    )

    assert _build_model(settings) == "anthropic:claude-example"
