from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi_users_db_sqlalchemy import (
    SQLAlchemyBaseOAuthAccountTableUUID,
    SQLAlchemyBaseUserTableUUID,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, relationship

if TYPE_CHECKING:
    from uuid import UUID


class AuthBase(DeclarativeBase):
    pass


class OAuthAccount(SQLAlchemyBaseOAuthAccountTableUUID, AuthBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, AuthBase):
    if TYPE_CHECKING:
        id: UUID

    oauth_accounts: Mapped[list[OAuthAccount]] = relationship(
        "OAuthAccount",
        lazy="joined",
    )
