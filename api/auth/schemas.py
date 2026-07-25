from __future__ import annotations

from uuid import UUID

from fastapi_users import schemas
from pydantic import ConfigDict, computed_field, field_validator, model_validator

from api.auth.claims import Role, normalize_role, scope_claims


class UserRead(schemas.BaseUser[UUID]):
    role: Role = "user"

    @field_validator("role", mode="before")
    @classmethod
    def normalize_persisted_role(cls, value: object) -> Role:
        """Present retired database roles as the consolidated user role."""
        return normalize_role(value)

    @model_validator(mode="after")
    def align_role_with_superuser(self) -> UserRead:
        self.role = scope_claims(self).role
        return self

    @computed_field
    @property
    def scopes(self) -> list[str]:
        return scope_claims(self).scopes


class UserCreate(schemas.BaseUserCreate):
    """Public registration payload without product-role assignment."""

    model_config = ConfigDict(extra="forbid")


class UserUpdate(schemas.BaseUserUpdate):
    """Public profile update payload without product-role assignment."""

    model_config = ConfigDict(extra="forbid")
