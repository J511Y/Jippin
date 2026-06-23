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
import contextlib
import hashlib
import json
import time
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError

from ..config import get_settings
from ..errors import ZippinException
from ..logging import get_logger
from ..services import main_flow
from .events import SseEventStream
from .projection import AssistantMessage, ProjectionWriter, ToolEnd, ToolStart
from .tools import TOOL_KINDS, RunContext, build_tools

log = get_logger("zippin.agent.runner")

# 스트리밍 중 다른 클라이언트의 /interrupt 를 감지하기 위한 DB status 폴링 주기(초).
_CANCEL_POLL_SECONDS = 15.0

# agent_runs.current_step 마커 — 재개 의미 판정용.
#  _STEP_SUBMITTING: 새 턴을 그래프에 넘기기 직전(아직 체크포인트 안 됨).
#  _STEP_STREAMING : 그래프가 첫 출력을 냄 = 입력이 체크포인트됨(재개 시 reconnect 가능).
_STEP_SUBMITTING = "submitting"
_STEP_STREAMING = "streaming"


def _stable_lc_id(prefix: str, *parts: str) -> str:
    """LC 메시지/툴콜 id 가 없을 때 쓰는 결정적 fallback.

    랜덤 uuid 를 쓰면 reconnect/resume 가 같은 체크포인트 메시지를 다시 흘릴 때마다
    id 가 바뀌어, ``find_*_by_lc_id`` 가 직전 row 를 못 찾고 중복 투영한다. 내용 해시로
    결정적 id 를 만들면 동일 내용은 동일 id → 멱등 투영 + 클라이언트 dedupe 가능
    (동일 내용 2건이 1건으로 합쳐지는 드문 손실은 중복보다 안전, #stable-projection-id).
    """

    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()[:32]
    return f"{prefix}:{digest}"


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
            args = dict(tc.get("args") or {})
            tc_id = tc.get("id")
            yield ToolStart(
                lc_tool_call_id=(
                    str(tc_id)
                    if tc_id
                    else _stable_lc_id(
                        "toolcall", name, json.dumps(args, sort_keys=True)
                    )
                ),
                tool_name=name,
                tool_kind=tool_kinds.get(name, "other"),
                input=args,
            )

    text = _message_text(getattr(msg, "content", ""))
    msg_type = getattr(msg, "type", None)
    if text and msg_type in (None, "ai", "AIMessageChunk", "assistant"):
        msg_id = getattr(msg, "id", None)
        yield AssistantMessage(
            lc_message_id=(str(msg_id) if msg_id else _stable_lc_id("assistant", text)),
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

        # resume 로 RunContext 가 새로 생긴 경우, 분석 시작 시점에 segment 가 런에
        # 내구화한 입력 지문을 복원한다 — evaluate_rules 가 현재 세션 입력으로 폴백해
        # stale 판정을 새 입력에 영속하는 걸 막는다(#analysis-input-fingerprint).
        if self._run_context.analysis_inputs is None:
            restored = await main_flow.get_run_analysis_inputs(run_id=self.run_id)
            if restored is not None:
                self._run_context.analysis_inputs = restored

        tools = build_tools(
            session_id=self.session_id,
            owner_user_id=self.owner_user_id,
            owner_is_anonymous=self.owner_is_anonymous,
            run_context=self._run_context,
            run_id=self.run_id,
            settings=settings,
        )
        checkpointer = await get_checkpointer()
        return build_agent(tools=tools, checkpointer=checkpointer)

    async def _is_cancelled(self) -> bool:
        try:
            row = await main_flow.get_agent_run(
                session_id=self.session_id,
                run_id=self.run_id,
                owner_user_id=self.owner_user_id,
                owner_is_anonymous=self.owner_is_anonymous,
            )
        except Exception:  # noqa: BLE001 - 폴링 실패는 스트림을 끊지 않는다
            return False
        return row.get("status") == "cancelled"

    async def stream(
        self,
        *,
        user_message: str | None,
        agent: Any | None = None,
        is_disconnected: Callable[[], Awaitable[bool]] | None = None,
        create_run: bool = False,
        resume: bool = False,
    ) -> AsyncIterator[str]:
        """SSE 프레임 async generator. agent 를 주입하면 LLM 없이 테스트 가능.

        런 row 의 생성/점유는 **generator 안에서** 한다 — try/finally 가 늘 감싸므로,
        스트림이 시작되기 전 disconnect 로 row 가 고아(pending/running)가 되는 일을
        막는다(#pre-stream-orphan). ``create_run=True``=새 런 생성, ``resume=True``=
        resumable 런 점유. 둘 다 아니면(테스트) row 가 이미 존재한다고 본다.
        """

        settings = get_settings()
        sse = SseEventStream()
        deadline = time.monotonic() + settings.agent_run_wallclock_timeout_seconds
        run_status = "succeeded"
        finalized = False
        owns_run = True  # self.run_id 가 우리가 마감해도 되는 row 인지
        # interrupted 런의 재개는 "재연결" — 새 user 턴을 append/전송하지 않고
        # 체크포인트에서 이어 돌린다(#reconnect-idempotent).
        reconnect = False

        try:
            try:
                if create_run:
                    try:
                        await main_flow.create_agent_run(
                            run_id=self.run_id,
                            session_id=self.session_id,
                            owner_user_id=self.owner_user_id,
                            model=settings.agent_model,
                            input_summary={"content_chars": len(user_message)},
                            owner_is_anonymous=self.owner_is_anonymous,
                        )
                    except ZippinException as exc:
                        if exc.code == "AGENT_RUN_ALREADY_ACTIVE":
                            owns_run = False
                            # 사전판정 이후 generator insert 직전에 동시 start 가 활성
                            # 런을 만든 race — 클라이언트가 그 런으로 복구할 수 있도록
                            # 활성 런 id/상태를 error 에 실어 준다(#active-run-on-race).
                            active = await main_flow.get_active_agent_run(
                                session_id=self.session_id,
                                owner_user_id=self.owner_user_id,
                                owner_is_anonymous=self.owner_is_anonymous,
                            )
                            yield sse.error(
                                error_code="AGENT_RUN_ALREADY_ACTIVE",
                                message="이미 진행 중인 런이 있습니다.",
                                recoverable=False,
                                active_run_id=str(active["id"]) if active else None,
                                active_run_status=active["status"] if active else None,
                            )
                            yield sse.done(run_status="failed")
                            return
                        # 그 외(세션/유저가 precheck 이후 삭제 → SESSION_NOT_FOUND 등):
                        # row 가 아직 없으므로 generic except(update_agent_run →
                        # AGENT_RUN_NOT_FOUND)나 finally finalize 로 보내지 않고 여기서
                        # 깔끔히 error+done 으로 종료한다. owns_run=False 라 finally 도
                        # 건드리지 않는다(#pre-insert-failure).
                        owns_run = False
                        yield sse.error(
                            error_code=exc.code,
                            message="런을 시작할 수 없습니다.",
                            recoverable=False,
                        )
                        yield sse.done(run_status="failed")
                        return
                    # pending→running 조건부. 시작 전 /interrupt 가 cancelled 로
                    # 바꿨으면 None — 되살리지 않고 중단한다(#startup-overwrite).
                    if (
                        await main_flow.mark_agent_run_running(run_id=self.run_id)
                        is None
                    ):
                        finalized = True
                        yield sse.done(run_status="cancelled")
                        return
                elif resume:
                    # 점유 전 직전 상태를 읽어 재개 의미를 정한다. interrupted(스트림이
                    # 끊겼지만 턴은 이미 수락/체크포인트됨)면 재연결 — 클라이언트가 같은
                    # 프롬프트를 다시 보내도 그 턴을 append/재전송하지 않아 chat_messages
                    # 와 모델 컨텍스트에 중복이 생기지 않는다. awaiting_input(에이전트가
                    # 추가 입력을 기다림)이면 새 user 메시지를 정상 append/전송한다.
                    try:
                        prior = await main_flow.get_agent_run(
                            session_id=self.session_id,
                            run_id=self.run_id,
                            owner_user_id=self.owner_user_id,
                            owner_is_anonymous=self.owner_is_anonymous,
                        )
                        # 재연결(=새 턴 재전송 안 함)은 직전 턴이 실제로 그래프에
                        # 체크포인트된 경우만. row/헤더만 만들어지고 astream 진입 전
                        # disconnect → interrupted 면 current_step 이 _STEP_STREAMING 이
                        # 아니므로 재전송한다(프롬프트 유실 방지, #replay-after-accept).
                        reconnect = (
                            prior.get("status") == "interrupted"
                            and prior.get("current_step") == _STEP_STREAMING
                        )
                    except ZippinException:
                        reconnect = False
                    # resumable 런을 generator 안에서 원자적으로 점유한다 — 스트림이
                    # 시작 안 되면 finally 가 running 으로 남은 row 를 풀어 준다
                    # (#resume-claim-orphan). 점유 실패는 SSE error 로 알린다.
                    try:
                        await main_flow.claim_resumable_agent_run(
                            session_id=self.session_id,
                            run_id=self.run_id,
                            owner_user_id=self.owner_user_id,
                            owner_is_anonymous=self.owner_is_anonymous,
                        )
                    except ZippinException as exc:
                        owns_run = False
                        yield sse.error(
                            error_code=exc.code,
                            message="재개할 수 없는 런입니다.",
                            recoverable=False,
                        )
                        yield sse.done(run_status="failed")
                        return
                # 재연결이 아니면 사용자 메시지를 투영(공개 경로와 동일하게 owner-gated).
                # 여기서 실패(삭제/만료 세션, 일시 DB 오류)해도 except 가 failed 로
                # 마감하고 finally 가 런을 풀어 준다(#startup-finalize). 재연결이면
                # 새 턴을 만들지 않고 체크포인트(input=None)에서 이어 돌린다.
                # no-message reconnect(user_message=None)도 새 턴이 없으므로 reconnect 와
                # 동일하게 다룬다 — append/재전송 없이 체크포인트에서 이어 받는다.
                if user_message is None:
                    reconnect = True
                if not reconnect:
                    # user 턴을 (run_id + 내용) 단위로 멱등하게 투영한다. pre-checkpoint
                    # resume 는 같은 run_id 로 같은 메시지를 다시 보내므로(프롬프트 유실
                    # 방지) 동일 내용은 dedupe 되어야 하지만, awaiting_input 후속 답변은
                    # 같은 run_id 라도 내용이 다른 새 턴이라 별도로 기록돼야 한다. 그래서
                    # 내용 해시를 키에 포함한다 — 재전송(동일 내용)은 1건, 후속(다른 내용)은
                    # 새 row(#per-turn-user-id). 동일 내용 2턴이 합쳐지는 드문 손실은 허용.
                    content_key = hashlib.sha256(
                        user_message.encode("utf-8")
                    ).hexdigest()[:16]
                    lc_user_id = f"user-turn:{self.run_id}:{content_key}"
                    existing_turn = await main_flow.find_chat_message_by_lc_id(
                        session_id=self.session_id, lc_message_id=lc_user_id
                    )
                    if existing_turn is None:
                        try:
                            await main_flow.append_chat_message(
                                session_id=self.session_id,
                                owner_user_id=self.owner_user_id,
                                payload={
                                    "content": user_message,
                                    "metadata": {"lc_message_id": lc_user_id},
                                },
                                owner_is_anonymous=self.owner_is_anonymous,
                            )
                        except IntegrityError:
                            # 부분 유니크 백스톱 — 동시/replay race 로 이미 투영됨.
                            pass
                    # 새 턴 제출 직전 마커. 여기서부터 astream 첫 출력 전까지 disconnect
                    # 되면 _STEP_STREAMING 이 아니라 _STEP_SUBMITTING 으로 남아, 재개가
                    # reconnect 가 아니라 재전송으로 처리된다(프롬프트 유실 방지).
                    await main_flow.update_agent_run(
                        run_id=self.run_id, current_step=_STEP_SUBMITTING
                    )
                if agent is None:
                    agent = await self._build_agent()
                astream_input = (
                    None
                    if reconnect
                    else {"messages": [{"role": "user", "content": user_message}]}
                )
                raw = agent.astream(
                    astream_input,
                    config={"configurable": {"thread_id": str(self.session_id)}},
                    stream_mode=["updates", "messages", "custom"],
                )
                try:
                    last_poll = time.monotonic()
                    turn_checkpointed = reconnect  # 재연결은 이미 수락된 턴
                    async for frame in self._consume(raw, sse, deadline):
                        yield frame
                        if not turn_checkpointed and not frame.startswith(":"):
                            # 그래프가 실제 출력을 냄 = 입력이 체크포인트됨. 이제부터
                            # 끊겨 interrupted 되면 재개를 reconnect 로 이어 돌린다.
                            turn_checkpointed = True
                            await main_flow.update_agent_run(
                                run_id=self.run_id, current_step=_STEP_STREAMING
                            )
                        if is_disconnected is not None and await is_disconnected():
                            run_status = "interrupted"
                            break
                        now = time.monotonic()
                        if now - last_poll >= _CANCEL_POLL_SECONDS:
                            last_poll = now
                            # 다른 탭/클라이언트의 /interrupt 를 감지하면 스트림을
                            # 멈춘다 — LLM/툴이 계속 돌며 부수효과를 내지 않게(#interrupt-stop).
                            if await self._is_cancelled():
                                run_status = "cancelled"
                                break
                    else:
                        # 스트림이 break 없이 정상 소진됨 — 아직 첨부 안 된 A2UI 버퍼를
                        # 마지막에 flush 한다(빈 assistant·resume 잔여, #drain-without-text).
                        async for frame in self._flush_pending_ui(sse):
                            yield frame
                except TimeoutError:
                    # 다음 청크를 기다리다 wall-clock 초과 — stall 도 잡힌다(#7).
                    run_status = "interrupted"
                    yield sse.error(
                        error_code="AGENT_RUN_TIMEOUT",
                        message="런 제한 시간을 초과했습니다.",
                        recoverable=True,
                    )
            except Exception as exc:  # noqa: BLE001 - 어떤 실패든 런을 마감하고 통지
                # str(exc)/traceback 은 SQL 파라미터·업스트림 URL·프롬프트/주소 PII 를
                # 담을 수 있다. 로그 싱크가 redaction 되지 않으므로 안정적 코드/타입/run
                # id 만 남기고 raw 메시지·트레이스백은 기록하지 않는다(#no-raw-exc-log).
                log.error(
                    "agent_run_failed",
                    run_id=str(self.run_id),
                    error_type=type(exc).__name__,
                )
                run_status = "failed"
                # raw 예외 문자열(SQL 파라미터·업스트림 텍스트·사용자 프롬프트/주소 등
                # PII 가능)을 status 메타에 저장하지 않는다 — 안정적 메시지만 영속한다
                # (계약: error_message 에 raw 금지).
                await main_flow.update_agent_run(
                    run_id=self.run_id,
                    error_code="AGENT_RUNTIME_ERROR",
                    error_message="에이전트 실행 중 오류가 발생했습니다.",
                )
                yield sse.error(
                    error_code="AGENT_RUNTIME_ERROR",
                    message="에이전트 실행 중 오류가 발생했습니다.",
                    recoverable=False,
                )

            final_status = await self._finalize(run_status)
            finalized = True
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
        finally:
            # 클라이언트 abort/disconnect 로 제너레이터가 닫히면(GeneratorExit/
            # CancelledError) 위 정상 경로가 실행되지 않아 런이 running 으로 남고,
            # 활성-런 유니크 때문에 다음 send 가 AGENT_RUN_ALREADY_ACTIVE 가 된다.
            # 버려진 스트림을 interrupted 로 풀어 준다(#cancel). shield 로 취소 중에도
            # DB write 가 완료되게 한다. owns_run=False(이미 활성 런 존재)면 건드리지 않음.
            if not finalized and owns_run:
                try:
                    await asyncio.shield(self._finalize("interrupted"))
                except Exception:  # noqa: BLE001
                    log.warning("agent_run_release_failed", run_id=str(self.run_id))

    async def _drain_ui(self) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
        """A2UI 버퍼를 drain 한다 — 메모리(같은 스트림) 우선, 비었으면 내구 버퍼(resume).

        항상 내구 버퍼를 비워 stale carry-over 를 막는다. 같은 스트림에선 메모리·내구가
        동일 내용이라 메모리를 택하고 내구는 버린다(중복 방지). resume 에선 메모리가
        비어 있어 내구 버퍼가 사용된다(#a2ui-durable).
        """

        ui_mem, snap_mem = self._run_context.drain_ui()
        ui_db, snap_db = await main_flow.take_pending_ui(run_id=self.run_id)
        ui = ui_mem or ui_db
        snapshot = snap_mem if snap_mem is not None else snap_db
        return ui, snapshot

    async def _flush_pending_ui(self, sse: SseEventStream) -> AsyncIterator[str]:
        """스트림 정상 종료 후 아직 첨부 안 된 A2UI 버퍼를 마지막 메시지로 내보낸다.

        모델이 결과를 emit_ui_component 로만 내고 빈 assistant 메시지를 낸 경우, 텍스트
        가드로 AssistantMessage 시그널이 억제돼 drain 이 안 일어난다. 그 버퍼가 유실되지
        않도록 스트림 끝에서 한 번 더 drain 해 UI-only 메시지로 투영/emit 한다
        (#drain-without-text).
        """

        ui, snapshot = await self._drain_ui()
        if not ui and snapshot is None:
            return
        msg = AssistantMessage(
            lc_message_id=f"ui-flush:{self.run_id}",
            content="",
            role="assistant",
            ui_components=ui,
            judgment_snapshot=snapshot,
        )
        row, _created = await self._writer.project_message(msg)
        if row is not None:
            yield sse.message(
                role=row.get("role", "assistant"),
                content=row.get("content", ""),
                message_id=str(row["id"]),
                ui_components=row.get("ui_components") or [],
            )

    async def _consume(
        self,
        raw: AsyncIterator[Any],
        sse: SseEventStream,
        deadline: float,
        heartbeat_interval: float = 15.0,
    ) -> AsyncIterator[str]:
        # translate_stream 을 수동 구동한다. 다음 청크를 heartbeat 간격으로만 기다리고
        # (그 사이 ': heartbeat' 프레임을 흘려 프록시 idle-timeout 을 막는다 #heartbeat),
        # 전체 wall-clock 을 넘기면 TimeoutError(#7). pending 태스크는 heartbeat 시
        # 취소하지 않아 같은 제너레이터를 안전하게 이어서 기다린다.
        heartbeat = heartbeat_interval
        signals = translate_stream(raw, tool_kinds=TOOL_KINDS)
        pending: asyncio.Task[Any] | None = None
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError
                if pending is None:
                    pending = asyncio.ensure_future(signals.__anext__())
                done, _ = await asyncio.wait(
                    {pending}, timeout=min(heartbeat, remaining)
                )
                if not done:
                    yield sse.heartbeat()
                    continue
                task, pending = pending, None
                try:
                    sig = task.result()
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
                    ui, snapshot = await self._drain_ui()
                    sig.ui_components = ui
                    sig.judgment_snapshot = snapshot
                    row, _created = await self._writer.project_message(sig)
                    # 영속된 row 기준으로 항상 emit 한다 — resume 재연결 시(SSE 프레임이
                    # 도달 전 끊긴 경우) 이미 저장된 답변도 클라이언트가 받도록. 중복은
                    # 클라이언트가 message_id 로 dedupe 한다(#replay-on-resume).
                    if row is not None:
                        yield sse.message(
                            role=row.get("role", sig.role),
                            content=row.get("content", sig.content),
                            message_id=str(row["id"]),
                            ui_components=row.get("ui_components") or [],
                        )
        finally:
            if pending is not None:
                pending.cancel()
                with contextlib.suppress(BaseException):
                    await pending
            with contextlib.suppress(Exception):
                await signals.aclose()
            # 래핑한 raw astream 도 닫아 리소스를 정리한다(LangGraph/테스트 공통).
            raw_aclose = getattr(raw, "aclose", None)
            if raw_aclose is not None:
                with contextlib.suppress(Exception):
                    await raw_aclose()

    async def _finalize(self, run_status: str) -> str:
        """런을 terminal 상태로 마감하고 실제 최종 상태를 돌려준다.

        이미 terminal(succeeded/failed/cancelled) 이면 덮어쓰지 않고 그 상태를
        보존한다 — /interrupt 가 cancelled 로 마감한 경우(#1)뿐 아니라, 정상
        finalize 직후 finalized=True 전에 disconnect cleanup 이 끼어드는 race 에서
        완료된 런이 interrupted 로 강등되는 것도 막는다(#preserve-terminal).
        """

        current = await main_flow.get_agent_run(
            session_id=self.session_id,
            run_id=self.run_id,
            owner_user_id=self.owner_user_id,
            owner_is_anonymous=self.owner_is_anonymous,
        )
        current_status = current.get("status")
        if current_status in ("succeeded", "failed", "cancelled"):
            return current_status

        status_map = {
            "succeeded": "succeeded",
            "failed": "failed",
            "interrupted": "interrupted",
            "cancelled": "cancelled",
        }
        final = status_map.get(run_status, "succeeded")
        # 조건부 마감(비-terminal 일 때만). read 이후 write 직전에 /interrupt 가
        # cancelled 로 바꾼 race 에서, 무조건 write 가 그 cancelled 를 덮어쓰지 않게
        # 한다 — no-op 이면 실제(=cancelled) 상태를 다시 읽어 돌려준다(#preserve-cancel).
        row = await main_flow.finalize_agent_run(run_id=self.run_id, status=final)
        if row is None:
            refreshed = await main_flow.get_agent_run(
                session_id=self.session_id,
                run_id=self.run_id,
                owner_user_id=self.owner_user_id,
                owner_is_anonymous=self.owner_is_anonymous,
            )
            return refreshed.get("status") or final
        return final
