from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi_users_db_sqlalchemy import (
    SQLAlchemyBaseOAuthAccountTableUUID,
    SQLAlchemyBaseUserTableUUID,
)
from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from uuid import UUID


class AuthBase(DeclarativeBase):
    pass


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, AuthBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, AuthBase):
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'user')", name="ck_user_role"),
        CheckConstraint(
            "is_superuser = (role = 'admin')",
            name="ck_user_role_matches_superuser",
        ),
        CheckConstraint("auth_version >= 1", name="ck_user_auth_version"),
    )

    if TYPE_CHECKING:
        id: UUID

    role: Mapped[str] = mapped_column(
        String(length=32),
        nullable=False,
        default="user",
        server_default="user",
    )
    # Tokens carry this value and are rejected when it no longer matches the
    # account.  Role and credential changes therefore take effect immediately.
    auth_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        "OAuthAccount",
        lazy="joined",
    )
