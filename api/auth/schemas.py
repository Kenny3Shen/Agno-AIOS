from __future__ import annotations

from uuid import UUID

from fastapi_users import schemas
from pydantic import computed_field

from api.auth.permissions import permission_claims


class UserRead(schemas.BaseUser[UUID]):
    role: str = "user"

    @computed_field
    @property
    def permissions(self) -> list[str]:
        return permission_claims(self).permissions


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass
