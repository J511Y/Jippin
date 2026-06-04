from __future__ import annotations

from sqlalchemy import CheckConstraint, Text, UniqueConstraint

from src.models import Base, TermsConsent, User


def test_auth_tables_are_registered_without_legacy_shadow_tables() -> None:
    assert {"users", "terms_consents"}.issubset(Base.metadata.tables)
    assert "anonymous_users" not in Base.metadata.tables
    assert "external_sso_accounts" not in Base.metadata.tables
    assert "auth_identities" not in Base.metadata.tables


def test_user_profile_never_contains_password_or_shadow_identity_columns() -> None:
    column_names = set(User.__table__.c.keys())

    assert "password" not in column_names
    assert "password_hash" not in column_names
    assert "salt" not in column_names
    assert "email" not in column_names


def test_all_public_models_never_contain_password_columns() -> None:
    forbidden = {"password", "password_hash", "salt"}

    for table in Base.metadata.tables.values():
        assert forbidden.isdisjoint(table.c.keys())


def test_user_profile_id_references_supabase_auth_users() -> None:
    fk = next(iter(User.__table__.c.id.foreign_keys))

    assert fk.target_fullname == "auth.users.id"
    assert fk.ondelete == "CASCADE"
    assert User.__table__.c.id.server_default is None


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


def test_terms_consents_reference_supabase_auth_users() -> None:
    fk = next(iter(TermsConsent.__table__.c.user_id.foreign_keys))

    assert fk.target_fullname == "auth.users.id"
    assert fk.ondelete == "CASCADE"


def test_terms_consents_uniqueness_and_source_values_are_sealed() -> None:
    table = TermsConsent.__table__
    unique_constraints = {
        constraint.name: tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    check_constraints = {
        constraint.name: str(constraint.sqltext)
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert unique_constraints["uq_terms_consents_user_id_term_id_version"] == (
        "user_id",
        "term_id",
        "version",
    )
    assert (
        check_constraints["ck_terms_consents_terms_consents_source_allowed"]
        == "source IN ('kakao_sync', 'internal_signup')"
    )
