"""Terminalize legacy active Eval SuiteRuns that cannot use the durable worker.

Revision ID: 20260725_0028
Revises: 20260725_0027
Create Date: 2026-07-25 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from api.config import get_settings

revision: str = "20260725_0028"
down_revision: str | Sequence[str] | None = "20260725_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_LEGACY_ACTIVE_RUN_ERROR = (
    "Eval SuiteRun was marked error during upgrade because it has no durable "
    "execution snapshot and cannot be resumed by the current worker."
)


def upgrade() -> None:
    """Stop pre-durable active runs from permanently blocking their Suite.

    Prior to the durable SuiteRun contract, a synchronous HTTP execution could
    leave a ``queued``/``running`` row without a job, immutable snapshot, or
    CaseRun work items when its process exited.  The new worker must not try to
    reconstruct those mutable executions.  Terminalizing only rows with an
    empty legacy snapshot leaves every v2 durable run untouched.
    """
    suite_runs = sa.table(
        "agent_eval_suite_runs",
        sa.column("status", sa.Text()),
        sa.column("execution_snapshot", JSONB()),
        sa.column("error_summary", sa.Text()),
        sa.column("completed_at", sa.DateTime(timezone=True)),
        schema=get_settings().agno_app_schema,
    )
    op.execute(
        suite_runs.update()
        .where(
            sa.and_(
                suite_runs.c.status.in_(("queued", "running", "cancelling")),
                sa.or_(
                    suite_runs.c.execution_snapshot.is_(None),
                    suite_runs.c.execution_snapshot == sa.text("'{}'::jsonb"),
                ),
            )
        )
        .values(
            status="error",
            error_summary=_LEGACY_ACTIVE_RUN_ERROR,
            completed_at=sa.func.now(),
        )
    )


def downgrade() -> None:
    """The legacy lifecycle state is intentionally not recoverable."""
    pass
