"""Remove retired 0xMarcio/cve source records.

Revision ID: 20260722_0016
Revises: 20260722_0015
Create Date: 2026-07-22 23:15:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260722_0016"
down_revision: str | Sequence[str] | None = "20260722_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RETIRED_SOURCE = "marcio-cve"


def upgrade() -> None:
    schema = get_settings().agno_app_schema
    cves = sa.table("cves", sa.column("source", sa.String()), schema=schema)
    source_settings = sa.table(
        "cve_source_settings",
        sa.column("source", sa.String()),
        schema=schema,
    )
    op.execute(sa.delete(cves).where(cves.c.source == _RETIRED_SOURCE))
    op.execute(sa.delete(source_settings).where(source_settings.c.source == _RETIRED_SOURCE))


def downgrade() -> None:
    # The retired source data cannot be reconstructed after deletion.
    pass
