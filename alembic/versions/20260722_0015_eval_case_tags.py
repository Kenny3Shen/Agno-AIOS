"""Persist Eval Case tags for Agno-style Suite selectors.

Revision ID: 20260722_0015
Revises: 20260722_0014
Create Date: 2026-07-22 22:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from api.config import get_settings

revision: str = "20260722_0015"
down_revision: str | Sequence[str] | None = "20260722_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema = get_settings().agno_app_schema
    op.add_column(
        "agent_eval_cases",
        sa.Column(
            "tags",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema=schema,
    )
    op.create_index(
        "idx_agent_eval_cases_tags",
        "agent_eval_cases",
        ["tags"],
        schema=schema,
        postgresql_using="gin",
    )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    op.drop_index(
        "idx_agent_eval_cases_tags",
        table_name="agent_eval_cases",
        schema=schema,
    )
    op.drop_column("agent_eval_cases", "tags", schema=schema)
