"""Drop legacy Chat settings memory booleans.

Revision ID: 20260726_0031
Revises: 20260726_0030
Create Date: 2026-07-26 10:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260726_0031"
down_revision: str | Sequence[str] | None = "20260726_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Remove flags superseded by the canonical ``memory_mode`` column."""
    schema = get_settings().agno_app_schema
    op.drop_column("chat_settings", "enable_agentic_memory", schema=schema)
    op.drop_column("chat_settings", "memory_enabled", schema=schema)


def downgrade() -> None:
    """Restore legacy flags for an application rollback from ``memory_mode``."""
    schema = get_settings().agno_app_schema
    op.add_column(
        "chat_settings",
        sa.Column(
            "memory_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        schema=schema,
    )
    op.add_column(
        "chat_settings",
        sa.Column(
            "enable_agentic_memory",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema=schema,
    )
    table = sa.table(
        "chat_settings",
        sa.column("memory_mode", sa.String()),
        sa.column("memory_enabled", sa.Boolean()),
        sa.column("enable_agentic_memory", sa.Boolean()),
        schema=schema,
    )
    op.execute(
        table.update().values(
            memory_enabled=sa.case(
                (table.c.memory_mode == "off", False),
                else_=True,
            ),
            enable_agentic_memory=sa.case(
                (table.c.memory_mode == "agentic", True),
                else_=False,
            ),
        )
    )
