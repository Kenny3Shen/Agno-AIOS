"""Chat settings: unified memory_mode (off / automatic / agentic).

Revision ID: 20260721_0010
Revises: 20260721_0009
Create Date: 2026-07-21 23:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260721_0010"
down_revision: str | Sequence[str] | None = "20260721_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema = get_settings().agno_app_schema
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_mode",
            sa.String(16),
            nullable=False,
            server_default="automatic",
        ),
        schema=schema,
    )
    # Backfill from legacy dual booleans when the global row already exists.
    table = sa.table(
        "chat_settings",
        sa.column("id", sa.String),
        sa.column("memory_enabled", sa.Boolean),
        sa.column("enable_agentic_memory", sa.Boolean),
        sa.column("memory_mode", sa.String),
        schema=schema,
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.select(
            table.c.id,
            table.c.memory_enabled,
            table.c.enable_agentic_memory,
        )
    ).fetchall()
    for row in rows:
        enabled = bool(row[1])
        agentic = bool(row[2])
        if not enabled:
            mode = "off"
        elif agentic:
            mode = "agentic"
        else:
            mode = "automatic"
        conn.execute(
            sa.update(table).where(table.c.id == row[0]).values(memory_mode=mode)
        )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    op.drop_column("chat_settings", "memory_mode", schema=schema)
