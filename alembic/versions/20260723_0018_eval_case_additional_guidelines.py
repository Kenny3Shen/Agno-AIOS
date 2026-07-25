"""Persist Agno evaluator guidance as a structured Eval Case field.

Revision ID: 20260723_0018
Revises: 20260722_0017
Create Date: 2026-07-23 08:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from api.config import get_settings

revision: str = "20260723_0018"
down_revision: str | Sequence[str] | None = "20260722_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_eval_cases",
        sa.Column(
            "additional_guidelines",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        schema=get_settings().agno_app_schema,
    )


def downgrade() -> None:
    op.drop_column(
        "agent_eval_cases",
        "additional_guidelines",
        schema=get_settings().agno_app_schema,
    )
