"""Alembic env (CMP-537).

봉인:
- sync 컨텍스트(`postgresql+psycopg://`)로만 동작한다. async 엔진은 사용하지 않는다 —
  alembic 의 운영 단순성을 위해 마이그레이션은 동기 트랜잭션으로 고정한다.
- URL 은 `apps/api/src/config.py:Settings.database_url` (non-pooler) 에서만 읽는다.
  pooler(`database_pool_url`)는 prepared statement 및 일부 DDL 호환성에 문제가 있어
  마이그레이션 경로에서 명시적으로 금지한다.
- `target_metadata = Base.metadata` — `src.models` 의 DeclarativeBase 가
  모든 모델 import 의 단일 진입점이다.

CTO ADR-0001 §4(Neon 클라이언트) 와 부모 CMP-536 의 분리 원칙(요청-경로 pooler /
DDL non-pooler)에 정렬된다.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# alembic 은 apps/api 루트에서 호출된다고 가정하지만, 컨테이너/CI 가 다른 cwd 에서
# 실행할 경우에도 src 패키지를 import 할 수 있도록 sys.path 를 보강한다.
_HERE = Path(__file__).resolve().parent
_APP_ROOT = _HERE.parent  # apps/api
if str(_APP_ROOT) not in sys.path:
    sys.path.insert(0, str(_APP_ROOT))

from src.config import get_settings  # noqa: E402
from src.models import Base  # noqa: E402

config = context.config

# Alembic ini 의 로깅 설정 적용. ini 가 없는 경로(예: 임베디드 호출)에서도 안전.
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)


def _resolve_database_url() -> str:
    """Settings.database_url 만 사용. pooler URL 은 명시적으로 차단한다."""
    settings = get_settings()
    url = settings.database_url
    if not url:
        raise RuntimeError(
            "DATABASE_URL is required for Alembic (non-pooler Neon URL). "
            "DATABASE_POOL_URL 은 마이그레이션에 사용할 수 없습니다 — "
            "apps/api/.env.example 와 ADR-0001 §4 참조.",
        )
    # psycopg3 sync 드라이버로 정규화. asyncpg/일반 postgresql 스킴은 동기로 강제 변환.
    if url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and not url.startswith("postgresql+"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """`--sql` 모드. 실제 DB 연결 없이 SQL 스크립트만 생성."""
    url = _resolve_database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """일반 경로 — Neon non-pooler 에 sync psycopg3 연결로 DDL 적용."""
    ini_section = config.get_section(config.config_ini_section) or {}
    ini_section["sqlalchemy.url"] = _resolve_database_url()

    connectable = engine_from_config(
        ini_section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        future=True,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
