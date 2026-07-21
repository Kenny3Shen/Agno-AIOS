"""Chat settings: memory tool-content capture + prune knobs (P0).

Revision ID: 20260721_0008
Revises: 20260721_0007
Create Date: 2026-07-21 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260721_0008"
down_revision: str | Sequence[str] | None = "20260721_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema = get_settings().agno_app_schema
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_tool_content_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_prune_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_prune_retention_days",
            sa.Integer(),
            nullable=False,
            server_default="90",
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_prune_top_k",
            sa.Integer(),
            nullable=False,
            server_default="50",
        ),
        schema=schema,
    )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    for col in (
        "memory_prune_top_k",
        "memory_prune_retention_days",
        "memory_prune_enabled",
        "memory_tool_content_enabled",
    ):
        op.drop_column("chat_settings", col, schema=schema)
