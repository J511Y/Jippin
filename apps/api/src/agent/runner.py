"""에이전트 런 오케스트레이터 — 라이프사이클 + SSE 스트리밍 + 투영 연결.

흐름:
1. 런(agent_runs)을 running 으로 표시하고 사용자 메시지를 chat_messages 에 기록.
2. 세션 컨텍스트로 도구를 만들고 deep agent 를 조립.
3. ``agent.astream`` 청크를 정규화 시그널로 번역(``translate_stream``)하고,
   투영 writer 로 ledger/메시지를 기록하면서 SSE 프레임을 yield.
4. disconnect/wall-clock/에러를 처리하고 런을 terminal 상태로 마감.

번역기는 langchain 을 import 하지 않고 메시지 객체를 duck-typing 한다 — fake 메시지로
단위 테스트할 수 있다(``tests/test_agent_runner.py``).
"""

from __future__ import annotations

import ast
import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from ..config import get_settings
from ..logging import get_logger
from ..services import main_flow
from .events import SseEventStream
from .projection import AssistantMessage, ProjectionWriter, ToolEnd, ToolStart
from .tools import TOOL_KINDS, RunContext, build_tools

log = get_logger("zippin.agent.runner")


@dataclass
class TokenSignal:
    delta: str


Signal = TokenSignal | ToolStart | ToolEnd | AssistantMessage


# --- astream 청크 → 정규화 시그널 번역 (langchain duck-typing) ----------------


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        return "".join(parts)
    return str(content) if content is not None else ""


def _tool_result_dict(msg: Any) -> dict[str, Any] | None:
    """도구 결과 dict 를 복원한다.

    plain ``@tool`` 은 dict 반환을 ToolMessage.content(JSON 문자열)로 싣는다
    (artifact 아님). 그래서 artifact 우선, 없으면 content 를 JSON→파이썬 리터럴
    순으로 파싱해 ``{"ok": ..., "error_code": ...}`` 를 복원한다 — 그렇지 않으면
    ok=false degrade 가 succeeded 로 오기록된다.
    """

    artifact = getattr(msg, "artifact", None)
    if isinstance(artifact, dict):
        return artifact
    content = _message_text(getattr(msg, "content", None))
    if not content:
        return None
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(content)
        except (ValueError, SyntaxError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _tool_end_status(msg: Any, result: dict[str, Any] | None) -> str:
    if getattr(msg, "status", None) == "error":
        return "failed"
    if isinstance(result, dict) and result.get("ok") is False:
        return "failed"
    return "succeeded"


def _tool_end_payload(msg: Any, result: dict[str, Any] | None) -> dict[str, Any]:
    output = result if isinstance(result, dict) else None
    error_code = output.get("error_code") if output else None
    summary = (output.get("summary") or output.get("message")) if output else None
    if summary is None:
        text = _message_text(getattr(msg, "content", None))
        if text:
            summary = text[:280]
    return {"output": output, "output_summary": summary, "error_code": error_code}


async def translate_stream(
    raw_stream: AsyncIterator[Any], *, tool_kinds: dict[str, str]
) -> AsyncIterator[Signal]:
    """LangGraph astream(stream_mode=[...]) 청크를 정규화 시그널로 변환."""

    _MODES = {
        "messages",
        "updates",
        "custom",
        "values",
        "tasks",
        "checkpoints",
        "debug",
    }
    async for item in raw_stream:
        if (
            isinstance(item, tuple)
            and len(item) == 2
            and isinstance(item[0], str)
            and item[0] in _MODES
        ):
            mode, data = item
        else:
            mode, data = "updates", item

        if mode == "messages":
            chunk = data[0] if isinstance(data, tuple) and data else data
            text = _message_text(getattr(chunk, "content", ""))
            if text and not getattr(chunk, "tool_calls", None):
                yield TokenSignal(text)
            continue

        if mode != "updates" or not isinstance(data, dict):
            continue

        for node_update in data.values():
            if not isinstance(node_update, dict):
                continue
            for msg in node_update.get("messages", []) or []:
                async for sig in _translate_message(msg, tool_kinds):
                    yield sig


async def _translate_message(
    msg: Any, tool_kinds: dict[str, str]
) -> AsyncIterator[Signal]:
    tool_call_id = getattr(msg, "tool_call_id", None)
    if tool_call_id:  # ToolMessage → tool end
        result = _tool_result_dict(msg)
        payload = _tool_end_payload(msg, result)
        yield ToolEnd(
            lc_tool_call_id=str(tool_call_id),
            status=_tool_end_status(msg, result),
            output=payload["output"],
            output_summary=payload["output_summary"],
            error_code=payload["error_code"],
        )
        return

    tool_calls = getattr(msg, "tool_calls", None)
    if tool_calls:  # AIMessage with tool calls → tool starts
        for tc in tool_calls:
            name = tc.get("name", "")
            yield ToolStart(
                lc_tool_call_id=str(tc.get("id") or uuid.uuid4()),
                tool_name=name,
                tool_kind=tool_kinds.get(name, "other"),
                input=dict(tc.get("args") or {}),
            )

    text = _message_text(getattr(msg, "content", ""))
    msg_type = getattr(msg, "type", None)
    if text and msg_type in (None, "ai", "AIMessageChunk", "assistant"):
        yield AssistantMessage(
            lc_message_id=str(getattr(msg, "id", None) or uuid.uuid4()),
            content=text,
            role="assistant",
        )


# --- 런너 -------------------------------------------------------------------


class AgentRunner:
    def __init__(
        self,
        *,
        session_id: uuid.UUID,
        owner_user_id: uuid.UUID,
        owner_is_anonymous: bool,
        run_id: uuid.UUID,
    ) -> None:
        self.session_id = session_id
        self.owner_user_id = owner_user_id
        self.owner_is_anonymous = owner_is_anonymous
        self.run_id = run_id
        self._writer = ProjectionWriter(
            session_id=session_id, owner_user_id=owner_user_id
        )
        self._run_context = RunContext()

    async def _build_agent(self) -> Any:
        settings = get_settings()
        from .checkpointer import get_checkpointer
        from .graph import build_agent

        tools = build_tools(
            session_id=self.session_id,
            owner_user_id=self.owner_user_id,
            owner_is_anonymous=self.owner_is_anonymous,
            run_context=self._run_context,
            settings=settings,
        )
        checkpointer = await get_checkpointer()
        return build_agent(tools=tools, checkpointer=checkpointer)

    async def stream(
        self,
        *,
        user_message: str,
        agent: Any | None = None,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
    ) -> AsyncIterator[str]:
        """SSE 프레임 async generator. agent 를 주입하면 LLM 없이 테스트 가능."""

        settings = get_settings()
        sse = SseEventStream()
        deadline = time.monotonic() + settings.agent_run_wallclock_timeout_seconds
        run_status = "succeeded"

        await main_flow.update_agent_run(
            run_id=self.run_id, status="running", started_at=main_flow._now()
        )
        # 사용자 메시지 투영(공개 경로와 동일하게 owner-gated user 메시지).
        await main_flow.append_chat_message(
            session_id=self.session_id,
            owner_user_id=self.owner_user_id,
            payload={"content": user_message},
            owner_is_anonymous=self.owner_is_anonymous,
        )

        try:
            if agent is None:
                agent = await self._build_agent()
            raw = agent.astream(
                {"messages": [{"role": "user", "content": user_message}]},
                config={"configurable": {"thread_id": str(self.session_id)}},
                stream_mode=["updates", "messages", "custom"],
            )
            try:
                async for frame in self._consume(raw, sse, deadline):
                    yield frame
                    if is_disconnected is not None and await is_disconnected():
                        run_status = "interrupted"
                        break
            except TimeoutError:
                # 다음 청크를 기다리다 wall-clock 초과 — stall 도 잡힌다(#7).
                run_status = "interrupted"
                yield sse.error(
                    error_code="AGENT_RUN_TIMEOUT",
                    message="런 제한 시간을 초과했습니다.",
                    recoverable=True,
                )
        except Exception as exc:  # noqa: BLE001 - 어떤 실패든 런을 마감하고 통지
            log.exception("agent_run_failed", run_id=str(self.run_id), error=str(exc))
            run_status = "failed"
            await main_flow.update_agent_run(
                run_id=self.run_id,
                error_code="AGENT_RUNTIME_ERROR",
                error_message=str(exc)[:500],
            )
            yield sse.error(
                error_code="AGENT_RUNTIME_ERROR",
                message="에이전트 실행 중 오류가 발생했습니다.",
                recoverable=False,
            )

        final_status = await self._finalize(run_status)
        # 최종 세션 상태 통지.
        session = await main_flow.get_owned_session(
            self.session_id,
            owner_user_id=self.owner_user_id,
            owner_is_anonymous=self.owner_is_anonymous,
        )
        yield sse.state_change(
            session_status=session["status"],
            completion_decision=session.get("completion_decision"),
        )
        yield sse.done(run_status=final_status)

    async def _consume(
        self, raw: AsyncIterator[Any], sse: SseEventStream, deadline: float
    ) -> AsyncIterator[str]:
        # translate_stream 을 수동 구동해, 다음 청크 await 를 남은 wall-clock 으로
        # 제한한다 — LLM/툴이 청크 사이에서 멈춰도 deadline 이 발동한다(#7).
        signals = translate_stream(raw, tool_kinds=TOOL_KINDS)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            try:
                sig = await asyncio.wait_for(signals.__anext__(), timeout=remaining)
            except StopAsyncIteration:
                break
            if isinstance(sig, TokenSignal):
                yield sse.token(sig.delta)
            elif isinstance(sig, ToolStart):
                await self._writer.project_tool_start(sig)
                yield sse.tool_step(
                    tool_name=sig.tool_name,
                    tool_kind=sig.tool_kind,
                    status="started",
                )
            elif isinstance(sig, ToolEnd):
                await self._writer.project_tool_end(sig)
                yield sse.tool_step(
                    tool_name="tool",
                    tool_kind="other",
                    status="succeeded" if sig.status == "succeeded" else "failed",
                    error_code=sig.error_code,
                )
            elif isinstance(sig, AssistantMessage):
                ui, snapshot = self._run_context.drain_ui()
                sig.ui_components = ui
                sig.judgment_snapshot = snapshot
                row, created = await self._writer.project_message(sig)
                # resume replay 로 이미 투영된 메시지는 SSE 를 다시 보내지 않는다 —
                # 클라이언트 중복 버블 방지(#5).
                if created:
                    yield sse.message(
                        role=sig.role,
                        content=sig.content,
                        message_id=str(row["id"]) if row else None,
                        ui_components=ui,
                    )

    async def _finalize(self, run_status: str) -> str:
        """런을 terminal 상태로 마감하고 실제 최종 상태를 돌려준다.

        스트리밍 도중 /interrupt 가 런을 cancelled 로 마감했을 수 있다 — 그 경우
        로컬 run_status(보통 succeeded)로 덮어쓰지 않고 cancelled 를 보존한다(#1).
        """

        current = await main_flow.get_agent_run(
            session_id=self.session_id,
            run_id=self.run_id,
            owner_user_id=self.owner_user_id,
            owner_is_anonymous=self.owner_is_anonymous,
        )
        if current.get("status") == "cancelled":
            return "cancelled"

        status_map = {
            "succeeded": "succeeded",
            "failed": "failed",
            "interrupted": "interrupted",
            "cancelled": "cancelled",
        }
        final = status_map.get(run_status, "succeeded")
        await main_flow.update_agent_run(
            run_id=self.run_id, status=final, finished_at=main_flow._now()
        )
        return final
