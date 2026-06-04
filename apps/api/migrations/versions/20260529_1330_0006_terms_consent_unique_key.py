"""align terms consent unique key

revision: 0006_terms_consent_unique_key / down: 0005_auth_skeleton

CMP-562 aligns Kakao Sync consent upsert with the CMP-559 canonical
terms_consents uniqueness contract: one consent row per user, term, and version.
"""

from __future__ import annotations

from alembic import op

revision: str = "0006_terms_consent_unique_key"
down_revision: str | None = "0005_auth_skeleton"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("uq_terms_consents_user_id_term_id_version_source"),
        "terms_consents",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_terms_consents_user_id_term_id_version"),
        "terms_consents",
        ["user_id", "term_id", "version"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_terms_consents_user_id_term_id_version"),
        "terms_consents",
        type_="unique",
    )
    op.create_unique_constraint(
        op.f("uq_terms_consents_user_id_term_id_version_source"),
        "terms_consents",
        ["user_id", "term_id", "version", "source"],
    )
