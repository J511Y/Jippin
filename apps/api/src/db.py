from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .config import get_settings

_engine: Optional[AsyncEngine] = None
_migration_engine: Optional[AsyncEngine] = None


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


async def dispose_engines() -> None:
    global _engine, _migration_engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
    if _migration_engine is not None:
        await _migration_engine.dispose()
        _migration_engine = None
