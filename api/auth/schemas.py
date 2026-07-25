from __future__ import annotations

from uuid import UUID

from fastapi_users import schemas
from pydantic import ConfigDict, EmailStr, computed_field, field_validator, model_validator

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


class UserCreate(schemas.CreateUpdateDictModel):
    """Public registration payload without product-role assignment."""

    email: EmailStr
    password: str
    model_config = ConfigDict(extra="forbid")


class UserUpdate(schemas.CreateUpdateDictModel):
    """Public profile update payload without product-role assignment."""

    email: EmailStr | None = None
    password: str | None = None
    model_config = ConfigDict(extra="forbid")
