"""Create the T.A.I.S control-plane baseline.

Agno owns its own persistence and PgVector table lifecycle, so this revision
creates only tables defined by this repository.  Future changes to those tables
must be represented by a new Alembic revision; application startup must never
perform DDL.

Revision ID: 20260720_0001
Revises:
Create Date: 2026-07-20 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.schema_metadata import control_plane_metadata

revision: str = "20260720_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def upgrade() -> None:
    """Create schemas, pgvector extension, tables, constraints and indexes."""
    bind = op.get_bind()
    settings = get_settings()

    bind.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))
    for schema in (
        settings.agno_app_schema,
        settings.agno_db_schema,
        settings.agno_mcp_schema,
        settings.agno_knowledge_schema,
    ):
        bind.execute(CreateSchema(schema, if_not_exists=True))

    metadata = control_plane_metadata()
    # SQLAlchemy's PostgreSQL dialect cannot render this existing expression
    # index with ``literal_binds`` in ``alembic upgrade --sql``.  Create its
    # table through metadata but emit the three CVE indexes as explicit,
    # portable PostgreSQL DDL below.
    cves = metadata.tables[f"{settings.agno_app_schema}.cves"]
    cve_indexes = set(cves.indexes)
    cves.indexes.clear()
    try:
        metadata.create_all(bind=bind, checkfirst=True)
    finally:
        cves.indexes.update(cve_indexes)
    for table in metadata.sorted_tables:
        if table is cves:
            continue
        for index in table.indexes:
            index.create(bind=bind, checkfirst=True)

    app_schema = _identifier(settings.agno_app_schema)
    bind.execute(
        sa.text(
            f"ALTER TABLE {app_schema}.\"cves\" DROP CONSTRAINT IF EXISTS uq_cves_cve_url"
        )
    )
    bind.execute(
        sa.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_cves_cve_url_source "
            f"ON {app_schema}.\"cves\" (cve_id, github_url, source)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_cves_cve_id "
            f"ON {app_schema}.\"cves\" (cve_id)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_cves_source "
            f"ON {app_schema}.\"cves\" (source)"
        )
    )
    bind.execute(
        sa.text(
            "CREATE INDEX IF NOT EXISTS idx_cves_search "
            f"ON {app_schema}.\"cves\" USING gin "
            "(to_tsvector('simple', cve_id || ' ' || coalesce(description, '')))"
        )
    )


def downgrade() -> None:
    """Drop repository-owned tables while retaining Agno schemas and extension."""
    metadata = control_plane_metadata()
    metadata.drop_all(bind=op.get_bind(), checkfirst=True)
