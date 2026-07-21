"""Global Agno input guardrail settings.

Revision ID: 20260721_0006
Revises: 20260721_0005
Create Date: 2026-07-21 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence
from time import time

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260721_0006"
down_revision: str | Sequence[str] | None = "20260721_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    settings = get_settings()
    schema = settings.agno_app_schema
    op.create_table(
        "guardrail_settings",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("pii_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("pii_mask", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "pii_check_email", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "pii_check_phone", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "prompt_injection_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        schema=schema,
    )
    # Seed global row from env defaults at migration time.
    op.bulk_insert(
        sa.table(
            "guardrail_settings",
            sa.column("id", sa.String),
            sa.column("enabled", sa.Boolean),
            sa.column("pii_enabled", sa.Boolean),
            sa.column("pii_mask", sa.Boolean),
            sa.column("pii_check_email", sa.Boolean),
            sa.column("pii_check_phone", sa.Boolean),
            sa.column("prompt_injection_enabled", sa.Boolean),
            sa.column("updated_at", sa.BigInteger),
            schema=schema,
        ),
        [
            {
                "id": "global",
                "enabled": bool(settings.guardrails_enabled),
                "pii_enabled": bool(settings.guardrails_pii_enabled),
                "pii_mask": bool(settings.guardrails_pii_mask),
                "pii_check_email": bool(settings.guardrails_pii_check_email),
                "pii_check_phone": bool(settings.guardrails_pii_check_phone),
                "prompt_injection_enabled": bool(
                    settings.guardrails_prompt_injection_enabled
                ),
                "updated_at": int(time()),
            }
        ],
    )


def downgrade() -> None:
    settings = get_settings()
    op.drop_table("guardrail_settings", schema=settings.agno_app_schema)
