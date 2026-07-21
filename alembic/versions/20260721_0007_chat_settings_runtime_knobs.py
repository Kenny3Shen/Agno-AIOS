"""Extend chat_settings with Agno runtime knobs (history, summaries, tools).

Revision ID: 20260721_0007
Revises: 20260721_0006
Create Date: 2026-07-21 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260721_0007"
down_revision: str | Sequence[str] | None = "20260721_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema = get_settings().agno_app_schema
    # Boolean knobs
    op.add_column(
        "chat_settings",
        sa.Column(
            "session_summaries_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "add_datetime_to_context",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "enable_agentic_memory",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "markdown",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        schema=schema,
    )
    # Integer knobs (NULL = use profile / unlimited)
    op.add_column(
        "chat_settings",
        sa.Column(
            "num_history_runs",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column("max_tool_calls_from_history", sa.Integer(), nullable=True),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column("default_tool_call_limit", sa.Integer(), nullable=True),
        schema=schema,
    )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    for col in (
        "default_tool_call_limit",
        "max_tool_calls_from_history",
        "num_history_runs",
        "markdown",
        "enable_agentic_memory",
        "add_datetime_to_context",
        "session_summaries_enabled",
    ):
        op.drop_column("chat_settings", col, schema=schema)
