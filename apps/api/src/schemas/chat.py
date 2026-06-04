"""Pydantic contracts for Phase A 채팅/툴콜 (CMP-609).

DB 정본은 ``docs/plans/main-feature-db-schema-v0.1.md`` 의 ``chat_messages``
와 ``chat_tool_calls`` 다. 다음 두 가지 비고에 정합된다:

- ``chat_messages.ui_components`` 는 사용자에게 렌더링할 A2UI payload 다.
- ``chat_tool_calls.output`` 또는 ``output_summary`` 는 에이전트 내부 추론
  용도이며 UI 로 렌더링되지 않아도 저장 가능하다. 둘을 혼동하지 않는다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

ChatRole = Literal["user", "assistant", "system", "tool"]
ToolKind = Literal[
    "retrieval",
    "db_query",
    "external_api",
    "ai_model",
    "rule_engine",
    "render",
    "notification",
    "other",
]
ToolCallStatus = Literal["started", "succeeded", "failed", "cancelled"]


class ChatMessageCreateRequest(BaseModel):
    role: ChatRole
    content: str
    content_redacted: bool = False
    ui_components: list[Any] = Field(default_factory=list)
    judgment_snapshot: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID | None
    role: ChatRole
    content: str
    content_redacted: bool
    ui_components: list[Any]
    judgment_snapshot: dict[str, Any] | None
    metadata: dict[str, Any]
    created_at: datetime


class ChatToolCallStartRequest(BaseModel):
    """`POST /sessions/{id}/chat/tool-calls` body — `status='started'` 만 만든다.

    완료/실패는 별도 PATCH 로 처리해 ``started_at`` / ``completed_at`` 페어를
    확실히 남긴다.
    """

    message_id: uuid.UUID | None = None
    parent_tool_call_id: uuid.UUID | None = None
    tool_name: str = Field(min_length=1)
    tool_kind: ToolKind
    input: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatToolCallCompleteRequest(BaseModel):
    """`PATCH /sessions/{id}/chat/tool-calls/{id}` body — 완료/실패/취소.

    ``output`` 이 너무 크면 ``output_summary`` 만 채워도 된다. 둘 다 None
    이어도 허용한다 (예: notification tool 처럼 의미 있는 output 이 없는 경우).
    """

    status: Literal["succeeded", "failed", "cancelled"]
    output: dict[str, Any] | None = None
    output_summary: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class ChatToolCallResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    message_id: uuid.UUID | None
    parent_tool_call_id: uuid.UUID | None
    user_id: uuid.UUID | None
    tool_name: str
    tool_kind: ToolKind
    status: ToolCallStatus
    input: dict[str, Any]
    output: dict[str, Any] | None
    output_summary: str | None
    error_code: str | None
    error_message: str | None
    duration_ms: int | None
    started_at: datetime
    completed_at: datetime | None
    metadata: dict[str, Any]
