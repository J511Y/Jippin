"""drop deployment probe temp table

revision: 0003_drop_deployment_probe_temp / down: 0002_deployment_probe_temp

Cleanup migration for CMP-539 deployment propagation verification.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003_drop_deployment_probe_temp"
down_revision: Union[str, Sequence[str], None] = "0002_deployment_probe_temp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("deployment_probe_temp")


def downgrade() -> None:
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
