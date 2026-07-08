from __future__ import annotations

from api.auth.claims import ActorLike, scope_user_id


def scoped_requested_user_id(
    actor: ActorLike | None,
    requested_user_id: str | None,
) -> str | None:
    return scope_user_id(actor, requested_user_id)
