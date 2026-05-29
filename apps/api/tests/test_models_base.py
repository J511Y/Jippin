from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import BigInteger, MetaData, Text
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.models import (
    AuditMixin,
    CreatedAtMixin,
    CreatedByMixin,
    NAMING_CONVENTION,
    TimestampMixin,
    utc_now,
)


class LocalBase(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class CreatedOnly(CreatedAtMixin, LocalBase):
    __tablename__ = "created_only"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class Timestamped(TimestampMixin, LocalBase):
    __tablename__ = "timestamped"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class CreatedBy(CreatedByMixin, LocalBase):
    __tablename__ = "created_by"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


class Audited(AuditMixin, LocalBase):
    __tablename__ = "audited"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)


def test_created_at_mixin_adds_utc_timestamp_defaults() -> None:
    column = CreatedOnly.__table__.c.created_at

    assert isinstance(column.type, postgresql.TIMESTAMP)
    assert column.type.timezone is True
    assert column.nullable is False
    assert column.default is not None
    assert callable(column.default.arg)
    assert column.default.arg(None).tzinfo is UTC
    assert column.server_default is not None


def test_timestamp_mixin_adds_updated_at_with_onupdate_policy() -> None:
    table = Timestamped.__table__

    assert set(table.c.keys()) == {"id", "created_at", "updated_at"}
    updated_at = table.c.updated_at
    assert isinstance(updated_at.type, postgresql.TIMESTAMP)
    assert updated_at.type.timezone is True
    assert updated_at.nullable is False
    assert updated_at.default is not None
    assert callable(updated_at.default.arg)
    assert updated_at.default.arg(None).tzinfo is UTC
    assert updated_at.onupdate is not None
    assert callable(updated_at.onupdate.arg)
    assert updated_at.onupdate.arg(None).tzinfo is UTC
    assert updated_at.server_default is not None


def test_created_by_mixin_keeps_auth_reference_loose() -> None:
    table = CreatedBy.__table__

    assert set(table.c.keys()) == {"id", "created_at", "created_by"}
    assert isinstance(table.c.created_by.type, Text)
    assert table.c.created_by.nullable is True
    assert not table.c.created_by.foreign_keys


def test_audit_mixin_adds_all_audit_columns_without_foreign_keys() -> None:
    table = Audited.__table__

    assert set(table.c.keys()) == {
        "id",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
    }
    assert isinstance(table.c.created_by.type, Text)
    assert isinstance(table.c.updated_by.type, Text)
    assert not table.c.created_by.foreign_keys
    assert not table.c.updated_by.foreign_keys


def test_utc_now_returns_timezone_aware_utc_datetime() -> None:
    value = utc_now()

    assert isinstance(value, datetime)
    assert value.tzinfo is UTC
