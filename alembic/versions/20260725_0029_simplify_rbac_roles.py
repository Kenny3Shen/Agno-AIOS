"""Collapse retired RBAC role presets into the normal user role.

Revision ID: 20260725_0029
Revises: 20260725_0028
Create Date: 2026-07-25 19:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from api.config import get_settings

revision: str = "20260725_0029"
down_revision: str | Sequence[str] | None = "20260725_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_ROLES = ("admin", "user")
_ADMIN_ROLE_JSON = sa.text("'\"admin\"'::jsonb")
_USER_ROLE_JSON = sa.text("'\"user\"'::jsonb")
_TRUE_JSON = sa.text("'true'::jsonb")
_FALSE_JSON = sa.text("'false'::jsonb")


def _json_role(column: sa.ColumnElement[JSONB], path: str) -> sa.ColumnElement[str]:
    return column.op("#>>")(sa.text(path))


def _json_value(column: sa.ColumnElement[JSONB], path: str) -> sa.ColumnElement[JSONB]:
    return column.op("#>")(sa.text(path))


def _normalized_role(column: sa.ColumnElement[str]) -> sa.ColumnElement[str]:
    return sa.func.lower(sa.func.trim(column))


def _json_bool_is_true(
    column: sa.ColumnElement[JSONB], path: str
) -> sa.ColumnElement[bool]:
    return _json_value(column, path) == _TRUE_JSON


def _json_bool_needs_canonicalization(
    column: sa.ColumnElement[JSONB], path: str
) -> sa.ColumnElement[bool]:
    value = _json_value(column, path)
    return sa.or_(
        value.is_(None),
        sa.and_(value != _TRUE_JSON, value != _FALSE_JSON),
    )


def _actor_needs_canonicalization(
    column: sa.ColumnElement[JSONB],
    *,
    actor_path: str,
    role_path: str,
    is_superuser_path: str,
) -> sa.ColumnElement[bool]:
    role = _json_role(column, role_path)
    normalized_role = _normalized_role(role)
    is_superuser = _json_bool_is_true(column, is_superuser_path)
    return sa.and_(
        sa.func.jsonb_typeof(_json_value(column, actor_path)) == "object",
        sa.or_(
            role.is_(None),
            normalized_role.not_in(_ACTIVE_ROLES),
            role != normalized_role,
            sa.and_(is_superuser, role != "admin"),
            _json_bool_needs_canonicalization(column, is_superuser_path),
        ),
    )


def _canonicalize_actor(
    column: sa.ColumnElement[JSONB],
    *,
    role_path: str,
    is_superuser_path: str,
) -> sa.ColumnElement[JSONB]:
    is_superuser = _json_bool_is_true(column, is_superuser_path)
    role = _json_role(column, role_path)
    with_role = sa.func.jsonb_set(
        column,
        sa.text(role_path),
        sa.case(
            (is_superuser, _ADMIN_ROLE_JSON),
            (_normalized_role(role) == "admin", _ADMIN_ROLE_JSON),
            else_=_USER_ROLE_JSON,
        ),
        True,
    )
    return sa.func.jsonb_set(
        with_role,
        sa.text(is_superuser_path),
        sa.case((is_superuser, _TRUE_JSON), else_=_FALSE_JSON),
        True,
    )


def upgrade() -> None:
    """Canonicalize account and durable execution roles.

    Retired roles become ``user``; every superuser is explicitly represented as
    ``admin``. Audit rows intentionally retain their historical actor role.
    Role-bearing execution snapshots need canonical values because workers
    validate their frozen execution contracts after this release.
    """
    users = sa.table(
        "user",
        sa.column("role", sa.String()),
        sa.column("is_superuser", sa.Boolean()),
    )
    op.execute(
        users.update().values(
            role=sa.case(
                (users.c.is_superuser.is_(True), "admin"),
                (_normalized_role(users.c.role) == "admin", "admin"),
                else_="user",
            )
        )
    )

    schema = get_settings().agno_app_schema
    suite_runs = sa.table(
        "agent_eval_suite_runs",
        sa.column("execution_snapshot", JSONB()),
        schema=schema,
    )
    op.execute(
        suite_runs.update()
        .where(
            _actor_needs_canonicalization(
                suite_runs.c.execution_snapshot,
                actor_path="'{run_manifest,actor}'::text[]",
                role_path="'{run_manifest,actor,role}'::text[]",
                is_superuser_path="'{run_manifest,actor,is_superuser}'::text[]",
            )
        )
        .values(
            execution_snapshot=_canonicalize_actor(
                suite_runs.c.execution_snapshot,
                role_path="'{run_manifest,actor,role}'::text[]",
                is_superuser_path="'{run_manifest,actor,is_superuser}'::text[]",
            )
        )
    )

    case_runs = sa.table(
        "agent_eval_case_runs",
        sa.column("execution_provenance", JSONB()),
        schema=schema,
    )
    op.execute(
        case_runs.update()
        .where(
            _actor_needs_canonicalization(
                case_runs.c.execution_provenance,
                actor_path="'{actor}'::text[]",
                role_path="'{actor,role}'::text[]",
                is_superuser_path="'{actor,is_superuser}'::text[]",
            )
        )
        .values(
            execution_provenance=_canonicalize_actor(
                case_runs.c.execution_provenance,
                role_path="'{actor,role}'::text[]",
                is_superuser_path="'{actor,is_superuser}'::text[]",
            )
        )
    )

    durable_jobs = sa.table(
        "durable_jobs",
        sa.column("kind", sa.String()),
        sa.column("payload", JSONB()),
        schema=schema,
    )
    op.execute(
        durable_jobs.update()
        .where(
            sa.and_(
                durable_jobs.c.kind == "knowledge_ingest",
                _actor_needs_canonicalization(
                    durable_jobs.c.payload,
                    actor_path="'{actor}'::text[]",
                    role_path="'{actor,role}'::text[]",
                    is_superuser_path="'{actor,is_superuser}'::text[]",
                ),
            )
        )
        .values(
            payload=_canonicalize_actor(
                durable_jobs.c.payload,
                role_path="'{actor,role}'::text[]",
                is_superuser_path="'{actor,is_superuser}'::text[]",
            )
        )
    )


def downgrade() -> None:
    """Original specialist-role assignments cannot be reconstructed safely."""
