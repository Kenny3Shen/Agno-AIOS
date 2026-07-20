"""Add user-level capability preferences and owned MCP tokens.

Revision ID: 20260720_0003
Revises: 20260720_0002
Create Date: 2026-07-20 00:30:00
"""

from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260720_0003"
down_revision: str | Sequence[str] | None = "20260720_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _qualified(schema: str, table: str) -> str:
    return f"{_identifier(schema)}.{_identifier(table)}"


def upgrade() -> None:
    bind = op.get_bind()
    settings = get_settings()
    preferences = _qualified(settings.agno_app_schema, "user_capability_preferences")
    servers = _qualified(settings.agno_mcp_schema, "mcp_servers")
    tokens = _qualified(settings.agno_mcp_schema, "mcp_tokens")

    # ``0001`` creates current metadata on fresh deployments, so every DDL
    # statement is deliberately idempotent for both fresh and upgraded DBs.
    bind.execute(
        sa.text(
            f"""
            CREATE TABLE IF NOT EXISTS {preferences} (
                user_id VARCHAR(255) NOT NULL,
                capability_type VARCHAR(32) NOT NULL,
                capability_key VARCHAR(255) NOT NULL,
                state VARCHAR(16) NOT NULL,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL,
                PRIMARY KEY (user_id, capability_type, capability_key),
                CONSTRAINT ck_user_capability_preferences_type
                    CHECK (capability_type IN ('skill', 'mcp_server')),
                CONSTRAINT ck_user_capability_preferences_state
                    CHECK (state IN ('enabled', 'disabled'))
            )
            """
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_user_capability_preferences_user "
            f"ON {preferences} (user_id, capability_type)"
        )
    )

    bind.execute(
        sa.text(
            f"ALTER TABLE IF EXISTS {servers} "
            "ADD COLUMN IF NOT EXISTS default_enabled BOOLEAN NOT NULL DEFAULT true"
        )
    )
    for clause in (
        "ADD COLUMN IF NOT EXISTS token_hash TEXT",
        "ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(255)",
        "ADD COLUMN IF NOT EXISTS token_kind VARCHAR(16) NOT NULL DEFAULT 'service'",
    ):
        bind.execute(sa.text(f"ALTER TABLE IF EXISTS {tokens} {clause}"))

    # Convert formerly plaintext values in-place.  The legacy ``token``
    # column remains for backwards-compatible schema shape but stores the
    # digest after this revision, never the bearer secret.
    rows = bind.execute(
        sa.text(f"SELECT id, token FROM {tokens} WHERE token_hash IS NULL")
    ).mappings()
    for row in rows:
        digest = sha256(str(row["token"] or "").encode("utf-8")).hexdigest()
        bind.execute(
            sa.text(
                f"UPDATE {tokens} SET token = :digest, token_hash = :digest WHERE id = :id"
            ),
            {"id": row["id"], "digest": digest},
        )
    bind.execute(
        sa.text(f"ALTER TABLE IF EXISTS {tokens} ALTER COLUMN token_hash SET NOT NULL")
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_mcp_tokens_token_hash "
            f"ON {tokens} (token_hash)"
        )
    )


def downgrade() -> None:
    settings = get_settings()
    preferences = _qualified(settings.agno_app_schema, "user_capability_preferences")
    servers = _qualified(settings.agno_mcp_schema, "mcp_servers")
    tokens = _qualified(settings.agno_mcp_schema, "mcp_tokens")
    op.execute(sa.text(f"DROP TABLE IF EXISTS {preferences}"))
    op.execute(sa.text(f"DROP INDEX IF EXISTS {_identifier(settings.agno_mcp_schema)}.uq_mcp_tokens_token_hash"))
    for column in ("token_kind", "owner_user_id", "token_hash"):
        op.execute(sa.text(f"ALTER TABLE IF EXISTS {tokens} DROP COLUMN IF EXISTS {_identifier(column)}"))
    op.execute(sa.text(f"ALTER TABLE IF EXISTS {servers} DROP COLUMN IF EXISTS default_enabled"))
