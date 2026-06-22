"""런너 + 스트림 번역 테스트 — SSE 시퀀스 + agent_runs 전이 (CMP-DIRECT).

deepagents/LLM 을 mock 한 fake agent 의 astream 청크를 주입해, 번역기(translate_stream)
와 런너(AgentRunner.stream)가 올바른 정규화 시그널/ SSE 프레임을 내고 런 라이프사이클을
마감하는지 검증한다.
"""

from __future__ import annotations

import asyncio
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


async def test_runner_dedupes_replayed_message(fake: FakeMainFlowDb) -> None:
    # #5: 같은 lc_message_id 가 두 번 와도(resume replay) message SSE 는 1회만.
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
    message_events = [ev for ev, _ in _parse(frames) if ev == "message"]
    assert len(message_events) == 1
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


async def test_runner_create_run_conflict_emits_error(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    # 이미 활성 런이 있는 세션.
    await main_flow.create_agent_run(
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
    assert any(
        ev == "error" and d["error_code"] == "AGENT_RUN_ALREADY_ACTIVE"
        for ev, d in events
    )
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
    await main_flow.update_agent_run(run_id=run["id"], status="interrupted")
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
