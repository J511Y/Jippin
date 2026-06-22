"""이중 레이어 투영 writer — 에이전트 런타임 상태를 프로덕트 테이블로 투영.

LangGraph 체크포인터(``langgraph.*``)가 대화 정본이고, 본 모듈은 그 런타임이
흘리는 정규화 이벤트를 ``chat_messages`` / ``chat_tool_calls`` / ``sessions`` 로
**idempotent** 하게 투영한다. resume 가 커밋 상태를 replay 하므로 writer 는
replay-safe 해야 한다 — LC id(metadata->>'lc_*') 로 먼저 조회하고, 동시 race 는
DB 부분 유니크 인덱스(migration 0015)의 ``IntegrityError`` 로 잡아 "이미 투영됨"
으로 처리한다.

본 모듈은 langchain/deepagents 를 import 하지 않는다 — 런너가 raw astream 청크를
아래 정규화 이벤트로 변환해 넘긴다. 덕분에 투영 로직을 LLM 없이 단위 테스트할 수
있다(``tests/test_agent_projection.py``).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.exc import IntegrityError

from ..errors import ZippinException
from ..logging import get_logger
from ..services import main_flow

log = get_logger("zippin.agent.projection")


# --- 정규화 이벤트 (런너가 raw astream 청크를 이 형태로 변환) ----------------


@dataclass
class AssistantMessage:
    """완료된 assistant/system/tool 메시지 1건."""

    lc_message_id: str
    content: str
    role: str = "assistant"
    ui_components: list[dict[str, Any]] = field(default_factory=list)
    judgment_snapshot: dict[str, Any] | None = None


@dataclass
class ToolStart:
    lc_tool_call_id: str
    tool_name: str
    tool_kind: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolEnd:
    lc_tool_call_id: str
    status: str  # succeeded | failed | cancelled
    output: dict[str, Any] | None = None
    output_summary: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int | None = None


@dataclass
class DecisionChange:
    status: str | None = None
    completion_decision: Any = main_flow._UNSET


_UNSET = main_flow._UNSET


def _validate_judgment_snapshot(
    snapshot: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """common-judgment-schema 로 검증. 검증 불가/실패 시 fail-closed 로 드롭한다.

    contracts 바인딩이 런타임 이미지에 없으면(현재 api 이미지) 미검증 snapshot 을
    저장하지 않고 드롭한다 — downstream 계약 소비자가 잘못된 payload 를 받지 않도록
    (fail-closed). 운영에서 검증을 켜려면 zippin_contracts 를 런타임에 번들해야 한다.
    """

    if not snapshot:
        return None
    try:
        from zippin_contracts.common_judgment_schema import (  # type: ignore
            CommonJudgmentSchema,
        )
    except ImportError:
        log.warning("judgment_snapshot_validation_unavailable_dropped")
        return None
    try:
        CommonJudgmentSchema.model_validate(snapshot)
    except Exception as exc:  # noqa: BLE001 - 검증 실패는 드롭 + 로그
        log.warning("judgment_snapshot_invalid", error=str(exc))
        return None
    return snapshot


class ProjectionWriter:
    """한 런(session) 동안 정규화 이벤트를 프로덕트 테이블로 투영한다."""

    def __init__(self, *, session_id: uuid.UUID, owner_user_id: uuid.UUID) -> None:
        self.session_id = session_id
        self.owner_user_id = owner_user_id

    async def project_tool_start(self, ev: ToolStart) -> dict[str, Any] | None:
        existing = await main_flow.find_chat_tool_call_by_lc_id(
            session_id=self.session_id, lc_tool_call_id=ev.lc_tool_call_id
        )
        if existing is not None:
            return existing
        try:
            return await main_flow.start_chat_tool_call(
                session_id=self.session_id,
                owner_user_id=self.owner_user_id,
                payload={
                    "tool_name": ev.tool_name,
                    "tool_kind": ev.tool_kind,
                    "input": ev.input,
                    "metadata": {"lc_tool_call_id": ev.lc_tool_call_id},
                },
            )
        except IntegrityError:
            # 동시 race 백스톱 — 이미 투영됨.
            return await main_flow.find_chat_tool_call_by_lc_id(
                session_id=self.session_id, lc_tool_call_id=ev.lc_tool_call_id
            )

    async def project_tool_end(self, ev: ToolEnd) -> dict[str, Any] | None:
        row = await main_flow.find_chat_tool_call_by_lc_id(
            session_id=self.session_id, lc_tool_call_id=ev.lc_tool_call_id
        )
        if row is None:
            log.warning("tool_end_without_start", lc_tool_call_id=ev.lc_tool_call_id)
            return None
        if row["status"] != "started":
            # 이미 완료됨(resume replay) — idempotent skip.
            return row
        try:
            return await main_flow.complete_chat_tool_call(
                session_id=self.session_id,
                tool_call_id=row["id"],
                owner_user_id=self.owner_user_id,
                payload={
                    "status": ev.status,
                    "output": ev.output,
                    "output_summary": ev.output_summary,
                    "error_code": ev.error_code,
                    "error_message": ev.error_message,
                    "duration_ms": ev.duration_ms,
                },
            )
        except ZippinException as exc:
            if exc.code == "CHAT_TOOL_CALL_ALREADY_COMPLETED":
                return row
            raise

    async def project_message(
        self, ev: AssistantMessage
    ) -> tuple[dict[str, Any] | None, bool]:
        """메시지를 투영하고 ``(row, created)`` 를 돌려준다.

        ``created=False`` 면 (resume replay 등으로) 이미 투영된 메시지다 — 런너는
        이 경우 SSE message 프레임을 재전송하지 않는다(클라이언트 중복 방지).
        """

        existing = await main_flow.find_chat_message_by_lc_id(
            session_id=self.session_id, lc_message_id=ev.lc_message_id
        )
        if existing is not None:
            return existing, False
        snapshot = _validate_judgment_snapshot(ev.judgment_snapshot)
        try:
            row = await main_flow.append_internal_chat_message(
                session_id=self.session_id,
                role=ev.role,
                content=ev.content,
                ui_components=ev.ui_components,
                judgment_snapshot=snapshot,
                metadata={"lc_message_id": ev.lc_message_id},
            )
            return row, True
        except IntegrityError:
            row = await main_flow.find_chat_message_by_lc_id(
                session_id=self.session_id, lc_message_id=ev.lc_message_id
            )
            return row, False

    async def project_decision(self, ev: DecisionChange) -> dict[str, Any] | None:
        if ev.status is None and ev.completion_decision is _UNSET:
            return None
        return await main_flow.set_session_decision(
            session_id=self.session_id,
            status=ev.status,
            completion_decision=ev.completion_decision,
        )
