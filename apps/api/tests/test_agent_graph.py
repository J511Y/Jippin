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
    assert captured["store"] is False
    assert captured["extra_body"] == {
        "metadata": {"app": "jippin-agent", "env": "test"}
    }
    assert "use_previous_response_id" not in captured


def test_build_model_preserves_non_openai_provider_string() -> None:
    settings = SimpleNamespace(
        agent_model="anthropic:claude-example",
        openai_api_key=None,
    )

    assert _build_model(settings) == "anthropic:claude-example"
