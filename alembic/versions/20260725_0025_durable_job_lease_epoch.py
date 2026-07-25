"""Add a persistent fencing token to durable-job leases.

Revision ID: 20260725_0025
Revises: 20260725_0024
Create Date: 2026-07-25 15:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260725_0025"
down_revision: str | Sequence[str] | None = "20260725_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Track a monotonically increasing ownership epoch for every claim."""
    schema = get_settings().agno_app_schema
    op.add_column(
        "durable_jobs",
        sa.Column("lease_epoch", sa.Integer(), nullable=False, server_default=sa.text("0")),
        schema=schema,
    )
    op.create_check_constraint(
        "ck_durable_jobs_lease_epoch",
        "durable_jobs",
        "lease_epoch >= 0",
        schema=schema,
    )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    op.drop_constraint("ck_durable_jobs_lease_epoch", "durable_jobs", schema=schema)
    op.drop_column("durable_jobs", "lease_epoch", schema=schema)
