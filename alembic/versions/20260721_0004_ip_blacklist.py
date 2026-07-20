"""Add IP blacklist threat-intel table.

Revision ID: 20260721_0004
Revises: 20260720_0003
Create Date: 2026-07-21 02:30:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260721_0004"
down_revision: str | Sequence[str] | None = "20260720_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    settings = get_settings()
    schema = settings.agno_app_schema
    op.create_table(
        "ip_blacklist",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("indicator", sa.Text(), nullable=False),
        sa.Column("indicator_type", sa.Text(), nullable=False, server_default="cidr"),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("list_name", sa.Text(), nullable=False, server_default=""),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        schema=schema,
    )
    op.create_index(
        "idx_ip_blacklist_indicator",
        "ip_blacklist",
        ["indicator"],
        schema=schema,
    )
    op.create_index(
        "idx_ip_blacklist_source",
        "ip_blacklist",
        ["source"],
        schema=schema,
    )
    op.create_index(
        "uq_ip_blacklist_indicator_source",
        "ip_blacklist",
        ["indicator", "source"],
        unique=True,
        schema=schema,
    )


def downgrade() -> None:
    settings = get_settings()
    schema = settings.agno_app_schema
    op.drop_index(
        "uq_ip_blacklist_indicator_source",
        table_name="ip_blacklist",
        schema=schema,
    )
    op.drop_index(
        "idx_ip_blacklist_source",
        table_name="ip_blacklist",
        schema=schema,
    )
    op.drop_index(
        "idx_ip_blacklist_indicator",
        table_name="ip_blacklist",
        schema=schema,
    )
    op.drop_table("ip_blacklist", schema=schema)
