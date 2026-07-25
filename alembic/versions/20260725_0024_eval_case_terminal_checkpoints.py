"""Persist write-once private Eval CaseRun terminal checkpoints.

Revision ID: 20260725_0024
Revises: 20260725_0023
Create Date: 2026-07-25 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from api.config import get_settings

revision: str = "20260725_0024"
down_revision: str | Sequence[str] | None = "20260725_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add private CaseResult-lite evidence for durable crash recovery."""
    op.add_column(
        "agent_eval_case_runs",
        sa.Column(
            "terminal_checkpoint",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=get_settings().agno_app_schema,
    )


def downgrade() -> None:
    op.drop_column(
        "agent_eval_case_runs",
        "terminal_checkpoint",
        schema=get_settings().agno_app_schema,
    )
