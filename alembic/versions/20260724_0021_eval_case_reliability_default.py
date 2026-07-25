"""Align the persisted ReliabilityEval default with Agno Case.

Revision ID: 20260724_0021
Revises: 20260724_0020
Create Date: 2026-07-24 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260724_0021"
down_revision: str | Sequence[str] | None = "20260724_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Default newly persisted Cases to Agno's permissive tool-call mode.

    Existing Cases retain their explicit historical value. Imported safety
    artifacts already persist ``false`` whenever they require a strict tool
    boundary, so this alters only the database default for future writes.
    """
    op.alter_column(
        "agent_eval_cases",
        "allow_additional_tool_calls",
        existing_type=sa.Boolean(),
        server_default=sa.text("true"),
        schema=get_settings().agno_app_schema,
    )


def downgrade() -> None:
    op.alter_column(
        "agent_eval_cases",
        "allow_additional_tool_calls",
        existing_type=sa.Boolean(),
        server_default=sa.text("false"),
        schema=get_settings().agno_app_schema,
    )
