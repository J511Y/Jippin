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

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

ChatRole = Literal["user", "assistant", "system", "tool"]
# 공개 endpoint 에 client 가 직접 만들 수 있는 role 만. assistant/system/tool 은
# agent runtime / 내부 서비스만 ``services.main_flow.append_internal_chat_message``
# 로 생성한다. ``content_redacted``/``judgment_snapshot``/``ui_components`` 같은
# 내부 메타 필드도 같은 사유로 internal-only 다.
ClientChatRole = Literal["user"]
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


# SQLAlchemy 모델은 ``metadata`` 가 예약어이므로 컬럼을 ``metadata_`` 로 매핑한다
# (``apps/api/src/models/main_feature.py`` 의 ``ChatMessage`` / ``ChatToolCall``).
# Pydantic ``from_attributes=True`` 가 ORM row 에서 ``row.metadata`` 만 시도하면
# AttributeError 가 나기 때문에 두 이름 모두 받아들이는 alias 를 둔다 — dict
# 입력 (skeleton in-memory store) 은 ``metadata`` 키로, ORM row 는 ``metadata_``
# 속성으로 모두 검증된다 (board round-3 #2).
_METADATA_ALIAS = AliasChoices("metadata_", "metadata")


class ChatMessageCreateRequest(BaseModel):
    """`POST /sessions/{id}/chat/messages` body — 공개 endpoint.

    Client 가 직접 만들 수 있는 message 는 role=``user`` 만이다. assistant /
    system / tool message 는 agent runtime 이 ``main_flow`` 내부 함수로 만든다
    — 공개 endpoint 에서 신뢰할 수 없는 source 가 assistant role 을 흉내내
    judgment snapshot 이나 UI A2UI payload 를 주입하는 것을 막기 위해서다.
    """

    role: ClientChatRole = "user"
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID | None
    role: ChatRole
    content: str
    content_redacted: bool
    ui_components: list[Any]
    judgment_snapshot: dict[str, Any] | None
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias=_METADATA_ALIAS
    )
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
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

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
    metadata: dict[str, Any] = Field(
        default_factory=dict, validation_alias=_METADATA_ALIAS
    )
