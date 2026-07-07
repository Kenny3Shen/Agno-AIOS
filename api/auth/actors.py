from __future__ import annotations

from typing import Any, Literal

Role = Literal["admin", "user", "guest"]


def actor_id(user: Any) -> str:
    return str(getattr(user, "id", "") or "")


def actor_role(user: Any) -> Role:
    if bool(getattr(user, "is_superuser", False)):
        return "admin"
    role = str(getattr(user, "role", "user") or "user").lower()
    if role == "admin":
        return "admin"
    if role == "guest":
        return "guest"
    return "user"
