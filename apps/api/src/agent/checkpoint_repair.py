"""손상된 legacy Responses reasoning 체크포인트의 제한적 복구 도구.

``langchain-openai`` v0 출력은 Responses API reasoning item 을
``AIMessage.additional_kwargs["reasoning"]`` 단일 필드에 저장한다. 복수 reasoning
item 이 스트리밍 중 합쳐지면 encrypted_content 가 무효화되어 이후 모든 stateless
replay 가 ``invalid_encrypted_content`` 400 으로 실패할 수 있다.

이 모듈은 지정한 thread 의 최신 체크포인트에서 암호화된 legacy reasoning 필드만
제거한다. 기존 체크포인트를 수정하지 않고 새 자식 체크포인트를 추가하므로 원본은
보존된다. 사용자/assistant 본문, function call, tool output 은 변경하지 않는다.

운영 사용 예::

    python -m src.agent.checkpoint_repair <session-uuid>
    python -m src.agent.checkpoint_repair <session-uuid> --apply --expected-items 1
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import uuid
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class RepairResult:
    thread_id: str
    legacy_reasoning_items: int
    applied: bool
    source_checkpoint_id: str | None
    repair_checkpoint_id: str | None = None
    candidates: tuple[dict[str, Any], ...] = ()


def inspect_encrypted_legacy_reasoning(
    messages: list[Any],
) -> tuple[dict[str, Any], ...]:
    """원문 없이 message index, reasoning id, 길이, 짧은 해시만 반환한다."""

    candidates: list[dict[str, Any]] = []
    for index, message in enumerate(messages):
        additional_kwargs = getattr(message, "additional_kwargs", None)
        reasoning = (
            additional_kwargs.get("reasoning")
            if isinstance(additional_kwargs, dict)
            else None
        )
        encrypted = (
            reasoning.get("encrypted_content") if isinstance(reasoning, dict) else None
        )
        if not isinstance(encrypted, str) or not encrypted:
            continue
        candidates.append(
            {
                "message_index": index,
                "reasoning_id": reasoning.get("id"),
                "encrypted_length": len(encrypted),
                "encrypted_sha256": hashlib.sha256(encrypted.encode()).hexdigest()[:16],
            }
        )
    return tuple(candidates)


def strip_encrypted_legacy_reasoning(
    messages: list[Any], *, reasoning_ids: frozenset[str] | None = None
) -> tuple[list[Any], int]:
    """암호화된 v0 reasoning 필드만 제거한 메시지 복사본과 제거 개수를 반환한다."""

    sanitized: list[Any] = []
    removed = 0
    for message in messages:
        additional_kwargs = getattr(message, "additional_kwargs", None)
        reasoning = (
            additional_kwargs.get("reasoning")
            if isinstance(additional_kwargs, dict)
            else None
        )
        if not (
            isinstance(reasoning, dict)
            and isinstance(reasoning.get("encrypted_content"), str)
            and reasoning["encrypted_content"]
        ):
            sanitized.append(message)
            continue
        reasoning_id = reasoning.get("id")
        if reasoning_ids is not None and reasoning_id not in reasoning_ids:
            sanitized.append(message)
            continue

        new_kwargs = dict(additional_kwargs)
        new_kwargs.pop("reasoning", None)
        model_copy = getattr(message, "model_copy", None)
        if model_copy is None:
            raise TypeError("legacy reasoning message does not support model_copy")
        sanitized.append(
            model_copy(update={"additional_kwargs": new_kwargs}, deep=False)
        )
        removed += 1
    return sanitized, removed


async def repair_latest_checkpoint(
    checkpointer: Any,
    *,
    thread_id: uuid.UUID,
    apply: bool,
    expected_items: int | None = None,
    reasoning_ids: frozenset[str] | None = None,
) -> RepairResult:
    """최신 체크포인트를 검사하고, 요청된 경우 복구 자식 체크포인트를 추가한다."""

    config = {"configurable": {"thread_id": str(thread_id), "checkpoint_ns": ""}}
    checkpoint_tuple = await checkpointer.aget_tuple(config)
    if checkpoint_tuple is None:
        raise RuntimeError("checkpoint not found")

    checkpoint = checkpoint_tuple.checkpoint
    messages = checkpoint.get("channel_values", {}).get("messages")
    if not isinstance(messages, list):
        raise RuntimeError("checkpoint messages channel not found")

    candidates = inspect_encrypted_legacy_reasoning(messages)
    sanitized, removed = strip_encrypted_legacy_reasoning(
        messages, reasoning_ids=reasoning_ids
    )
    source_id = checkpoint.get("id")
    if apply and not reasoning_ids:
        raise RuntimeError("apply requires at least one targeted reasoning id")
    if expected_items is not None and removed != expected_items:
        raise RuntimeError(
            f"legacy reasoning count mismatch: expected={expected_items}, actual={removed}"
        )
    if not apply or removed == 0:
        return RepairResult(
            thread_id=str(thread_id),
            legacy_reasoning_items=removed,
            applied=False,
            source_checkpoint_id=source_id,
            candidates=candidates,
        )

    from langgraph.checkpoint.base import create_checkpoint

    repaired = copy.deepcopy(checkpoint)
    repaired["channel_values"]["messages"] = sanitized
    current_version = repaired["channel_versions"].get("messages")
    next_version = checkpointer.get_next_version(current_version, None)
    repaired["channel_versions"]["messages"] = next_version

    metadata = dict(checkpoint_tuple.metadata)
    step = int(metadata.get("step", -1)) + 1
    metadata.update({"source": "update", "step": step})
    repair_checkpoint = create_checkpoint(repaired, None, step)
    repair_checkpoint["updated_channels"] = ["messages"]
    next_config = await checkpointer.aput(
        checkpoint_tuple.config,
        repair_checkpoint,
        metadata,
        {"messages": next_version},
    )
    return RepairResult(
        thread_id=str(thread_id),
        legacy_reasoning_items=removed,
        applied=True,
        source_checkpoint_id=source_id,
        repair_checkpoint_id=next_config["configurable"]["checkpoint_id"],
        candidates=candidates,
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect or repair encrypted legacy reasoning in a LangGraph checkpoint."
    )
    parser.add_argument("thread_id", type=uuid.UUID)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Append a sanitized child checkpoint. Without this flag, only inspect.",
    )
    parser.add_argument(
        "--expected-items",
        type=int,
        default=None,
        help="Fail without writing unless the removable item count matches.",
    )
    parser.add_argument(
        "--reasoning-id",
        action="append",
        default=[],
        help="Legacy reasoning item ID to remove. Repeat for multiple IDs.",
    )
    args = parser.parse_args()
    if args.apply and args.expected_items is None:
        parser.error("--apply requires --expected-items")
    if args.apply and not args.reasoning_id:
        parser.error("--apply requires at least one --reasoning-id")
    return args


async def _run(args: argparse.Namespace) -> None:
    from ..db import dispose_engines
    from .checkpointer import get_checkpointer

    try:
        result = await repair_latest_checkpoint(
            await get_checkpointer(),
            thread_id=args.thread_id,
            apply=args.apply,
            expected_items=args.expected_items,
            reasoning_ids=frozenset(args.reasoning_id) if args.reasoning_id else None,
        )
        print(json.dumps(asdict(result), ensure_ascii=False))
    finally:
        await dispose_engines()


def main() -> None:
    asyncio.run(_run(_parse_args()))


if __name__ == "__main__":
    main()
