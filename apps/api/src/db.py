from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import get_settings

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

_engine: Optional[AsyncEngine] = None
_migration_engine: Optional[AsyncEngine] = None
_checkpointer_pool: Optional["AsyncConnectionPool[Any]"] = None


def _normalize_async_url(url: str) -> str:
    # psycopg3 is the chosen async driver per CMP-528.
    if url.startswith(("postgresql+psycopg://", "postgresql+psycopg_async://")):
        return url
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def _create_engine(url: str) -> AsyncEngine:
    return create_async_engine(_normalize_async_url(url), pool_pre_ping=True)


def get_engine() -> AsyncEngine:
    """Pooler engine — request-path queries (short connections)."""
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.database_pool_url or settings.database_url
        if not url:
            raise RuntimeError(
                "Neither DATABASE_POOL_URL nor DATABASE_URL is configured. "
                "See apps/api/.env.example."
            )
        _engine = _create_engine(url)
    return _engine


def get_migration_engine() -> AsyncEngine:
    """Non-pooler engine — migrations / long-running transactions."""
    global _migration_engine
    if _migration_engine is None:
        settings = get_settings()
        url = settings.database_url
        if not url:
            raise RuntimeError(
                "DATABASE_URL is required for the migration engine. "
                "See apps/api/.env.example."
            )
        _migration_engine = _create_engine(url)
    return _migration_engine


def _psycopg_conninfo(url: str) -> str:
    """SQLAlchemy URL → libpq conninfo (psycopg_pool 은 driver suffix 를 모른다)."""
    for prefix in (
        "postgresql+psycopg://",
        "postgresql+psycopg_async://",
        "postgresql+asyncpg://",
    ):
        if url.startswith(prefix):
            return "postgresql://" + url[len(prefix) :]
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


async def get_checkpointer_pool() -> "AsyncConnectionPool[Any]":
    """LangGraph 체크포인터 전용 direct(:5432) psycopg async 풀.

    SQLAlchemy 엔진과 분리한다 — 체크포인터는 psycopg prepared statement 를 쓰는데
    Supabase 트랜잭션 풀러(:6543)에서 깨지므로 direct ``DATABASE_URL`` 을 쓴다.
    ``search_path=langgraph`` 로 스코프해 체크포인터의 unqualified 테이블이 전용
    스키마(migration 0015)로 해석되게 한다. config 의
    ``_validate_agent_checkpointer_url`` 가 pooler URL 사용을 부팅 시 차단한다.
    """
    global _checkpointer_pool
    if _checkpointer_pool is None:
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        settings = get_settings()
        url = settings.database_url
        if not url:
            raise RuntimeError(
                "DATABASE_URL (direct, :5432) is required for the agent checkpointer "
                "pool. See apps/api/.env.example."
            )
        pool: AsyncConnectionPool[Any] = AsyncConnectionPool(
            conninfo=_psycopg_conninfo(url),
            min_size=settings.checkpointer_pool_min_size,
            max_size=settings.checkpointer_pool_max_size,
            open=False,
            kwargs={
                "autocommit": True,
                "prepare_threshold": 0,
                "row_factory": dict_row,
                "options": f"-c search_path={settings.langgraph_db_schema}",
            },
        )
        await pool.open()
        _checkpointer_pool = pool
    return _checkpointer_pool


async def dispose_engines() -> None:
    global _engine, _migration_engine, _checkpointer_pool
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    if _migration_engine is not None:
        await _migration_engine.dispose()
        _migration_engine = None
    if _checkpointer_pool is not None:
        await _checkpointer_pool.close()
        _checkpointer_pool = None
