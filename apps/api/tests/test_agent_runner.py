"""런너 + 스트림 번역 테스트 — SSE 시퀀스 + agent_runs 전이 (CMP-DIRECT).

deepagents/LLM 을 mock 한 fake agent 의 astream 청크를 주입해, 번역기(translate_stream)
와 런너(AgentRunner.stream)가 올바른 정규화 시그널/ SSE 프레임을 내고 런 라이프사이클을
마감하는지 검증한다.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from src.agent.events import SseEventStream
from src.agent.projection import AssistantMessage, ToolEnd, ToolStart
from src.agent.runner import AgentRunner, TokenSignal, translate_stream
from src.services import main_flow
from tests._main_flow_db_fake import FakeMainFlowDb, install_main_flow_fake


@pytest.fixture
def fake(monkeypatch) -> FakeMainFlowDb:
    return install_main_flow_fake(monkeypatch)


async def _aiter(items: list[Any]):
    for item in items:
        yield item


def _ai_tool_call() -> SimpleNamespace:
    return SimpleNamespace(
        content="",
        tool_calls=[
            {"id": "tc1", "name": "segment_floorplan", "args": {"image_url": "x"}}
        ],
        id="ai1",
        type="ai",
    )


def _tool_message() -> SimpleNamespace:
    return SimpleNamespace(
        tool_call_id="tc1",
        content="ok",
        status="success",
        artifact={"ok": True, "summary": "세그멘테이션 완료", "error_code": None},
    )


def _final_ai() -> SimpleNamespace:
    return SimpleNamespace(
        content="분석을 마쳤습니다.", tool_calls=[], id="ai2", type="ai"
    )


def _chunks() -> list[Any]:
    return [
        ("messages", (SimpleNamespace(content="안녕", tool_calls=None), {})),
        ("updates", {"agent": {"messages": [_ai_tool_call()]}}),
        ("updates", {"tools": {"messages": [_tool_message()]}}),
        ("updates", {"agent": {"messages": [_final_ai()]}}),
    ]


class _FakeAgent:
    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks

    def astream(self, payload: Any, config: Any = None, stream_mode: Any = None):
        return _aiter(self._chunks)


def _parse(frames: list[str]) -> list[tuple[str | None, dict[str, Any] | None]]:
    events: list[tuple[str | None, dict[str, Any] | None]] = []
    for frame in frames:
        if frame.startswith(":"):  # heartbeat/comment
            continue
        ev: str | None = None
        data: dict[str, Any] | None = None
        for line in frame.strip().split("\n"):
            if line.startswith("event: "):
                ev = line[len("event: ") :]
            elif line.startswith("data: "):
                data = json.loads(line[len("data: ") :])
        events.append((ev, data))
    return events


async def test_translate_stream_emits_expected_signals() -> None:
    tool_kinds = {"segment_floorplan": "ai_model"}
    signals = [
        sig async for sig in translate_stream(_aiter(_chunks()), tool_kinds=tool_kinds)
    ]

    assert isinstance(signals[0], TokenSignal)
    assert signals[0].delta == "안녕"

    starts = [s for s in signals if isinstance(s, ToolStart)]
    assert len(starts) == 1
    assert starts[0].lc_tool_call_id == "tc1"
    assert starts[0].tool_kind == "ai_model"

    ends = [s for s in signals if isinstance(s, ToolEnd)]
    assert len(ends) == 1
    assert ends[0].lc_tool_call_id == "tc1"
    assert ends[0].status == "succeeded"

    messages = [s for s in signals if isinstance(s, AssistantMessage)]
    assert len(messages) == 1
    assert messages[0].content == "분석을 마쳤습니다."


async def test_translate_stream_messages_skips_tool_message_tokens() -> None:
    # #tool-message-token-leak: messages 모드에서 ToolMessage(도구 결과 — tool_call_id 보유,
    # content=JSON/내부 텍스트)는 토큰으로 흘리지 않는다(tool_step 으로만 노출). AI 청크는 흘린다.
    tool_chunk = SimpleNamespace(
        tool_call_id="tc1",
        content='{"ok": true, "summary": "주소 확정"}',
        type="tool",
    )
    ai_chunk = SimpleNamespace(content="안녕하세요", tool_calls=None, type="ai")
    chunks = [
        ("messages", (tool_chunk, {})),
        ("messages", (ai_chunk, {})),
    ]
    signals = [s async for s in translate_stream(_aiter(chunks), tool_kinds={})]
    tokens = [s for s in signals if isinstance(s, TokenSignal)]
    # ToolMessage 는 누출되지 않고, AI 청크만 토큰으로 방출된다.
    assert len(tokens) == 1
    assert tokens[0].delta == "안녕하세요"


async def test_translate_stream_messages_skips_non_ai_chunks() -> None:
    # messages 모드에서 비-AI(human 등) 청크도 토큰으로 흘리지 않는다.
    human_chunk = SimpleNamespace(content="사용자 입력", tool_calls=None, type="human")
    signals = [
        s
        async for s in translate_stream(
            _aiter([("messages", (human_chunk, {}))]), tool_kinds={}
        )
    ]
    assert [s for s in signals if isinstance(s, TokenSignal)] == []


async def test_translate_stream_uses_stable_id_when_message_id_absent() -> None:
    # #stable-projection-id: id 없는 메시지는 내용 기반 결정적 id → replay 시 동일.
    def chunks() -> list[Any]:
        return [
            (
                "updates",
                {
                    "agent": {
                        "messages": [
                            SimpleNamespace(
                                content="결과입니다", tool_calls=[], type="ai"
                            )
                        ]
                    }
                },
            ),
        ]

    first = [
        s
        async for s in translate_stream(_aiter(chunks()), tool_kinds={})
        if isinstance(s, AssistantMessage)
    ]
    second = [
        s
        async for s in translate_stream(_aiter(chunks()), tool_kinds={})
        if isinstance(s, AssistantMessage)
    ]
    assert first[0].lc_message_id == second[0].lc_message_id
    assert "uuid" not in first[0].lc_message_id
    assert first[0].lc_message_id.startswith("assistant:")


async def test_runner_streams_sse_and_finalizes(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    session_id = session["id"]
    run = await main_flow.create_agent_run(
        session_id=session_id, owner_user_id=owner, model="openai:gpt-5.4-mini"
    )

    runner = AgentRunner(
        session_id=session_id,
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    frames = [
        frame
        async for frame in runner.stream(
            user_message="우리집 봐줘", agent=_FakeAgent(_chunks())
        )
    ]
    events = _parse(frames)
    kinds = [ev for ev, _ in events]

    assert "token" in kinds
    assert any(ev == "tool_step" and data["status"] == "started" for ev, data in events)
    assert any(
        ev == "tool_step" and data["status"] == "succeeded" for ev, data in events
    )
    assert any(
        ev == "message" and data["content"] == "분석을 마쳤습니다."
        for ev, data in events
    )
    # 마지막 두 프레임은 state_change, done 순.
    assert events[-1][0] == "done"
    assert events[-1][1]["run_status"] == "succeeded"
    assert events[-2][0] == "state_change"

    # 런 라이프사이클 마감 + 투영.
    assert fake.agent_runs[run["id"]]["status"] == "succeeded"
    assert fake.agent_runs[run["id"]]["finished_at"] is not None
    user_msgs = [
        r
        for r in fake.chat_messages.values()
        if r["session_id"] == session_id and r["role"] == "user"
    ]
    assert len(user_msgs) == 1
    assert user_msgs[0]["content"] == "우리집 봐줘"
    assistant_msgs = [
        r
        for r in fake.chat_messages.values()
        if r["session_id"] == session_id and r["role"] == "assistant"
    ]
    assert len(assistant_msgs) == 1
    tool_calls = [
        r for r in fake.chat_tool_calls.values() if r["session_id"] == session_id
    ]
    assert len(tool_calls) == 1
    assert tool_calls[0]["status"] == "succeeded"


def _token_only_chunks() -> list[Any]:
    # assistant 메시지 없이 토큰만 — 모델이 결과를 emit_ui_component 로만 낸 경우 모사.
    return [("messages", (SimpleNamespace(content="음", tool_calls=None), {}))]


async def test_runner_flushes_durable_ui_without_assistant_text(
    fake: FakeMainFlowDb,
) -> None:
    # #drain-without-text + #a2ui-durable: assistant 텍스트가 없어도 내구 A2UI 버퍼를
    # 스트림 끝에서 flush 해 UI-only 메시지로 투영/emit 한다(resume 도 같은 경로).
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    # 도구가 등록한(체크포인트된) A2UI 가 내구 버퍼에만 있고 메모리엔 없는 상태(resume 모사).
    await main_flow.append_pending_ui(
        run_id=run["id"], components=[{"kind": "result"}], snapshot={"v": 1}
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    frames = [
        f
        async for f in runner.stream(
            user_message="x", agent=_FakeAgent(_token_only_chunks())
        )
    ]
    events = _parse(frames)
    msgs = [d for ev, d in events if ev == "message"]
    assert len(msgs) == 1
    assert msgs[0]["ui_components"] == [{"kind": "result"}]
    # drain 후 내구 버퍼는 비워진다.
    assert fake.agent_runs[run["id"]]["pending_ui"] == []
    assert fake.agent_runs[run["id"]]["pending_judgment_snapshot"] is None


async def test_runner_one_active_run_per_session(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    session_id = session["id"]
    await main_flow.create_agent_run(
        session_id=session_id, owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    # 두 번째 활성 런은 부분 유니크 백스톱으로 409.
    from src.errors import ZippinException

    with pytest.raises(ZippinException) as excinfo:
        await main_flow.create_agent_run(
            session_id=session_id, owner_user_id=owner, model="openai:gpt-5.4-mini"
        )
    assert excinfo.value.code == "AGENT_RUN_ALREADY_ACTIVE"


async def test_create_run_fk_violation_maps_to_not_found(
    fake: FakeMainFlowDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #unique-only-conflict: FK 위반(23503)은 활성 런 충돌이 아니라 not-found 로.
    from sqlalchemy.exc import IntegrityError

    from src.errors import ZippinException

    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )

    class _Orig(Exception):
        sqlstate = "23503"

    async def _fk_boom(values: dict[str, Any]) -> dict[str, Any]:
        raise IntegrityError("insert", None, _Orig("fk"))

    monkeypatch.setattr(main_flow, "_db_insert_agent_run", _fk_boom)
    with pytest.raises(ZippinException) as excinfo:
        await main_flow.create_agent_run(
            session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
        )
    assert excinfo.value.code == "SESSION_NOT_FOUND"


async def test_runner_create_run_pre_insert_failure_emits_clean_error(
    fake: FakeMainFlowDb, monkeypatch: pytest.MonkeyPatch
) -> None:
    # #pre-insert-failure: precheck 이후 세션 삭제로 create_agent_run 이 row 생성 전에
    # 실패하면, generic except(update_agent_run→NOT_FOUND)로 가지 않고 깔끔히 error+done.
    from src.errors import ZippinException

    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )

    async def _boom(**kwargs: Any) -> dict[str, Any]:
        raise ZippinException("gone", code="SESSION_NOT_FOUND", http_status=404)

    monkeypatch.setattr(main_flow, "create_agent_run", _boom)
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=uuid.uuid4(),
    )
    frames = [
        f
        async for f in runner.stream(
            user_message="안녕", agent=_FakeAgent(_chunks()), create_run=True
        )
    ]
    events = _parse(frames)
    assert any(
        ev == "error" and d["error_code"] == "SESSION_NOT_FOUND" for ev, d in events
    )
    assert events[-1][0] == "done" and events[-1][1]["run_status"] == "failed"


def _tool_message_degraded() -> SimpleNamespace:
    # plain @tool 은 dict 반환을 content(JSON 문자열)로 싣고 status=success, artifact=None.
    return SimpleNamespace(
        tool_call_id="tc1",
        content=(
            '{"ok": false, "error_code": "SEGMENTATION_ENDPOINT_UNAVAILABLE", '
            '"summary": "미배포"}'
        ),
        status="success",
    )


async def test_translate_tool_content_failure_maps_to_failed() -> None:
    # #6: artifact 가 아니라 content(JSON) 의 ok=false 를 읽어 failed 로 매핑.
    chunks = [("updates", {"tools": {"messages": [_tool_message_degraded()]}})]
    signals = [s async for s in translate_stream(_aiter(chunks), tool_kinds={})]
    ends = [s for s in signals if isinstance(s, ToolEnd)]
    assert len(ends) == 1
    assert ends[0].status == "failed"
    assert ends[0].error_code == "SEGMENTATION_ENDPOINT_UNAVAILABLE"


async def test_runner_replayed_message_persists_once_with_stable_id(
    fake: FakeMainFlowDb,
) -> None:
    # #replay-on-resume: 같은 lc_message_id 가 두 번 와도 DB row 는 1개고, SSE message
    # 는 같은 message_id 로 재방출된다(resume 재연결 시 누락 방지 — 클라이언트가 dedupe).
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    final = _final_ai()
    chunks = [
        ("updates", {"agent": {"messages": [final]}}),
        ("updates", {"agent": {"messages": [final]}}),
    ]
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    frames = [
        f async for f in runner.stream(user_message="x", agent=_FakeAgent(chunks))
    ]
    msg_ids = [
        data["message_id"] for ev, data in _parse(frames) if ev == "message" and data
    ]
    # 두 번 emit 되지만 같은 message_id (클라이언트가 dedupe).
    assert len(msg_ids) == 2
    assert msg_ids[0] == msg_ids[1] and msg_ids[0] is not None
    # DB 에는 assistant row 가 1개만.
    assistant = [
        r
        for r in fake.chat_messages.values()
        if r["session_id"] == session["id"] and r["role"] == "assistant"
    ]
    assert len(assistant) == 1
    assistant = [r for r in fake.chat_messages.values() if r["role"] == "assistant"]
    assert len(assistant) == 1


async def test_finalize_preserves_cancelled_run(fake: FakeMainFlowDb) -> None:
    # #1: 스트리밍 중 /interrupt 가 cancelled 로 마감했으면 finalize 가 덮어쓰지 않음.
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    await main_flow.update_agent_run(run_id=run["id"], status="cancelled")
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    final = await runner._finalize("succeeded")
    assert final == "cancelled"
    assert fake.agent_runs[run["id"]]["status"] == "cancelled"


async def test_runner_releases_run_on_abandon(fake: FakeMainFlowDb) -> None:
    # #cancel: 클라이언트 abort 로 제너레이터가 aclose 되면 런이 running 으로 남지
    # 않고 interrupted 로 풀린다(다음 send 의 AGENT_RUN_ALREADY_ACTIVE 방지).
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    gen = runner.stream(user_message="x", agent=_FakeAgent(_chunks()))
    await gen.__anext__()  # 첫 프레임만 받고
    await gen.aclose()  # 연결 끊김 시뮬레이션
    assert fake.agent_runs[run["id"]]["status"] == "interrupted"
    assert fake.agent_runs[run["id"]]["finished_at"] is not None


async def test_consume_emits_heartbeat_while_waiting(fake: FakeMainFlowDb) -> None:
    # #heartbeat: 다음 청크가 늦으면 ': heartbeat' 프레임을 흘려 idle 연결을 유지한다.
    async def slow_stream():
        await asyncio.sleep(0.05)
        yield ("updates", {"agent": {"messages": [_final_ai()]}})

    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    sse = SseEventStream()
    deadline = time.monotonic() + 5.0
    frames = [
        f
        async for f in runner._consume(
            slow_stream(), sse, deadline, heartbeat_interval=0.01
        )
    ]
    assert any(f.startswith(": heartbeat") for f in frames)
    assert any("event: message" in f for f in frames)


async def test_claim_resumable_run_is_atomic(fake: FakeMainFlowDb) -> None:
    # #resume-atomic: 동시 resume 중 단 하나만 running 으로 점유, 나머지는 409.
    from src.errors import ZippinException

    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    # pending 은 resumable 아님 → 409.
    with pytest.raises(ZippinException) as e1:
        await main_flow.claim_resumable_agent_run(
            session_id=session["id"], run_id=run["id"], owner_user_id=owner
        )
    assert e1.value.code == "AGENT_RUN_NOT_RESUMABLE"

    await main_flow.update_agent_run(run_id=run["id"], status="interrupted")
    claimed = await main_flow.claim_resumable_agent_run(
        session_id=session["id"], run_id=run["id"], owner_user_id=owner
    )
    assert claimed["status"] == "running"
    # 두 번째 점유는 이미 running 이라 409.
    with pytest.raises(ZippinException) as e2:
        await main_flow.claim_resumable_agent_run(
            session_id=session["id"], run_id=run["id"], owner_user_id=owner
        )
    assert e2.value.code == "AGENT_RUN_NOT_RESUMABLE"


async def test_runner_finalizes_when_startup_projection_fails(
    fake: FakeMainFlowDb, monkeypatch
) -> None:
    # #startup-finalize: 사용자 메시지 투영이 실패해도 런이 running 으로 멈추지 않는다.
    from src.errors import ZippinException

    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )

    async def _boom(**_: Any) -> dict[str, Any]:
        raise ZippinException("gone", code="SESSION_NOT_FOUND", http_status=404)

    monkeypatch.setattr(main_flow, "append_chat_message", _boom)
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    frames = [
        f async for f in runner.stream(user_message="x", agent=_FakeAgent(_chunks()))
    ]
    assert fake.agent_runs[run["id"]]["status"] == "failed"
    assert any(ev == "error" for ev, _ in _parse(frames))


async def test_cancel_agent_run_preserves_terminal(fake: FakeMainFlowDb) -> None:
    # #interrupt-race: 자연 종료된 런을 interrupt 가 cancelled 로 덮어쓰지 않는다.
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    await main_flow.update_agent_run(
        run_id=run["id"], status="succeeded", finished_at=main_flow._now()
    )
    row = await main_flow.cancel_agent_run(
        session_id=session["id"], run_id=run["id"], owner_user_id=owner
    )
    assert row["status"] == "succeeded"
    assert fake.agent_runs[run["id"]]["status"] == "succeeded"


async def test_cancel_agent_run_cancels_active(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    row = await main_flow.cancel_agent_run(
        session_id=session["id"], run_id=run["id"], owner_user_id=owner
    )
    assert row["status"] == "cancelled"
    assert fake.agent_runs[run["id"]]["finished_at"] is not None


async def test_runner_create_run_marks_and_finalizes(fake: FakeMainFlowDb) -> None:
    # #pre-stream-orphan: create_run=True 면 row 를 generator 안에서 만들고 running
    # 으로 표시한 뒤 정상 마감한다.
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run_id = uuid.uuid4()
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run_id,
    )
    frames = [
        f
        async for f in runner.stream(
            user_message="x", agent=_FakeAgent(_chunks()), create_run=True
        )
    ]
    assert run_id in fake.agent_runs
    assert fake.agent_runs[run_id]["status"] == "succeeded"
    assert fake.agent_runs[run_id]["started_at"] is not None
    events = _parse(frames)
    assert events[-1][0] == "done" and events[-1][1]["run_status"] == "succeeded"


async def test_cancel_before_create_writes_tombstone(fake: FakeMainFlowDb) -> None:
    # #early-interrupt-race: 헤더로 노출된 run_id 로 generator insert 전에 /interrupt 가
    # 오면, row 가 없어도 cancelled 톰스톤을 남긴다(소유 세션 검증됨).
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run_id = uuid.uuid4()
    row = await main_flow.cancel_agent_run(
        session_id=session["id"], run_id=run_id, owner_user_id=owner
    )
    assert row["status"] == "cancelled"
    assert run_id in fake.agent_runs


async def test_runner_create_run_honors_precreated_cancel(
    fake: FakeMainFlowDb,
) -> None:
    # #early-interrupt-race: 이른 /interrupt 가 만든 cancelled 톰스톤을 generator 의 멱등
    # create 가 그대로 받고 mark_running 이 None → done(cancelled).
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run_id = uuid.uuid4()
    # generator 시작 전에 취소 톰스톤 생성.
    await main_flow.cancel_agent_run(
        session_id=session["id"], run_id=run_id, owner_user_id=owner
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run_id,
    )
    frames = [
        f
        async for f in runner.stream(
            user_message="x", agent=_FakeAgent(_chunks()), create_run=True
        )
    ]
    events = _parse(frames)
    assert events[-1][0] == "done" and events[-1][1]["run_status"] == "cancelled"
    assert fake.agent_runs[run_id]["status"] == "cancelled"


async def test_runner_create_run_conflict_emits_error(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    # 이미 활성 런이 있는 세션.
    existing = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    run_id = uuid.uuid4()
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run_id,
    )
    frames = [
        f
        async for f in runner.stream(
            user_message="x", agent=_FakeAgent(_chunks()), create_run=True
        )
    ]
    events = _parse(frames)
    # 에러에 활성 런 id/상태가 실려 클라이언트가 복구할 수 있다(#active-run-on-race).
    err = next(
        d
        for ev, d in events
        if ev == "error" and d["error_code"] == "AGENT_RUN_ALREADY_ACTIVE"
    )
    assert err["active_run_id"] == str(existing["id"])
    assert err["active_run_status"] == "pending"
    assert events[-1][0] == "done" and events[-1][1]["run_status"] == "failed"
    assert run_id not in fake.agent_runs  # 우리 row 는 만들어지지 않음


async def test_get_active_and_mark_running(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    assert (
        await main_flow.get_active_agent_run(
            session_id=session["id"], owner_user_id=owner
        )
        is None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    active = await main_flow.get_active_agent_run(
        session_id=session["id"], owner_user_id=owner
    )
    assert active is not None and active["id"] == run["id"]

    # pending → running.
    assert (await main_flow.mark_agent_run_running(run_id=run["id"]))["status"] == (
        "running"
    )
    # cancelled 면 mark 가 None(되살리지 않음, #startup-overwrite).
    await main_flow.update_agent_run(run_id=run["id"], status="cancelled")
    assert await main_flow.mark_agent_run_running(run_id=run["id"]) is None
    assert fake.agent_runs[run["id"]]["status"] == "cancelled"


async def test_runner_resume_claims_in_generator(fake: FakeMainFlowDb) -> None:
    # #resume-claim-orphan: resume 점유를 generator 안에서 한다.
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    # 이전 마감으로 finished_at 이 남아 있다.
    await main_flow.update_agent_run(
        run_id=run["id"], status="interrupted", finished_at=main_flow._now()
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    frames = [
        f
        async for f in runner.stream(
            user_message="계속", agent=_FakeAgent(_chunks()), resume=True
        )
    ]
    assert fake.agent_runs[run["id"]]["status"] == "succeeded"
    events = _parse(frames)
    assert events[-1][0] == "done" and events[-1][1]["run_status"] == "succeeded"


async def test_claim_clears_stale_finished_at(fake: FakeMainFlowDb) -> None:
    # #stale-finished-at: resume 점유 시 이전 마감의 finished_at/error 메타를 지운다.
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    await main_flow.update_agent_run(
        run_id=run["id"],
        status="interrupted",
        finished_at=main_flow._now(),
        error_code="X",
    )
    claimed = await main_flow.claim_resumable_agent_run(
        session_id=session["id"], run_id=run["id"], owner_user_id=owner
    )
    assert claimed["status"] == "running"
    assert claimed["finished_at"] is None
    assert claimed["error_code"] is None


class _CapturingAgent:
    """astream 입력 payload 를 기록하는 fake — 재연결 시 None 검증용."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = chunks
        self.payloads: list[Any] = []

    def astream(self, payload: Any, config: Any = None, stream_mode: Any = None):
        self.payloads.append(payload)
        return _aiter(self._chunks)


async def test_runner_reconnect_does_not_duplicate_turn(fake: FakeMainFlowDb) -> None:
    # #reconnect-idempotent: 체크포인트된(_STEP_STREAMING) interrupted 런 재개는 새
    # user 턴을 append/전송하지 않고 None 으로 이어 돌린다.
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    await main_flow.update_agent_run(
        run_id=run["id"], status="interrupted", current_step="streaming"
    )
    before = sum(
        1
        for m in fake.chat_messages.values()
        if m["session_id"] == session["id"] and m["role"] == "user"
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    agent = _CapturingAgent(_chunks())
    frames = [
        f async for f in runner.stream(user_message="계속", agent=agent, resume=True)
    ]
    # 재연결이므로 astream 에 새 user 메시지가 아니라 None 을 넘긴다(체크포인트 이어돌림).
    assert agent.payloads == [None]
    after = sum(
        1
        for m in fake.chat_messages.values()
        if m["session_id"] == session["id"] and m["role"] == "user"
    )
    assert after == before  # user 턴이 중복 append 되지 않음
    events = _parse(frames)
    assert events[-1][0] == "done"


async def test_runner_resume_awaiting_input_appends_turn(
    fake: FakeMainFlowDb,
) -> None:
    # awaiting_input 재개는 새 user 메시지를 정상 append/전송한다(재연결 아님).
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    await main_flow.update_agent_run(run_id=run["id"], status="awaiting_input")
    before = sum(
        1
        for m in fake.chat_messages.values()
        if m["session_id"] == session["id"] and m["role"] == "user"
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    agent = _CapturingAgent(_chunks())
    _ = [f async for f in runner.stream(user_message="네", agent=agent, resume=True)]
    assert agent.payloads[0] == {"messages": [{"role": "user", "content": "네"}]}
    after = sum(
        1
        for m in fake.chat_messages.values()
        if m["session_id"] == session["id"] and m["role"] == "user"
    )
    assert after == before + 1


async def test_runner_awaiting_input_followup_is_distinct_turn(
    fake: FakeMainFlowDb,
) -> None:
    # #per-turn-user-id: 같은 run 이라도 awaiting_input 후속(다른 내용)은 별도 user row.
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    await main_flow.update_agent_run(run_id=run["id"], status="awaiting_input")
    # 이미 같은 run 의 초기 턴("처음")이 투영돼 있다.
    first_key = hashlib.sha256("처음".encode()).hexdigest()[:16]
    await main_flow.append_chat_message(
        session_id=session["id"],
        owner_user_id=owner,
        payload={
            "content": "처음",
            "metadata": {"lc_message_id": f"user-turn:{run['id']}:{first_key}"},
        },
    )
    before = sum(
        1
        for m in fake.chat_messages.values()
        if m["session_id"] == session["id"] and m["role"] == "user"
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    agent = _CapturingAgent(_chunks())
    # 후속 답변(다른 내용)은 같은 run 이라도 새 row 로 기록된다.
    _ = [
        f
        async for f in runner.stream(user_message="추가답변", agent=agent, resume=True)
    ]
    after = sum(
        1
        for m in fake.chat_messages.values()
        if m["session_id"] == session["id"] and m["role"] == "user"
    )
    assert after == before + 1


async def test_runner_interrupted_before_checkpoint_resends(
    fake: FakeMainFlowDb,
) -> None:
    # #replay-after-accept: 턴이 그래프에 닿기 전(astream 진입 전) interrupted 된 런은
    # current_step 이 _STEP_STREAMING 이 아니므로 reconnect 가 아니라 재전송한다 —
    # 프롬프트 유실 방지.
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    # interrupted 지만 체크포인트 마커는 submitting(첫 출력 전에 끊김).
    await main_flow.update_agent_run(
        run_id=run["id"], status="interrupted", current_step="submitting"
    )
    # 원래 런이 이미 같은 내용의 user 턴을 투영했었다(lc id = user-turn:{run_id}:{hash}).
    content_key = hashlib.sha256("계속".encode()).hexdigest()[:16]
    await main_flow.append_chat_message(
        session_id=session["id"],
        owner_user_id=owner,
        payload={
            "content": "계속",
            "metadata": {"lc_message_id": f"user-turn:{run['id']}:{content_key}"},
        },
    )
    before = sum(
        1
        for m in fake.chat_messages.values()
        if m["session_id"] == session["id"] and m["role"] == "user"
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    agent = _CapturingAgent(_chunks())
    _ = [f async for f in runner.stream(user_message="계속", agent=agent, resume=True)]
    # 재전송이므로 None 이 아니라 메시지를 그래프에 넘긴다(프롬프트 유실 방지).
    assert agent.payloads[0] == {"messages": [{"role": "user", "content": "계속"}]}
    # 그러나 user 턴은 run_id 로 멱등 투영 → 중복 append 되지 않는다(#dup-user-turn).
    after = sum(
        1
        for m in fake.chat_messages.values()
        if m["session_id"] == session["id"] and m["role"] == "user"
    )
    assert after == before


async def test_list_session_chat_messages_history(fake: FakeMainFlowDb) -> None:
    # #load-history-on-mount: user/assistant 메시지를 시간순으로 복원(tool/system 제외).
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    await main_flow.append_chat_message(
        session_id=session["id"], owner_user_id=owner, payload={"content": "안녕"}
    )
    await main_flow.append_internal_chat_message(
        session_id=session["id"], role="assistant", content="네 도와드릴게요"
    )
    await main_flow.append_internal_chat_message(
        session_id=session["id"], role="tool", content="(내부)"
    )
    history = await main_flow.list_session_chat_messages(
        session_id=session["id"], owner_user_id=owner
    )
    roles = [m["role"] for m in history]
    assert roles == ["user", "assistant"]  # tool 제외, 시간순
    assert history[0]["content"] == "안녕"


async def test_runner_no_message_reconnect_drains_without_append(
    fake: FakeMainFlowDb,
) -> None:
    # #reconnect: user_message=None(no-message reconnect)은 새 턴을 append/전송하지 않고
    # 체크포인트에서 이어 받는다(astream None).
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    await main_flow.update_agent_run(
        run_id=run["id"], status="awaiting_input", current_step="streaming"
    )
    before = sum(
        1
        for m in fake.chat_messages.values()
        if m["session_id"] == session["id"] and m["role"] == "user"
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    agent = _CapturingAgent(_chunks())
    _ = [f async for f in runner.stream(user_message=None, agent=agent, resume=True)]
    assert agent.payloads == [None]  # 메시지 없이 체크포인트 이어 받기
    after = sum(
        1
        for m in fake.chat_messages.values()
        if m["session_id"] == session["id"] and m["role"] == "user"
    )
    assert after == before  # 새 user 턴 없음


async def test_runner_resume_not_resumable_errors(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    # pending 은 resumable 아님 → claim 실패.
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    frames = [
        f
        async for f in runner.stream(
            user_message="계속", agent=_FakeAgent(_chunks()), resume=True
        )
    ]
    events = _parse(frames)
    assert any(
        ev == "error" and d["error_code"] == "AGENT_RUN_NOT_RESUMABLE"
        for ev, d in events
    )
    assert events[-1][0] == "done" and events[-1][1]["run_status"] == "failed"


async def test_finalize_preserves_succeeded_terminal(fake: FakeMainFlowDb) -> None:
    # #preserve-terminal: 완료된 런을 disconnect cleanup 이 interrupted 로 강등하지 않음.
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    await main_flow.update_agent_run(
        run_id=run["id"], status="succeeded", finished_at=main_flow._now()
    )
    runner = AgentRunner(
        session_id=session["id"],
        owner_user_id=owner,
        owner_is_anonymous=False,
        run_id=run["id"],
    )
    final = await runner._finalize("interrupted")
    assert final == "succeeded"
    assert fake.agent_runs[run["id"]]["status"] == "succeeded"


async def test_finalize_agent_run_is_conditional(fake: FakeMainFlowDb) -> None:
    # #preserve-cancel: 마감은 비-terminal 일 때만. 이미 terminal 이면 None(덮어쓰지 않음).
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    run = await main_flow.create_agent_run(
        session_id=session["id"], owner_user_id=owner, model="openai:gpt-5.4-mini"
    )
    first = await main_flow.finalize_agent_run(run_id=run["id"], status="succeeded")
    assert first is not None and first["status"] == "succeeded"
    # 동시 cancel 후 마감 시도가 와도 succeeded 를 덮어쓰지 않는다.
    assert (
        await main_flow.finalize_agent_run(run_id=run["id"], status="interrupted")
        is None
    )
    assert fake.agent_runs[run["id"]]["status"] == "succeeded"
