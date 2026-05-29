from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Text, UniqueConstraint
from sqlalchemy.dialects import postgresql

from src.models import (
    EXTERNAL_SSO_PROVIDER_VALUES,
    AnonymousUser,
    Base,
    ExternalSsoAccount,
    Term,
    TermsConsent,
    User,
)

AUTH_TABLES = (
    AnonymousUser.__table__,
    User.__table__,
    ExternalSsoAccount.__table__,
    Term.__table__,
    TermsConsent.__table__,
)


def test_auth_tables_are_registered() -> None:
    assert {
        "anonymous_users",
        "users",
        "external_sso_accounts",
        "terms",
        "terms_consents",
    }.issubset(Base.metadata.tables)


def test_user_model_never_contains_password_columns() -> None:
    column_names = set(User.__table__.c.keys())

    assert "password" not in column_names
    assert "password_hash" not in column_names


def test_user_status_lifecycle_is_sealed() -> None:
    table = User.__table__
    check_constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert isinstance(table.c.status.type, Text)
    assert table.c.status.nullable is False
    assert table.c.status.server_default is not None
    assert (
        check_constraints["ck_users_users_status_allowed"]
        == "status IN ('active', 'suspended', 'deleted')"
    )


def test_all_models_never_contain_password_columns() -> None:
    forbidden = {"password", "password_hash"}

    for table in Base.metadata.tables.values():
        assert forbidden.isdisjoint(table.c.keys())


def test_anonymous_user_conversion_fk_sets_null_on_user_delete() -> None:
    fk = next(iter(AnonymousUser.__table__.c.converted_user_id.foreign_keys))

    assert fk.target_fullname == "users.id"
    assert fk.ondelete == "SET NULL"
    assert AnonymousUser.__table__.c.converted_user_id.nullable is True


def test_anonymous_user_hash_columns_store_nullable_bytea_only() -> None:
    table = AnonymousUser.__table__

    assert isinstance(table.c.ip_hash.type, postgresql.BYTEA)
    assert isinstance(table.c.ua_hash.type, postgresql.BYTEA)
    assert table.c.ip_hash.nullable is True
    assert table.c.ua_hash.nullable is True


def test_external_sso_account_constraints_and_enum_are_sealed() -> None:
    table = ExternalSsoAccount.__table__
    unique_constraints = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }

    assert unique_constraints >= {
        ("provider", "provider_subject"),
        ("user_id", "provider"),
    }
    assert set(table.c.provider.type.enums) == set(EXTERNAL_SSO_PROVIDER_VALUES)
    assert set(EXTERNAL_SSO_PROVIDER_VALUES) == {"kakao", "naver", "google"}
    assert "email" not in table.c
    assert isinstance(table.c.provider_email.type, Text)
    assert table.c.provider_email.nullable is True
    assert table.c.user_id.foreign_keys
    assert next(iter(table.c.user_id.foreign_keys)).ondelete == "CASCADE"


def test_terms_table_shape() -> None:
    table = Term.__table__

    assert isinstance(table.c.id.type, BigInteger)
    assert isinstance(table.c.code.type, Text)
    assert table.c.code.unique is True
    assert isinstance(table.c.is_required.type, Boolean)
    assert table.c.is_required.nullable is False
    assert table.c.is_required.server_default is not None
    assert isinstance(table.c.effective_at.type, postgresql.TIMESTAMP)
    assert table.c.effective_at.type.timezone is True


def test_terms_consent_constraints_are_sealed() -> None:
    table = TermsConsent.__table__
    unique_constraints = {
        constraint.name: tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    check_constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert unique_constraints["uq_terms_consents_user_id_term_id"] == (
        "user_id",
        "term_id",
    )
    assert (
        check_constraints["ck_terms_consents_terms_consents_source_allowed"]
        == "source IN ('kakao_sync', 'internal_signup')"
    )
    assert next(iter(table.c.user_id.foreign_keys)).target_fullname == "users.id"
    assert next(iter(table.c.user_id.foreign_keys)).ondelete == "CASCADE"
    assert next(iter(table.c.term_id.foreign_keys)).target_fullname == "terms.id"


def test_auth_tables_use_timestamp_mixin() -> None:
    for table in AUTH_TABLES:
        assert "created_at" in table.c
        assert "updated_at" in table.c
        assert isinstance(table.c.created_at.type, postgresql.TIMESTAMP)
        assert isinstance(table.c.updated_at.type, postgresql.TIMESTAMP)
        assert table.c.created_at.type.timezone is True
        assert table.c.updated_at.type.timezone is True
        assert table.c.created_at.nullable is False
        assert table.c.updated_at.nullable is False
