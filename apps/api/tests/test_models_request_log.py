from __future__ import annotations

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import BigInteger, Boolean, Integer, Text
from sqlalchemy.dialects import postgresql

from src.models import Base, RequestLog


def test_request_logs_table_is_registered() -> None:
    table = Base.metadata.tables["request_logs"]

    assert RequestLog.__table__ is table
    assert isinstance(table.c.id.type, BigInteger)
    assert table.c.id.primary_key
    assert table.c.id.autoincrement is True
    assert isinstance(table.c.created_at.type, postgresql.TIMESTAMP)
    assert table.c.created_at.type.timezone is True
    assert table.c.created_at.nullable is False
    assert isinstance(table.c.request_id.type, postgresql.UUID)
    assert table.c.request_id.type.as_uuid is True
    assert isinstance(table.c.is_anonymous_user.type, Boolean)
    assert table.c.is_anonymous_user.nullable is False
    assert isinstance(table.c.ip_addrs.type, postgresql.ARRAY)
    assert isinstance(table.c.ip_addrs.type.item_type, Text)
    assert table.c.ip_addrs.nullable is False
    assert isinstance(table.c.last_ip.type, postgresql.INET)
    assert isinstance(table.c.parameter.type, postgresql.JSONB)
    assert table.c.parameter.nullable is False
    assert isinstance(table.c.body.type, postgresql.JSONB)
    assert isinstance(table.c.response_code.type, Integer)
    assert table.c.response_code.nullable is False
    assert isinstance(table.c.duration_ms.type, Integer)
    assert table.c.duration_ms.nullable is False


def test_request_logs_indexes_use_naming_convention() -> None:
    table = Base.metadata.tables["request_logs"]
    index_names = {index.name for index in table.indexes}

    assert index_names == {
        "ix_request_logs_created_at",
        "ix_request_logs_request_id",
        "ix_request_logs_last_ip",
        "ix_request_logs_response_code",
        "ix_request_logs_duration_ms",
        "ix_request_logs_user_id_created_at",
        "ix_request_logs_method_url_created_at",
    }


def test_alembic_head_is_request_logs_revision() -> None:
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)

    assert script.get_current_head() == "0004_request_logs"
