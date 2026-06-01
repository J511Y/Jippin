"""auth identities table

revision: 0007_auth_identities / down: 0006_terms_consent_unique_key

CMP-595 introduces a generic identity-bridge table mapping a third-party
authenticator subject (e.g., Supabase Auth user UUID) to a jippin ``users.id``.
This is the canonical lookup the ``POST /auth/supabase/session`` endpoint
uses to mint a jippin session cookie from a verified Supabase access token.
The link-writer side (CMP-579 / CMP-583 link ladder) populates rows; the
session-bridge endpoint is read-only and 401s when no mapping exists.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_auth_identities"
down_revision: Union[str, Sequence[str], None] = "0006_terms_consent_unique_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("external_id", sa.Text(), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
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
            "provider IN ('supabase')",
            name=op.f("ck_auth_identities_auth_identities_provider_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_identities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_identities")),
        sa.UniqueConstraint(
            "provider",
            "external_id",
            name=op.f("uq_auth_identities_provider_external_id"),
        ),
        sa.UniqueConstraint(
            "provider",
            "user_id",
            name=op.f("uq_auth_identities_provider_user_id"),
        ),
    )


def downgrade() -> None:
    op.drop_table("auth_identities")
