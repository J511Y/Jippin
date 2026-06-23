"""LangGraph Postgres 체크포인터 빌더 + 스키마 검증 — CMP-DIRECT.

체크포인터는 ``langgraph`` 전용 스키마(migration 0015)에 대화/상태를 영속한다.
운영 런타임에서 ``.setup()`` DDL 을 실행하지 않는다 — 마이그레이션이 SSOT 이고,
부팅 시 ``verify_schema()`` 로 테이블 존재만 검증한다(없으면 호출 측이 agent 를
fail-safe 로 비활성화). langgraph 는 함수 내부에서 lazy import 한다.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..config import get_settings
from ..db import get_checkpointer_pool
from ..logging import get_logger

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

log = get_logger("zippin.agent.checkpointer")

_checkpointer: "AsyncPostgresSaver | None" = None


async def get_checkpointer() -> "AsyncPostgresSaver":
    """프로세스 단위 단일 AsyncPostgresSaver(전용 direct 풀 위에서)."""

    global _checkpointer
    if _checkpointer is None:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        pool = await get_checkpointer_pool()
        _checkpointer = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
    return _checkpointer


async def verify_schema() -> bool:
    """langgraph 체크포인터 테이블 존재 검증(DDL 실행하지 않음).

    True = 스키마 준비됨. False = 마이그레이션 0015 미적용 등 — 호출 측이 agent
    기능을 끈다(자동 DDL 금지).
    """

    settings = get_settings()
    schema = settings.langgraph_db_schema
    try:
        pool = await get_checkpointer_pool()
        async with pool.connection() as conn:
            cur = await conn.execute(
                "select to_regclass(%s) is not null",
                (f"{schema}.checkpoints",),
            )
            row = await cur.fetchone()
    except Exception as exc:  # noqa: BLE001 - 검증 실패는 비활성화 신호
        log.error("checkpointer_schema_verify_failed", error=str(exc))
        return False

    present = bool(_first_value(row))
    if not present:
        log.error(
            "checkpointer_schema_missing",
            schema=schema,
            hint="apply supabase migration 0015 (langgraph schema)",
        )
    return present


def _first_value(row: Any) -> Any:
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()), None)
    return row[0]
