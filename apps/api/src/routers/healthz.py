from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import text

from ..config import get_settings
from ..db import get_engine
from ..logging import get_logger

logger = get_logger("zippin.healthz")
router = APIRouter(tags=["health"])


async def _probe_db() -> dict[str, Any]:
    settings = get_settings()
    if settings.test_mode:
        return {"ok": True, "select_1": 1, "mode": "test"}

    try:
        engine = get_engine()
    except RuntimeError as exc:
        return {"ok": False, "error": str(exc)}

    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            row = result.scalar()
            return {"ok": row == 1, "select_1": row}
    except Exception as exc:  # noqa: BLE001 — health probe must not raise
        logger.warning("healthz_db_failed", error=str(exc))
        return {"ok": False, "error": exc.__class__.__name__}


@router.get("/healthz")
async def healthz(request: Request) -> dict[str, Any]:
    settings = get_settings()
    return {
        "status": "ok",
        "db": await _probe_db(),
        "version": settings.api_version,
        "request_id": getattr(request.state, "request_id", "-"),
    }
