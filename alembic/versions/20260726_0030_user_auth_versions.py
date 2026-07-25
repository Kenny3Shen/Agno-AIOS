"""Bind product roles to superuser state and add JWT authorization versions.

Revision ID: 20260726_0030
Revises: 20260725_0029
Create Date: 2026-07-26 09:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260726_0030"
down_revision: str | Sequence[str] | None = "20260725_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Make access state canonical before new JWTs depend on it."""
    op.add_column(
        "user",
        sa.Column(
            "auth_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.execute(
        """
        UPDATE "user"
        SET
            role = CASE
                WHEN is_superuser IS TRUE OR lower(trim(role)) = 'admin' THEN 'admin'
                ELSE 'user'
            END,
            is_superuser = CASE
                WHEN is_superuser IS TRUE OR lower(trim(role)) = 'admin' THEN true
                ELSE false
            END
        """
    )
    op.create_check_constraint(
        "ck_user_role",
        "user",
        "role IN ('admin', 'user')",
    )
    op.create_check_constraint(
        "ck_user_role_matches_superuser",
        "user",
        "is_superuser = (role = 'admin')",
    )
    op.create_check_constraint(
        "ck_user_auth_version",
        "user",
        "auth_version >= 1",
    )


def downgrade() -> None:
    op.drop_constraint("ck_user_auth_version", "user")
    op.drop_constraint("ck_user_role_matches_superuser", "user")
    op.drop_constraint("ck_user_role", "user")
    op.drop_column("user", "auth_version")
