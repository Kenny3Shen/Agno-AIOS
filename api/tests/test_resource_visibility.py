from types import SimpleNamespace
from uuid import uuid4

import pytest

from api.auth.visibility import (
    can_manage_resource,
    can_read_resource,
    metadata_visibility,
    normalize_visibility,
    visibility_metadata,
)


def actor(actor_id: str, role: str = "user", is_superuser: bool = False):
    return SimpleNamespace(id=actor_id, role=role, is_superuser=is_superuser)


def test_visibility_normalizes_missing_values_to_private():
    assert normalize_visibility(None) == "private"
    assert normalize_visibility("") == "private"
    assert metadata_visibility({}) == "private"
    assert metadata_visibility({"visibility": "unexpected"}) == "private"


def test_visibility_rejects_unknown_client_values():
    with pytest.raises(ValueError):
        normalize_visibility("shared", strict=True)


def test_visibility_metadata_includes_owner_when_present():
    assert visibility_metadata("public", "u1") == {
        "visibility": "public",
        "owner_user_id": "u1",
        "user_id": "u1",
    }


def test_public_read_and_owner_admin_manage_rules():
    owner = actor("u1")
    other = actor("u2")
    admin = actor(str(uuid4()), role="admin", is_superuser=True)
    public = {"visibility": "public", "owner_user_id": "u1"}
    private = {"visibility": "private", "owner_user_id": "u1"}

    assert can_read_resource(other, public)
    assert can_read_resource(owner, private)
    assert not can_read_resource(other, private)
    assert can_read_resource(admin, private)

    assert can_manage_resource(owner, public)
    assert can_manage_resource(admin, public)
    assert not can_manage_resource(other, public)
