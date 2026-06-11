"""Phase A 채팅 라우터 skeleton (CMP-609).

공개 엔드포인트:

- ``POST /sessions/{id}/chat/messages`` → ``chat_messages`` row append (role=user 만)

`chat_tool_calls` lifecycle 은 사용자-facing route 가 아니다. agent runtime
/ rule engine 내부 서비스가 ``services.main_flow.start_chat_tool_call`` /
``complete_chat_tool_call`` 을 직접 호출한다 — board P2-4: 사용자 토큰만으로
``output`` / ``status`` 를 위조하지 못하게 막는다.

``ui_components`` (UI A2UI payload) 와 ``output`` (agent 내부 결과) 는 다른
컬럼이다 — schema 단에서 분리되어 있다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path

from ..auth.request_token import RequestUser, require_supabase_request_user
from ..logging import get_logger
from ..schemas.chat import (
    ChatMessageCreateRequest,
    ChatMessageResponse,
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
    row = await main_flow.append_chat_message(
        session_id=session_id,
        owner_user_id=requester.user_id,
        payload=payload.model_dump(),
        owner_is_anonymous=requester.is_anonymous,
    )
    logger.info(
        "chat_message_appended",
        session_id=str(session_id),
        message_id=str(row["id"]),
        role=row["role"],
    )
    return ChatMessageResponse.model_validate(row)
