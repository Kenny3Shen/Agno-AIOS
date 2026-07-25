"""Add Agno-compatible per-Case timeout overrides for eval suites.

Revision ID: 20260722_0017
Revises: 20260722_0016
Create Date: 2026-07-22 23:55:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260722_0017"
down_revision: str | Sequence[str] | None = "20260722_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_eval_cases",
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        schema=get_settings().agno_app_schema,
    )


def downgrade() -> None:
    op.drop_column(
        "agent_eval_cases",
        "timeout_seconds",
        schema=get_settings().agno_app_schema,
    )
