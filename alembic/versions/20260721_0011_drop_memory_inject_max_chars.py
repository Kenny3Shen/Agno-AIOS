"""Drop unused memory_inject_max_chars (no inject character budget).

Revision ID: 20260721_0011
Revises: 20260721_0010
Create Date: 2026-07-21 23:50:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260721_0011"
down_revision: str | Sequence[str] | None = "20260721_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema = get_settings().agno_app_schema
    op.drop_column("chat_settings", "memory_inject_max_chars", schema=schema)


def downgrade() -> None:
    schema = get_settings().agno_app_schema
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
