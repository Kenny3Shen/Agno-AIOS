"""Make the Agno Case judge mode an explicit evaluation contract field.

Revision ID: 20260724_0020
Revises: 20260723_0019
Create Date: 2026-07-24 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260724_0020"
down_revision: str | Sequence[str] | None = "20260723_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Install the Agno-compatible binary default with a database invariant."""
    schema = get_settings().agno_app_schema
    op.add_column(
        "agent_eval_cases",
        sa.Column(
            "judge_mode",
            sa.Text(),
            nullable=False,
            server_default="binary",
        ),
        schema=schema,
    )
    op.create_check_constraint(
        "ck_agent_eval_cases_judge_mode",
        "agent_eval_cases",
        "judge_mode IN ('binary', 'numeric')",
        schema=schema,
    )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    op.drop_constraint(
        "ck_agent_eval_cases_judge_mode",
        "agent_eval_cases",
        schema=schema,
    )
    op.drop_column("agent_eval_cases", "judge_mode", schema=schema)
