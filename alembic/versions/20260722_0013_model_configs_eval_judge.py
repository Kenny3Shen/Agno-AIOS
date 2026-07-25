"""Mark one model_configs row as Agent Eval judge model.

Revision ID: 20260722_0013
Revises: 20260721_0012
Create Date: 2026-07-22 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260722_0013"
down_revision: str | Sequence[str] | None = "20260721_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    schema = get_settings().agno_app_schema
    op.add_column(
        "model_configs",
        sa.Column(
            "eval_judge",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
        schema=schema,
    )
    op.create_index(
        "idx_model_configs_eval_judge",
        "model_configs",
        ["eval_judge"],
        schema=schema,
    )


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    op.drop_index(
        "idx_model_configs_eval_judge",
        table_name="model_configs",
        schema=schema,
    )
    op.drop_column("model_configs", "eval_judge", schema=schema)
