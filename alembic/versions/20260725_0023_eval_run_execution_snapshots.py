"""Persist private immutable Eval execution snapshots.

Revision ID: 20260725_0023
Revises: 20260724_0022
Create Date: 2026-07-25 13:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from api.config import get_settings

revision: str = "20260725_0023"
down_revision: str | Sequence[str] | None = "20260724_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add private frozen inputs without projecting them through public APIs."""
    schema = get_settings().agno_app_schema
    op.add_column(
        "agent_eval_suite_runs",
        sa.Column(
            "execution_snapshot",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=schema,
    )
    op.add_column(
        "agent_eval_case_runs",
        sa.Column(
            "definition_snapshot",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=schema,
    )
    op.add_column(
        "agent_eval_case_runs",
        sa.Column(
            "execution_provenance",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema=schema,
    )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    op.drop_column("agent_eval_case_runs", "execution_provenance", schema=schema)
    op.drop_column("agent_eval_case_runs", "definition_snapshot", schema=schema)
    op.drop_column("agent_eval_suite_runs", "execution_snapshot", schema=schema)
