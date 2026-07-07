from __future__ import annotations

from typing import Any

from api.auth.claims import scope_user_id


def owner_user_id(actor: Any | None) -> str | None:
    return scope_user_id(actor, None)


def scoped_requested_user_id(
    actor: Any | None,
    requested_user_id: str | None,
) -> str | None:
    return scope_user_id(actor, requested_user_id)
