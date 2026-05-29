"""auth skeleton tables

revision: 0005_auth_skeleton / down: 0004_request_logs

CMP-559 adds the OAuth-only identity skeleton for anonymous users, users,
external SSO accounts, and canonical term consent audit rows.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_auth_skeleton"
down_revision: Union[str, Sequence[str], None] = "0004_request_logs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    provider_enum = postgresql.ENUM(
        "kakao",
        "naver",
        "google",
        name="external_sso_provider",
        create_type=False,
    )
    provider_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("profile_image_url", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Text(),
            server_default=sa.text("'active'"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Text(),
            server_default=sa.text("'user'"),
            nullable=False,
        ),
        sa.Column("last_login_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('active', 'suspended', 'deleted')",
            name=op.f("ck_users_users_status_allowed"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )

    op.create_table(
        "external_sso_accounts",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(always=False),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", provider_enum, nullable=False),
        sa.Column("provider_subject", sa.Text(), nullable=False),
        sa.Column("provider_email", sa.Text(), nullable=True),
        sa.Column(
            "linked_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("profile_image_url", sa.Text(), nullable=True),
        sa.Column(
            "raw_profile",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_external_sso_accounts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_external_sso_accounts")),
        sa.UniqueConstraint(
            "provider",
            "provider_subject",
            name=op.f("uq_external_sso_accounts_provider_provider_subject"),
        ),
        sa.UniqueConstraint(
            "user_id",
            "provider",
            name=op.f("uq_external_sso_accounts_user_id_provider"),
        ),
    )

    op.create_table(
        "anonymous_users",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("converted_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ip_hash", postgresql.BYTEA(), nullable=True),
        sa.Column("ua_hash", postgresql.BYTEA(), nullable=True),
        sa.Column(
            "last_seen_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("converted_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["converted_user_id"],
            ["users.id"],
            name=op.f("fk_anonymous_users_converted_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_anonymous_users")),
    )
    op.create_index(
        op.f("ix_anonymous_users_last_seen_at"),
        "anonymous_users",
        ["last_seen_at"],
    )

    op.create_table(
        "terms_consents",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("term_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column(
            "agreed_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('kakao_sync', 'internal_signup')",
            name=op.f("ck_terms_consents_terms_consents_source_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_terms_consents_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_terms_consents")),
        sa.UniqueConstraint(
            "user_id",
            "term_id",
            "version",
            name=op.f("uq_terms_consents_user_id_term_id_version"),
        ),
    )


def downgrade() -> None:
    op.drop_table("terms_consents")
    op.drop_index(
        op.f("ix_anonymous_users_last_seen_at"),
        table_name="anonymous_users",
    )
    op.drop_table("anonymous_users")
    op.drop_table("external_sso_accounts")
    op.drop_table("users")

    provider_enum = postgresql.ENUM(
        "kakao",
        "naver",
        "google",
        name="external_sso_provider",
        create_type=False,
    )
    provider_enum.drop(op.get_bind(), checkfirst=True)
