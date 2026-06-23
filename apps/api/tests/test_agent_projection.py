"""투영 writer 단위 테스트 — idempotency + resume replay (CMP-DIRECT).

LLM 없이 main_flow seam fake 위에서 정규화 이벤트를 투영하고, 같은 이벤트를 다시
넣어도(resume replay) 중복 row 가 생기지 않음을 검증한다.
"""

from __future__ import annotations

import uuid

import pytest

from src.agent.projection import (
    AssistantMessage,
    DecisionChange,
    ProjectionWriter,
    ToolEnd,
    ToolStart,
)
from src.services import main_flow
from tests._main_flow_db_fake import FakeMainFlowDb, install_main_flow_fake


@pytest.fixture
def fake(monkeypatch) -> FakeMainFlowDb:
    return install_main_flow_fake(monkeypatch)


async def _make_session(owner: uuid.UUID) -> uuid.UUID:
    row = await main_flow.create_session(
        user_id=owner, is_anonymous_owner=False, judgment_schema_version=None
    )
    return row["id"]


async def test_tool_projection_idempotent_on_replay(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session_id = await _make_session(owner)
    writer = ProjectionWriter(session_id=session_id, owner_user_id=owner)

    start = ToolStart(
        lc_tool_call_id="tc-1",
        tool_name="segment_floorplan",
        tool_kind="ai_model",
        input={"image_url": "x"},
    )
    end = ToolEnd(
        lc_tool_call_id="tc-1",
        status="succeeded",
        output={"ok": True},
        output_summary="done",
    )

    await writer.project_tool_start(start)
    await writer.project_tool_end(end)
    # resume replay — 같은 LC 이벤트 재투입.
    await writer.project_tool_start(start)
    await writer.project_tool_end(end)

    rows = [r for r in fake.chat_tool_calls.values() if r["session_id"] == session_id]
    assert len(rows) == 1
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["tool_kind"] == "ai_model"
    assert rows[0]["metadata"]["lc_tool_call_id"] == "tc-1"
    # 원장에는 redacted 값만 — 원본 image_url(서명 URL 가능)은 저장 안 함.
    assert rows[0]["input"] == {"image_url": "[redacted]"}


async def test_failed_tool_marks_ledger_failed(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session_id = await _make_session(owner)
    writer = ProjectionWriter(session_id=session_id, owner_user_id=owner)

    await writer.project_tool_start(
        ToolStart(
            lc_tool_call_id="tc-9",
            tool_name="segment_floorplan",
            tool_kind="ai_model",
        )
    )
    await writer.project_tool_end(
        ToolEnd(
            lc_tool_call_id="tc-9",
            status="failed",
            error_code="SEGMENTATION_ENDPOINT_UNAVAILABLE",
            output_summary="미배포",
        )
    )

    row = next(
        r for r in fake.chat_tool_calls.values() if r["session_id"] == session_id
    )
    assert row["status"] == "failed"
    assert row["error_code"] == "SEGMENTATION_ENDPOINT_UNAVAILABLE"


async def test_message_projection_idempotent_with_ui(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session_id = await _make_session(owner)
    writer = ProjectionWriter(session_id=session_id, owner_user_id=owner)

    msg = AssistantMessage(
        lc_message_id="m-1",
        content="분석 결과입니다.",
        ui_components=[{"kind": "wall_summary", "payload": {}}],
    )
    await writer.project_message(msg)
    await writer.project_message(msg)  # replay

    rows = [
        r
        for r in fake.chat_messages.values()
        if r["session_id"] == session_id and r["role"] == "assistant"
    ]
    assert len(rows) == 1
    assert rows[0]["ui_components"] == [{"kind": "wall_summary", "payload": {}}]
    assert rows[0]["user_id"] is None
    assert rows[0]["metadata"]["lc_message_id"] == "m-1"


async def test_invalid_judgment_snapshot_is_dropped(fake: FakeMainFlowDb) -> None:
    # fail-closed: 검증 불가/실패 시 미검증 snapshot 을 저장하지 않고 드롭한다.
    owner = uuid.uuid4()
    session_id = await _make_session(owner)
    writer = ProjectionWriter(session_id=session_id, owner_user_id=owner)

    await writer.project_message(
        AssistantMessage(
            lc_message_id="m-snap",
            content="결과",
            judgment_snapshot={"definitely": "not-a-valid-common-judgment-schema"},
        )
    )
    row = next(
        r
        for r in fake.chat_messages.values()
        if r["session_id"] == session_id and r["role"] == "assistant"
    )
    assert row["judgment_snapshot"] is None


async def test_decision_projection_sets_completion_decision(
    fake: FakeMainFlowDb,
) -> None:
    owner = uuid.uuid4()
    session_id = await _make_session(owner)
    writer = ProjectionWriter(session_id=session_id, owner_user_id=owner)

    await writer.project_decision(DecisionChange(completion_decision="ASK_MORE"))

    assert fake.sessions[session_id]["completion_decision"] == "ASK_MORE"


async def test_tool_end_without_start_is_noop(fake: FakeMainFlowDb) -> None:
    owner = uuid.uuid4()
    session_id = await _make_session(owner)
    writer = ProjectionWriter(session_id=session_id, owner_user_id=owner)

    result = await writer.project_tool_end(
        ToolEnd(lc_tool_call_id="missing", status="succeeded")
    )
    assert result is None
    assert not [
        r for r in fake.chat_tool_calls.values() if r["session_id"] == session_id
    ]
