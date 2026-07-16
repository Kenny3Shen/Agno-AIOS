from __future__ import annotations

from uuid import UUID

from fastapi_users import schemas
from pydantic import Field, computed_field, field_validator

from api.auth.claims import normalize_role, scope_claims


class UserRead(schemas.BaseUser[UUID]):
    role: str = "user"

    @computed_field
    @property
    def scopes(self) -> list[str]:
        return scope_claims(self).scopes


class UserCreate(schemas.BaseUserCreate):
    role: str = Field(default="user")

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        role = normalize_role(value)
        if role == "admin":
            # Non-admin registration cannot self-promote; bootstrap/admin API only.
            return "user"
        return role


class UserUpdate(schemas.BaseUserUpdate):
    role: str | None = None

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        role = normalize_role(value)
        return role
