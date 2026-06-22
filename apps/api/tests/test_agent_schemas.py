"""에이전트 요청 스키마 계약 검증 (CMP-DIRECT).

agent-run-request 계약은 schema_version 을 required const 로 둔다 — 서버 모델도
누락 요청을 422 로 거절해야 한다(미래 incompatible 버전 boundary reject).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.schemas.agent import AgentRunResumeRequest, AgentRunStartRequest


def test_start_request_requires_schema_version() -> None:
    with pytest.raises(ValidationError):
        AgentRunStartRequest(message={"role": "user", "content": "hi"})


def test_resume_request_requires_schema_version() -> None:
    with pytest.raises(ValidationError):
        AgentRunResumeRequest(message={"role": "user", "content": "hi"})


def test_start_request_rejects_wrong_version() -> None:
    with pytest.raises(ValidationError):
        AgentRunStartRequest(
            schema_version="2.0.0", message={"role": "user", "content": "hi"}
        )


def test_start_request_accepts_versioned() -> None:
    req = AgentRunStartRequest(
        schema_version="1.0.0", message={"role": "user", "content": "hi"}
    )
    assert req.schema_version == "1.0.0"
    assert req.message.content == "hi"


def test_message_role_is_required() -> None:
    with pytest.raises(ValidationError):
        AgentRunStartRequest(schema_version="1.0.0", message={"content": "hi"})


def test_message_role_rejects_non_user() -> None:
    with pytest.raises(ValidationError):
        AgentRunStartRequest(
            schema_version="1.0.0",
            message={"role": "assistant", "content": "hi"},
        )
