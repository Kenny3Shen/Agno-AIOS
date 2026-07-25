"""Require every persisted Eval Case to declare its checks explicitly.

Revision ID: 20260724_0022
Revises: 20260724_0021
Create Date: 2026-07-24 10:15:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from api.config import get_settings

revision: str = "20260724_0022"
down_revision: str | Sequence[str] | None = "20260724_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove the misleading implicit Accuracy default for future Cases.

    Existing rows retain their stored evaluation type array. Application-level
    validation already rejects empty arrays and now requires the field on
    creation, so the database no longer guesses an evaluator for raw inserts.
    """
    op.alter_column(
        "agent_eval_cases",
        "eval_types",
        existing_type=JSONB(),
        server_default=None,
        schema=get_settings().agno_app_schema,
    )


def downgrade() -> None:
    op.alter_column(
        "agent_eval_cases",
        "eval_types",
        existing_type=JSONB(),
        server_default=sa.text("'[\"accuracy\"]'::jsonb"),
        schema=get_settings().agno_app_schema,
    )
