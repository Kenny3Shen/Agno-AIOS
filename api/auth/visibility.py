from __future__ import annotations

from collections.abc import Mapping
from typing import Literal, cast

from api.auth.claims import ADMIN_SCOPE, ActorLike, actor_id, has_scope

ResourceVisibility = Literal["private", "public"]
VALID_VISIBILITIES: set[str] = {"private", "public"}


def normalize_visibility(
    value: str | None,
    *,
    strict: bool = False,
) -> ResourceVisibility:
    raw = (value or "").strip().lower()
    if not raw:
        return "private"
    if raw in VALID_VISIBILITIES:
        return cast(ResourceVisibility, raw)
    if strict:
        raise ValueError("visibility must be private or public")
    return "private"


def visibility_metadata(
    visibility: str | None,
    owner_user_id: str | None,
) -> dict[str, str]:
    clean_owner = (owner_user_id or "").strip()
    metadata = {"visibility": normalize_visibility(visibility)}
    if clean_owner:
        metadata["owner_user_id"] = clean_owner
        metadata["user_id"] = clean_owner
    return metadata


def metadata_visibility(metadata: Mapping[str, object]) -> ResourceVisibility:
    return normalize_visibility(str(metadata.get("visibility") or ""))


def metadata_owner_user_id(metadata: Mapping[str, object]) -> str:
    return str(metadata.get("owner_user_id") or metadata.get("user_id") or "").strip()


def _is_admin(user: ActorLike | None) -> bool:
    return bool(user is not None and has_scope(user, ADMIN_SCOPE))


def can_read_resource(user: ActorLike | None, metadata: Mapping[str, object]) -> bool:
    if _is_admin(user):
        return True
    if metadata_visibility(metadata) == "public":
        return True
    return bool(user is not None and metadata_owner_user_id(metadata) == actor_id(user))


def can_manage_resource(user: ActorLike | None, metadata: Mapping[str, object]) -> bool:
    if _is_admin(user):
        return True
    return bool(user is not None and metadata_owner_user_id(metadata) == actor_id(user))
