"""Drop obsolete mcp_servers.default_enabled column.

User enablement is owned by per-user capability preferences only.
Platform availability remains the ``enabled`` column.

Revision ID: 20260720_0004
Revises: 20260720_0003
Create Date: 2026-07-20 19:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260720_0004"
down_revision: str | Sequence[str] | None = "20260720_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _qualified(schema: str, table: str) -> str:
    return f"{_identifier(schema)}.{_identifier(table)}"


def upgrade() -> None:
    settings = get_settings()
    servers = _qualified(settings.agno_mcp_schema, "mcp_servers")
    preferences = _qualified(settings.agno_app_schema, "user_capability_preferences")
    op.execute(sa.text(f"ALTER TABLE IF EXISTS {servers} DROP COLUMN IF EXISTS default_enabled"))
    # Sparse preferences: missing row means enabled. Drop redundant enabled rows.
    op.execute(
        sa.text(
            f"DELETE FROM {preferences} WHERE state = 'enabled'"
        )
    )


def downgrade() -> None:
    settings = get_settings()
    servers = _qualified(settings.agno_mcp_schema, "mcp_servers")
    op.execute(
        sa.text(
            f"ALTER TABLE IF EXISTS {servers} "
            "ADD COLUMN IF NOT EXISTS default_enabled BOOLEAN NOT NULL DEFAULT true"
        )
    )
