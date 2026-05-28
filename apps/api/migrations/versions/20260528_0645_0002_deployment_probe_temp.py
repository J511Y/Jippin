"""deployment probe temp table

revision: 0002_deployment_probe_temp / down: 0001_baseline

Temporary migration used to verify CMP-539 deployment propagation:
PR preview -> development -> production.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_deployment_probe_temp"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "deployment_probe_temp",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "marker",
            sa.String(length=64),
            server_default=sa.text("'cmp-539'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("deployment_probe_temp")
