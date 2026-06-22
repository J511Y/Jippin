"""에이전트 세션 라우터 Pydantic 계약 (CMP-DIRECT).

JSON Schema 정본은 ``packages/contracts/schemas/agent-*.schema.json`` 이다. 본
모듈은 라우터 입출력용 서버측 모델로, chat.py 와 같은 패턴을 따른다.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentUserMessage(BaseModel):
    """클라이언트가 만들 수 있는 유일한 메시지 — role=user.

    계약상 ``role`` 은 required(const "user") 다 — default 를 두지 않아 누락/오류
    role 을 422 로 거절한다(서버 경계를 계약과 일치시킨다). 계약의 additionalProperties
    :false 와 맞추려 extra="forbid" 로 미지원 필드를 거절한다.
    """

    model_config = ConfigDict(extra="forbid")

    role: Literal["user"] = Field(...)
    content: str = Field(min_length=1)


class AgentRunStartRequest(BaseModel):
    """`POST /sessions/{id}/agent/runs` body — agent-run-request 계약 정합.

    ``schema_version`` required, ``metadata`` optional. 계약과 동일하게 extra 필드를
    forbid 한다(미지원 필드를 조용히 버리지 않고 422).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = Field(...)
    message: AgentUserMessage
    metadata: dict[str, Any] | None = None


class AgentRunResumeRequest(BaseModel):
    """`POST /sessions/{id}/agent/runs/{run_id}/resume` body — 후속 사용자 입력."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0.0"] = Field(...)
    message: AgentUserMessage
    metadata: dict[str, Any] | None = None


class AgentRunStatusResponse(BaseModel):
    """`GET /sessions/{id}/agent/runs/{run_id}` — agent_runs row 투영."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    id: uuid.UUID
    session_id: uuid.UUID
    thread_id: uuid.UUID
    status: str
    model: str
    current_step: str | None
    langsmith_run_url: str | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
