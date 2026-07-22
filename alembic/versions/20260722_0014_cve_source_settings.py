"""Add persisted CVE source enablement toggles.

Revision ID: 20260722_0014
Revises: 20260722_0013
Create Date: 2026-07-22 22:15:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260722_0014"
down_revision: str | Sequence[str] | None = "20260722_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cve_source_settings",
        sa.Column("source", sa.String(length=128), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        schema=get_settings().agno_app_schema,
    )


def downgrade() -> None:
    op.drop_table("cve_source_settings", schema=get_settings().agno_app_schema)
