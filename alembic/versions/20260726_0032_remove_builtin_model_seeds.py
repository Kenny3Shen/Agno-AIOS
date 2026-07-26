"""Remove local-test model seeds from product configuration.

Revision ID: 20260726_0032
Revises: 20260726_0031
Create Date: 2026-07-26 11:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260726_0032"
down_revision: str | Sequence[str] | None = "20260726_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# These rows were formerly injected by the application only for local testing.
# A row with a real key was explicitly configured by an administrator, so it is
# retained as an ordinary editable connection rather than discarded on upgrade.
_LOCAL_TEST_MODEL_IDS = (
    "deepseek-v4-flash",
    "deepseek-v4-pro",
    "xai-grok-4.5",
)


def _delete_unconfigured_local_models_statement(
    table: sa.Table | sa.TableClause,
) -> sa.Delete:
    """Delete only the old blank test entries, never configured connections."""
    api_key = sa.func.trim(sa.func.coalesce(table.c.api_key, ""))
    return sa.delete(table).where(
        table.c.id.in_(_LOCAL_TEST_MODEL_IDS),
        api_key == "",
    )


def upgrade() -> None:
    """Remove empty test seeds and the obsolete built-in marker."""
    schema = get_settings().agno_app_schema
    models = sa.table(
        "model_configs",
        sa.column("id", sa.String()),
        sa.column("api_key", sa.Text()),
        schema=schema,
    )
    op.execute(_delete_unconfigured_local_models_statement(models))
    op.drop_column("model_configs", "builtin", schema=schema)


def downgrade() -> None:
    """Restore only the column; removed local test rows are intentionally gone."""
    schema = get_settings().agno_app_schema
    op.add_column(
        "model_configs",
        sa.Column(
            "builtin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        schema=schema,
    )
