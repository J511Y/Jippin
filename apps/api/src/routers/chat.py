"""Phase A 채팅 / 툴콜 라우터 skeleton (CMP-609).

- ``POST /sessions/{id}/chat/messages`` → ``chat_messages`` row append
- ``POST /sessions/{id}/chat/tool-calls`` → ``chat_tool_calls`` row create (started)
- ``PATCH /sessions/{id}/chat/tool-calls/{tcid}`` → 완료/실패/취소 전이

``ui_components`` (UI A2UI payload) 와 ``output`` (agent 내부 결과) 는 다른
필드다 — schema 단에서 분리되어 있다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path

from ..auth.request_token import RequestUser, require_supabase_request_user
from ..logging import get_logger
from ..schemas.chat import (
    ChatMessageCreateRequest,
    ChatMessageResponse,
    ChatToolCallCompleteRequest,
    ChatToolCallResponse,
    ChatToolCallStartRequest,
)
from ..services import main_flow

logger = get_logger("zippin.chat")
router = APIRouter(prefix="/sessions", tags=["chat"])


@router.post(
    "/{session_id}/chat/messages",
    response_model=ChatMessageResponse,
    status_code=201,
)
async def append_chat_message(
    payload: ChatMessageCreateRequest,
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> ChatMessageResponse:
    row = main_flow.append_chat_message(
        session_id=session_id,
        owner_user_id=requester.user_id,
        payload=payload.model_dump(),
    )
    logger.info(
        "chat_message_appended",
        session_id=str(session_id),
        message_id=str(row["id"]),
        role=row["role"],
    )
    return ChatMessageResponse.model_validate(row)


@router.post(
    "/{session_id}/chat/tool-calls",
    response_model=ChatToolCallResponse,
    status_code=201,
)
async def start_chat_tool_call(
    payload: ChatToolCallStartRequest,
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> ChatToolCallResponse:
    row = main_flow.start_chat_tool_call(
        session_id=session_id,
        owner_user_id=requester.user_id,
        payload=payload.model_dump(),
    )
    logger.info(
        "chat_tool_call_started",
        session_id=str(session_id),
        tool_call_id=str(row["id"]),
        tool_name=row["tool_name"],
        tool_kind=row["tool_kind"],
    )
    return ChatToolCallResponse.model_validate(row)


@router.patch(
    "/{session_id}/chat/tool-calls/{tool_call_id}",
    response_model=ChatToolCallResponse,
)
async def complete_chat_tool_call(
    payload: ChatToolCallCompleteRequest,
    session_id: uuid.UUID = Path(...),
    tool_call_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> ChatToolCallResponse:
    row = main_flow.complete_chat_tool_call(
        session_id=session_id,
        tool_call_id=tool_call_id,
        owner_user_id=requester.user_id,
        payload=payload.model_dump(),
    )
    logger.info(
        "chat_tool_call_completed",
        session_id=str(session_id),
        tool_call_id=str(tool_call_id),
        status=row["status"],
    )
    return ChatToolCallResponse.model_validate(row)
