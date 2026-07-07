from __future__ import annotations

from uuid import UUID

from fastapi_users import schemas
from pydantic import computed_field

from api.auth.claims import scope_claims


class UserRead(schemas.BaseUser[UUID]):
    role: str = "user"

    @computed_field
    @property
    def scopes(self) -> list[str]:
        return scope_claims(self).scopes


class UserCreate(schemas.BaseUserCreate):
    pass


class UserUpdate(schemas.BaseUserUpdate):
    pass
