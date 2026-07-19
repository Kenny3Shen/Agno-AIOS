"""Canonicalize legacy xAI/Grok model configuration rows.

Older releases represented xAI models as OpenAI-compatible configurations and
used the Responses API.  The application now uses Agno's native xAI Chat
Completions model, so this one-time data migration makes persisted rows match
that contract.  Keeping it in Alembic ensures every deployed database receives
the transformation before API/worker processes begin serving traffic.

Revision ID: 20260720_0002
Revises: 20260720_0001
Create Date: 2026-07-20 00:10:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260720_0002"
down_revision: str | Sequence[str] | None = "20260720_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _xai_model_config_canonicalization_statement(table: sa.Table) -> sa.Update:
    """Build the idempotent update for legacy xAI model configuration rows."""
    provider = sa.func.lower(sa.func.coalesce(table.c.provider, ""))
    model_id = sa.func.lower(sa.func.coalesce(table.c.model_id, ""))
    base_url = sa.func.lower(sa.func.coalesce(table.c.base_url, ""))
    legacy_xai = sa.and_(
        provider.in_(("", "openai-compatible")),
        sa.or_(model_id.like("grok%"), base_url.like("%api.x.ai%")),
    )
    stale_xai = sa.and_(
        provider == "xai",
        sa.or_(
            sa.func.coalesce(table.c.api_protocol, "") != "chat-completions",
            table.c.default_reasoning_effort.is_not(None),
        ),
    )
    return (
        sa.update(table)
        .where(sa.or_(legacy_xai, stale_xai))
        .values(
            provider="xai",
            api_protocol="chat-completions",
            default_reasoning_effort=None,
        )
    )


def _model_configs_table(schema: str) -> sa.Table:
    """Describe only the columns used by this data migration."""
    return sa.Table(
        "model_configs",
        sa.MetaData(),
        sa.Column("provider", sa.String()),
        sa.Column("model_id", sa.Text()),
        sa.Column("api_protocol", sa.String()),
        sa.Column("default_reasoning_effort", sa.String()),
        sa.Column("base_url", sa.Text()),
        schema=schema,
    )


def upgrade() -> None:
    """Rewrite pre-native-xAI configuration rows once the baseline is present."""
    table = _model_configs_table(get_settings().agno_app_schema)
    op.execute(_xai_model_config_canonicalization_statement(table))


def downgrade() -> None:
    """The canonical representation is intentionally not reversible."""
