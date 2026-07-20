"""Add per-user workflow custom nodes table.

Revision ID: 20260720_0005
Revises: 20260720_0004
Create Date: 2026-07-20 20:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260720_0005"
down_revision: str | Sequence[str] | None = "20260720_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _qualified(schema: str, table: str) -> str:
    return f"{_identifier(schema)}.{_identifier(table)}"


def upgrade() -> None:
    settings = get_settings()
    table = _qualified(settings.agno_app_schema, "workflow_custom_nodes")
    op.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (
                id VARCHAR(64) PRIMARY KEY,
                user_id VARCHAR(255) NOT NULL,
                name VARCHAR(255) NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                color VARCHAR(32) NOT NULL DEFAULT '#1677ff',
                definition JSONB NOT NULL DEFAULT '{{}}'::jsonb,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
            """
        )
    )
    op.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_workflow_custom_nodes_user "
            f"ON {table} (user_id, updated_at DESC)"
        )
    )


def downgrade() -> None:
    settings = get_settings()
    table = _qualified(settings.agno_app_schema, "workflow_custom_nodes")
    op.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
