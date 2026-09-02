"""legacy Responses reasoning 체크포인트 복구 회귀 테스트."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.checkpoint_repair import (
    inspect_encrypted_legacy_reasoning,
    repair_latest_checkpoint,
    strip_encrypted_legacy_reasoning,
)


def _messages() -> list[object]:
    return [
        HumanMessage(content="도면을 확인해 주세요.", id="user-1"),
        AIMessage(
            content=[{"type": "text", "text": "확인했습니다."}],
            id="assistant-1",
            additional_kwargs={
                "reasoning": {
                    "id": "rs-corrupt",
                    "type": "reasoning",
                    "encrypted_content": "corrupt-encrypted-content",
                    "summary": [],
                },
                "__openai_function_call_ids__": {"call-1": "fc-1"},
            },
            tool_calls=[
                {
                    "name": "set_completion_decision",
                    "args": {"decision": "ASK_MORE"},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content='{"ok":true}', tool_call_id="call-1", id="tool-1"),
        HumanMessage(content="스프링클러가 있어요.", id="user-2"),
    ]


def test_strip_encrypted_legacy_reasoning_preserves_public_and_tool_state() -> None:
    original = _messages()

    sanitized, removed = strip_encrypted_legacy_reasoning(original)

    assert removed == 1
    assert original[1].additional_kwargs["reasoning"]["id"] == "rs-corrupt"
    assert "reasoning" not in sanitized[1].additional_kwargs
    assert sanitized[1].content == original[1].content
    assert sanitized[1].tool_calls == original[1].tool_calls
    assert sanitized[1].additional_kwargs["__openai_function_call_ids__"] == {
        "call-1": "fc-1"
    }
    assert sanitized[2].content == original[2].content
    assert sanitized[3].content == original[3].content


def test_inspect_legacy_reasoning_returns_only_safe_descriptors() -> None:
    candidates = inspect_encrypted_legacy_reasoning(_messages())

    assert candidates == (
        {
            "message_index": 1,
            "reasoning_id": "rs-corrupt",
            "encrypted_length": len("corrupt-encrypted-content"),
            "encrypted_sha256": "2744c7f341322b31",
        },
    )
    assert "corrupt-encrypted-content" not in str(candidates)


def test_strip_legacy_reasoning_targets_explicit_id_only() -> None:
    original = _messages()

    untouched, removed = strip_encrypted_legacy_reasoning(
        original, reasoning_ids=frozenset({"rs-other"})
    )
    sanitized, matched = strip_encrypted_legacy_reasoning(
        original, reasoning_ids=frozenset({"rs-corrupt"})
    )

    assert removed == 0
    assert untouched[1].additional_kwargs["reasoning"]["id"] == "rs-corrupt"
    assert matched == 1
    assert "reasoning" not in sanitized[1].additional_kwargs


class _FakeCheckpointer:
    def __init__(self) -> None:
        self.put_args: tuple[object, ...] | None = None
        self.checkpoint_tuple = SimpleNamespace(
            config={
                "configurable": {
                    "thread_id": "thread",
                    "checkpoint_ns": "",
                    "checkpoint_id": "checkpoint-source",
                }
            },
            checkpoint={
                "v": 4,
                "ts": "2026-09-02T00:00:00+00:00",
                "id": "checkpoint-source",
                "channel_values": {"messages": _messages(), "other": "kept"},
                "channel_versions": {"messages": "0001.old", "other": "0004.old"},
                "versions_seen": {"agent": {"messages": "0001.old"}},
                "pending_sends": [],
                "updated_channels": ["messages"],
            },
            metadata={"source": "loop", "step": 7, "parents": {}},
        )

    async def aget_tuple(self, config: object) -> object:  # noqa: ARG002
        return self.checkpoint_tuple

    def get_next_version(self, current: str, channel: None) -> str:  # noqa: ARG002
        assert current == "0001.old"
        return "0002.new"

    async def aput(self, *args: object) -> dict[str, object]:
        self.put_args = args
        checkpoint = args[1]
        return {
            "configurable": {
                "thread_id": "thread",
                "checkpoint_ns": "",
                "checkpoint_id": checkpoint["id"],
            }
        }


@pytest.mark.asyncio
async def test_repair_dry_run_does_not_write() -> None:
    checkpointer = _FakeCheckpointer()

    result = await repair_latest_checkpoint(
        checkpointer,
        thread_id=uuid.UUID("865fec06-7e28-4818-baf6-fbb9550610f7"),
        apply=False,
        expected_items=1,
    )

    assert result.legacy_reasoning_items == 1
    assert result.applied is False
    assert checkpointer.put_args is None


@pytest.mark.asyncio
async def test_repair_appends_child_checkpoint_with_new_messages_version() -> None:
    checkpointer = _FakeCheckpointer()

    result = await repair_latest_checkpoint(
        checkpointer,
        thread_id=uuid.UUID("865fec06-7e28-4818-baf6-fbb9550610f7"),
        apply=True,
        expected_items=1,
        reasoning_ids=frozenset({"rs-corrupt"}),
    )

    assert result.applied is True
    assert result.repair_checkpoint_id is not None
    assert checkpointer.put_args is not None
    config, checkpoint, metadata, new_versions = checkpointer.put_args
    assert config["configurable"]["checkpoint_id"] == "checkpoint-source"
    assert checkpoint["id"] != "checkpoint-source"
    assert checkpoint["channel_versions"]["messages"] == "0002.new"
    assert checkpoint["channel_versions"]["other"] == "0004.old"
    assert checkpoint["channel_values"]["other"] == "kept"
    assert (
        "reasoning" not in checkpoint["channel_values"]["messages"][1].additional_kwargs
    )
    assert metadata["source"] == "update"
    assert metadata["step"] == 8
    assert new_versions == {"messages": "0002.new"}


@pytest.mark.asyncio
async def test_repair_refuses_unexpected_item_count() -> None:
    checkpointer = _FakeCheckpointer()

    with pytest.raises(RuntimeError, match="count mismatch"):
        await repair_latest_checkpoint(
            checkpointer,
            thread_id=uuid.UUID("865fec06-7e28-4818-baf6-fbb9550610f7"),
            apply=True,
            expected_items=2,
            reasoning_ids=frozenset({"rs-corrupt"}),
        )

    assert checkpointer.put_args is None


@pytest.mark.asyncio
async def test_repair_apply_requires_explicit_reasoning_id() -> None:
    checkpointer = _FakeCheckpointer()

    with pytest.raises(RuntimeError, match="targeted reasoning id"):
        await repair_latest_checkpoint(
            checkpointer,
            thread_id=uuid.UUID("865fec06-7e28-4818-baf6-fbb9550610f7"),
            apply=True,
            expected_items=1,
        )

    assert checkpointer.put_args is None
