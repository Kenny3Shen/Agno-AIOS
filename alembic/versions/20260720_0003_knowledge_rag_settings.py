"""Add knowledge RAG / PgVector runtime settings table.

Revision ID: 20260720_0003
Revises: 20260720_0002
Create Date: 2026-07-20 22:50:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings

revision: str = "20260720_0003"
down_revision: str | Sequence[str] | None = "20260720_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    settings = get_settings()
    schema = settings.agno_app_schema
    op.create_table(
        "knowledge_rag_settings",
        sa.Column("id", sa.String(length=32), primary_key=True),
        sa.Column("search_type", sa.String(length=32), nullable=False, server_default="hybrid"),
        sa.Column("top_k", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("vector_score_weight", sa.Float(), nullable=False, server_default="0.55"),
        sa.Column("similarity_threshold", sa.Float(), nullable=True),
        sa.Column("content_language", sa.String(length=64), nullable=False, server_default="english"),
        sa.Column("prefix_match", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("rerank_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("rerank_candidate_multiplier", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("rerank_min_candidates", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("updated_at", sa.BigInteger(), nullable=False),
        schema=schema,
    )


def downgrade() -> None:
    settings = get_settings()
    op.drop_table("knowledge_rag_settings", schema=settings.agno_app_schema)
