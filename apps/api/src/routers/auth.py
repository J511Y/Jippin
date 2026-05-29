from __future__ import annotations

from fastapi import APIRouter, Request

from ..logging import get_logger
from ..schemas.auth import AnonymousUserCreateRequest, AnonymousUserCreateResponse
from ..services.auth import create_or_reuse_anonymous_user

logger = get_logger("zippin.auth")
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/anonymous-users", response_model=AnonymousUserCreateResponse)
async def create_anonymous_user(
    payload: AnonymousUserCreateRequest,
    request: Request,
) -> AnonymousUserCreateResponse:
    result = await create_or_reuse_anonymous_user(payload.existing_anonymous_user_id)
    logger.info(
        "anonymous_user_resolved",
        anonymous_user_id=str(result.anonymous_user_id),
        reused=result.reused,
        request_id=getattr(request.state, "request_id", "-"),
    )
    return AnonymousUserCreateResponse(
        anonymous_user_id=result.anonymous_user_id,
        reused=result.reused,
    )
