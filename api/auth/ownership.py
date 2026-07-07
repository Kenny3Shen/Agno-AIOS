from __future__ import annotations

from fastapi import HTTPException, status

from api.auth.claims import ActorLike, actor_id, actor_role


def assert_owned_resource(
    actor: ActorLike,
    *,
    owner_user_id: str | None,
    resource_name: str,
) -> None:
    if actor_role(actor) == "admin":
        return
    if owner_user_id and str(owner_user_id) == actor_id(actor):
        return
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"{resource_name} 不存在",
    )
