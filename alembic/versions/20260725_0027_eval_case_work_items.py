"""Add immutable pre-created CaseRun work-item identities.

Revision ID: 20260725_0027
Revises: 20260725_0026
Create Date: 2026-07-25 17:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260725_0027"
down_revision: str | Sequence[str] | None = "20260725_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Mark new Suite CaseRuns as ordered work items with DB uniqueness."""
    schema = get_settings().agno_app_schema
    op.add_column(
        "agent_eval_case_runs",
        sa.Column("work_item_index", sa.Integer(), nullable=True),
        schema=schema,
    )
    # Existing direct/historical CaseRuns retain NULL and therefore do not
    # participate. New queue producers set a contiguous index in the same
    # transaction as SuiteRun and durable-job creation.
    op.create_index(
        "uq_agent_eval_case_runs_work_item_order",
        "agent_eval_case_runs",
        ["suite_run_id", "work_item_index"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("work_item_index IS NOT NULL"),
    )
    op.create_index(
        "uq_agent_eval_case_runs_work_item_case",
        "agent_eval_case_runs",
        ["suite_run_id", "case_id"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("work_item_index IS NOT NULL"),
    )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    op.drop_index(
        "uq_agent_eval_case_runs_work_item_case",
        table_name="agent_eval_case_runs",
        schema=schema,
    )
    op.drop_index(
        "uq_agent_eval_case_runs_work_item_order",
        table_name="agent_eval_case_runs",
        schema=schema,
    )
    op.drop_column("agent_eval_case_runs", "work_item_index", schema=schema)
