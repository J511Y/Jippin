"""에이전트 세션 라우터 — SSE 스트리밍(CMP-DIRECT).

엔드포인트(prefix ``/sessions``):
- ``POST   /{id}/agent/runs``                 런 시작 → SSE 스트림
- ``POST   /{id}/agent/runs/{run_id}/resume`` 후속 입력으로 재개 → SSE 스트림
- ``POST   /{id}/agent/runs/{run_id}/interrupt`` 런 취소
- ``GET    /{id}/agent/runs/{run_id}``        런 상태(재연결용, 재스트림 없음)

브라우저는 api.jippin.ai 로 직접 연결한다(Vercel 우회). EventSource 는 헤더를 못
실으므로 클라이언트는 fetch+ReadableStream POST + Authorization 헤더로 연결한다.
런 루프는 요청 커넥션과 분리된 DB 경로(main_flow→get_engine 풀러)로 기록한다.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import StreamingResponse

from ..agent.runner import AgentRunner
from ..auth.request_token import RequestUser, require_supabase_request_user
from ..config import get_settings
from ..errors import ZippinException
from ..logging import get_logger
from ..schemas.agent import (
    AgentRunResumeRequest,
    AgentRunStartRequest,
    AgentRunStatusResponse,
)
from ..services import main_flow

logger = get_logger("zippin.agent")
router = APIRouter(prefix="/sessions", tags=["agent"])

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    # nginx/프록시 버퍼링 차단 — SSE 가 즉시 flush 되도록.
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}


def _require_agent_ready(request: Request) -> None:
    """체크포인터 스키마 누락 등 fail-safe 비활성화 시 503(lifespan 이 설정)."""

    if not getattr(request.app.state, "agent_ready", True):
        raise ZippinException(
            "Agent is temporarily unavailable.",
            code="AGENT_UNAVAILABLE",
            http_status=503,
        )


@router.post("/{session_id}/agent/runs")
async def start_agent_run(
    payload: AgentRunStartRequest,
    request: Request,
    session_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> StreamingResponse:
    _require_agent_ready(request)
    settings = get_settings()
    run = await main_flow.create_agent_run(
        session_id=session_id,
        owner_user_id=requester.user_id,
        model=settings.agent_model,
        input_summary={"content_chars": len(payload.message.content)},
        owner_is_anonymous=requester.is_anonymous,
    )
    logger.info("agent_run_started", session_id=str(session_id), run_id=str(run["id"]))
    runner = AgentRunner(
        session_id=session_id,
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
        run_id=run["id"],
    )
    generator = runner.stream(
        user_message=payload.message.content,
        is_disconnected=request.is_disconnected,
    )
    # 클라이언트가 resumable 종료(interrupted/awaiting_input) 후 /resume 를 호출할 수
    # 있도록 run_id 를 헤더로 노출한다(SSE 본문 파싱 전에 읽힘). CORS expose 필요.
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={**_SSE_HEADERS, "X-Agent-Run-Id": str(run["id"])},
    )


@router.post("/{session_id}/agent/runs/{run_id}/resume")
async def resume_agent_run(
    payload: AgentRunResumeRequest,
    request: Request,
    session_id: uuid.UUID = Path(...),
    run_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> StreamingResponse:
    _require_agent_ready(request)
    # resumable 런을 원자적으로 점유한다 — 동시 resume(두 탭/더블서브밋) 중 하나만
    # 성공하고 나머지는 409(같은 row 라 활성-런 유니크로는 못 막는다).
    await main_flow.claim_resumable_agent_run(
        session_id=session_id,
        run_id=run_id,
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
    )
    logger.info("agent_run_resumed", session_id=str(session_id), run_id=str(run_id))
    runner = AgentRunner(
        session_id=session_id,
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
        run_id=run_id,
    )
    generator = runner.stream(
        user_message=payload.message.content,
        is_disconnected=request.is_disconnected,
    )
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={**_SSE_HEADERS, "X-Agent-Run-Id": str(run_id)},
    )


@router.post(
    "/{session_id}/agent/runs/{run_id}/interrupt",
    response_model=AgentRunStatusResponse,
)
async def interrupt_agent_run(
    session_id: uuid.UUID = Path(...),
    run_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> AgentRunStatusResponse:
    # 조건부 취소 — status read 이후 자연 종료되는 race 에서 terminal 을 덮어쓰지
    # 않는다(이미 terminal 이면 그 row 를 그대로 반환, idempotent).
    row = await main_flow.cancel_agent_run(
        session_id=session_id,
        run_id=run_id,
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
    )
    logger.info("agent_run_interrupted", session_id=str(session_id), run_id=str(run_id))
    return AgentRunStatusResponse.model_validate(row)


@router.get(
    "/{session_id}/agent/runs/{run_id}",
    response_model=AgentRunStatusResponse,
)
async def get_agent_run_status(
    session_id: uuid.UUID = Path(...),
    run_id: uuid.UUID = Path(...),
    requester: RequestUser = Depends(require_supabase_request_user),
) -> AgentRunStatusResponse:
    run = await main_flow.get_agent_run(
        session_id=session_id,
        run_id=run_id,
        owner_user_id=requester.user_id,
        owner_is_anonymous=requester.is_anonymous,
    )
    return AgentRunStatusResponse.model_validate(run)
