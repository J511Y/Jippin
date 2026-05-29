"""request logs table

revision: 0004_request_logs / down: 0003_drop_deployment_probe_temp

CMP-545 stores API request/response log rows. Only lookup indexes with an
immediate operational path are created to keep per-request inserts cheap.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_request_logs"
down_revision: Union[str, Sequence[str], None] = "0003_drop_deployment_probe_temp"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "request_logs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_anonymous_user", sa.Boolean(), nullable=False),
        sa.Column("user_id", sa.Text(), nullable=True),
        sa.Column("device_id", sa.Text(), nullable=True),
        sa.Column("version", sa.Text(), nullable=True),
        sa.Column("device", sa.Text(), nullable=True),
        sa.Column("country", sa.Text(), nullable=True),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column(
            "ip_addrs",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("last_ip", postgresql.INET(), nullable=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column(
            "parameter",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("method", sa.Text(), nullable=False),
        sa.Column("body", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("response_code", sa.Integer(), nullable=False),
        sa.Column("response_message", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("referrer", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_request_logs")),
    )
    op.create_index(op.f("ix_request_logs_created_at"), "request_logs", ["created_at"])
    op.create_index(op.f("ix_request_logs_request_id"), "request_logs", ["request_id"])
    op.create_index(
        op.f("ix_request_logs_response_code"), "request_logs", ["response_code"]
    )
    op.create_index(
        op.f("ix_request_logs_user_id_created_at"),
        "request_logs",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_table("request_logs")
