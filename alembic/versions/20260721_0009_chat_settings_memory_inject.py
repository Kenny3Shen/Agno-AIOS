"""Chat settings: memory inject-side scoring knobs (P1).

Revision ID: 20260721_0009
Revises: 20260721_0008
Create Date: 2026-07-21 22:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260721_0009"
down_revision: str | Sequence[str] | None = "20260721_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema = get_settings().agno_app_schema
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_inject_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_inject_top_k",
            sa.Integer(),
            nullable=False,
            server_default="12",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_inject_max_chars",
            sa.Integer(),
            nullable=False,
            server_default="2000",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_inject_window_days",
            sa.Integer(),
            nullable=False,
            server_default="90",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_inject_dedupe_topics",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        schema=schema,
    )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    for col in (
        "memory_inject_dedupe_topics",
        "memory_inject_window_days",
        "memory_inject_max_chars",
        "memory_inject_top_k",
        "memory_inject_enabled",
    ):
        op.drop_column("chat_settings", col, schema=schema)
