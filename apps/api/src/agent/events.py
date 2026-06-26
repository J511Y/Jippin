"""SSE 이벤트 envelope 빌더 — agent-sse-event 계약 정합(순수 모듈).

각 메서드는 ``packages/contracts/schemas/agent-sse-event.schema.json`` 의 한 variant
를 만들고, SSE wire frame 문자열(``event: <type>\\ndata: <json>\\n\\n``)을 반환한다.
런 단위 단조 증가 ``seq`` 를 들고 있어, 클라이언트가 순서/유실을 판단할 수 있다.
"""

from __future__ import annotations

import json
from typing import Any

_SCHEMA_VERSION = "1.0.0"


def _frame(event_type: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event_type}\ndata: {payload}\n\n"


class SseEventStream:
    """SSE 프레임 빌더. ``seq`` 카운터를 캡슐화한다."""

    def __init__(self) -> None:
        self._seq = 0

    def _base(self, event_type: str) -> dict[str, Any]:
        seq = self._seq
        self._seq += 1
        return {"schema_version": _SCHEMA_VERSION, "type": event_type, "seq": seq}

    def token(self, delta: str) -> str:
        data = self._base("token")
        data["delta"] = delta
        return _frame("token", data)

    def tool_step(
        self,
        *,
        tool_name: str,
        tool_kind: str,
        status: str,
        summary: str | None = None,
        error_code: str | None = None,
        todos: list[dict[str, Any]] | None = None,
    ) -> str:
        data = self._base("tool_step")
        data["tool_name"] = tool_name
        data["tool_kind"] = tool_kind
        data["status"] = status
        data["summary"] = summary
        data["error_code"] = error_code
        # 계획(deepagents write_todos)일 때만 단계 목록을 싣는다 — 프론트 PlanPanel 용.
        # [{content, status}] 형태. write_todos 외 도구에서는 키 자체를 생략한다.
        if todos is not None:
            data["todos"] = todos
        return _frame("tool_step", data)

    def state_change(
        self, *, session_status: str, completion_decision: str | None = None
    ) -> str:
        data = self._base("state_change")
        data["session_status"] = session_status
        data["completion_decision"] = completion_decision
        return _frame("state_change", data)

    def message(
        self,
        *,
        role: str,
        content: str,
        message_id: str | None = None,
        ui_components: list[dict[str, Any]] | None = None,
    ) -> str:
        data = self._base("message")
        data["role"] = role
        data["content"] = content
        data["message_id"] = message_id
        data["ui_components"] = ui_components or []
        return _frame("message", data)

    def error(
        self,
        *,
        error_code: str,
        message: str,
        recoverable: bool,
        active_run_id: str | None = None,
        active_run_status: str | None = None,
    ) -> str:
        data = self._base("error")
        data["error_code"] = error_code
        data["message"] = message
        data["recoverable"] = recoverable
        data["active_run_id"] = active_run_id
        data["active_run_status"] = active_run_status
        return _frame("error", data)

    def done(self, *, run_status: str) -> str:
        data = self._base("done")
        data["run_status"] = run_status
        return _frame("done", data)

    @staticmethod
    def heartbeat() -> str:
        """SSE 주석 프레임 — idle 연결 keep-alive(프록시 타임아웃 방지)."""
        return ": heartbeat\n\n"
