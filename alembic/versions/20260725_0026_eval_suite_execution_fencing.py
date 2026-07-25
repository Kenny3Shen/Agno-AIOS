"""Fence durable Eval Suite and CaseRun writes by durable-job lease epoch.

Revision ID: 20260725_0026
Revises: 20260725_0025
Create Date: 2026-07-25 16:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260725_0026"
down_revision: str | Sequence[str] | None = "20260725_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add private execution fences and one logical fenced CaseRun per Case."""
    schema = get_settings().agno_app_schema
    op.add_column(
        "agent_eval_suite_runs",
        sa.Column("active_job_id", sa.Text(), nullable=False, server_default=""),
        schema=schema,
    )
    op.add_column(
        "agent_eval_suite_runs",
        sa.Column(
            "active_lease_epoch",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema=schema,
    )
    op.add_column(
        "agent_eval_case_runs",
        sa.Column("lease_job_id", sa.Text(), nullable=False, server_default=""),
        schema=schema,
    )
    op.add_column(
        "agent_eval_case_runs",
        sa.Column(
            "lease_epoch",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        schema=schema,
    )
    # Only newly fenced Suite executions receive a positive epoch. Keeping
    # historical rows outside the predicate lets existing installations
    # migrate even if an older lease overlap already produced duplicate rows.
    op.create_index(
        "uq_agent_eval_case_runs_fenced_suite_case",
        "agent_eval_case_runs",
        ["suite_run_id", "case_id"],
        unique=True,
        schema=schema,
        postgresql_where=sa.text("suite_run_id <> '' AND lease_epoch > 0"),
    )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    op.drop_index(
        "uq_agent_eval_case_runs_fenced_suite_case",
        table_name="agent_eval_case_runs",
        schema=schema,
    )
    op.drop_column("agent_eval_case_runs", "lease_epoch", schema=schema)
    op.drop_column("agent_eval_case_runs", "lease_job_id", schema=schema)
    op.drop_column("agent_eval_suite_runs", "active_lease_epoch", schema=schema)
    op.drop_column("agent_eval_suite_runs", "active_job_id", schema=schema)
