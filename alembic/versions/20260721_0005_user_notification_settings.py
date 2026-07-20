"""Per-user notification settings (Feishu webhook).

Revision ID: 20260721_0005
Revises: 20260721_0004
Create Date: 2026-07-21 03:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260721_0005"
down_revision: str | Sequence[str] | None = "20260721_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    settings = get_settings()
    schema = settings.agno_app_schema
    op.create_table(
        "user_notification_settings",
        sa.Column("user_id", sa.String(length=255), primary_key=True),
        sa.Column("feishu_webhook_url", sa.String(length=2048), nullable=False, server_default=""),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        schema=schema,
    )


def downgrade() -> None:
    settings = get_settings()
    op.drop_table("user_notification_settings", schema=settings.agno_app_schema)
