"""Replace free-form Eval Case targets with one strict Suite target.

Revision ID: 20260723_0019
Revises: 20260723_0018
Create Date: 2026-07-23 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from api.config import get_settings
from api.services.agent_catalog import AGENT_PROFILES
from api.services.team_runtime import TEAM_PROFILES

revision: str = "20260723_0019"
down_revision: str | Sequence[str] | None = "20260723_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _target_ids() -> tuple[tuple[str, ...], tuple[str, ...]]:
    agents = tuple(
        target_id
        for target_id, profile in AGENT_PROFILES.items()
        if bool(profile.get("chat_selectable", False))
    )
    teams = tuple(
        target_id
        for target_id, profile in TEAM_PROFILES.items()
        if bool(profile.get("chat_selectable", False))
    )
    return agents, teams


def upgrade() -> None:
    """Fail closed when legacy rows express divergent or unknown semantics."""
    schema = get_settings().agno_app_schema
    suites = sa.table(
        "agent_eval_suites",
        sa.column("id", sa.Text()),
        sa.column("target_agent_id", sa.Text()),
        sa.column("target_kind", sa.Text()),
        sa.column("target_id", sa.Text()),
        schema=schema,
    )
    cases = sa.table(
        "agent_eval_cases",
        sa.column("id", sa.Text()),
        sa.column("suite_id", sa.Text()),
        sa.column("target_agent_id", sa.Text()),
        schema=schema,
    )
    agents, teams = _target_ids()
    known_target_ids = (*agents, *teams)
    bind = op.get_bind()

    invalid_suites = bind.execute(
        sa.select(suites.c.id, suites.c.target_agent_id).where(
            sa.or_(
                suites.c.target_agent_id.is_(None),
                ~suites.c.target_agent_id.in_(known_target_ids),
            )
        )
    ).all()
    if invalid_suites:
        ids = ", ".join(str(row.id) for row in invalid_suites[:10])
        raise RuntimeError(
            "Cannot migrate Eval Suite target(s) with unknown target_agent_id; "
            f"fix or remove Suite IDs: {ids}"
        )

    divergent_cases = bind.execute(
        sa.select(cases.c.id, cases.c.suite_id)
        .select_from(cases.outerjoin(suites, cases.c.suite_id == suites.c.id))
        .where(
            sa.or_(
                suites.c.id.is_(None),
                cases.c.target_agent_id != suites.c.target_agent_id,
            )
        )
    ).all()
    if divergent_cases:
        ids = ", ".join(str(row.id) for row in divergent_cases[:10])
        raise RuntimeError(
            "Cannot migrate divergent Eval Case target(s); each Case must match "
            f"its Suite target before the strict model is installed. Case IDs: {ids}"
        )

    op.add_column(
        "agent_eval_suites",
        sa.Column("target_kind", sa.Text(), nullable=True),
        schema=schema,
    )
    op.add_column(
        "agent_eval_suites",
        sa.Column("target_id", sa.Text(), nullable=True),
        schema=schema,
    )
    op.execute(
        suites.update().values(
            target_id=suites.c.target_agent_id,
            target_kind=sa.case(
                (suites.c.target_agent_id.in_(teams), "team"),
                else_="agent",
            ),
        )
    )
    op.alter_column(
        "agent_eval_suites",
        "target_kind",
        nullable=False,
        schema=schema,
    )
    op.alter_column(
        "agent_eval_suites",
        "target_id",
        nullable=False,
        schema=schema,
    )
    op.create_check_constraint(
        "ck_agent_eval_suites_target_kind",
        "agent_eval_suites",
        "target_kind IN ('agent', 'team')",
        schema=schema,
    )
    op.drop_column("agent_eval_suites", "target_agent_id", schema=schema)
    op.drop_column("agent_eval_cases", "target_agent_id", schema=schema)


def downgrade() -> None:
    schema = get_settings().agno_app_schema
    op.add_column(
        "agent_eval_suites",
        sa.Column("target_agent_id", sa.Text(), nullable=True),
        schema=schema,
    )
    suites = sa.table(
        "agent_eval_suites",
        sa.column("target_agent_id", sa.Text()),
        sa.column("target_id", sa.Text()),
        schema=schema,
    )
    op.execute(suites.update().values(target_agent_id=suites.c.target_id))
    op.alter_column(
        "agent_eval_suites",
        "target_agent_id",
        nullable=False,
        server_default="security-operations",
        schema=schema,
    )
    op.add_column(
        "agent_eval_cases",
        sa.Column(
            "target_agent_id",
            sa.Text(),
            nullable=False,
            server_default="security-operations",
        ),
        schema=schema,
    )
    op.drop_constraint(
        "ck_agent_eval_suites_target_kind",
        "agent_eval_suites",
        schema=schema,
    )
    op.drop_column("agent_eval_suites", "target_id", schema=schema)
    op.drop_column("agent_eval_suites", "target_kind", schema=schema)
