from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import jwt
from agno.os.middleware.jwt import JWTMiddleware
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
import pytest
from starlette.requests import Request

from api.auth import router as auth_router
from api.auth import claims
from api.auth.claims import actor_role, has_scope, scope_claims, scope_user_id
from api.auth.models import User
from api.tests.route_fakes import route_dependency

ADMIN_SCOPE = "agent_os:admin"


def user(role: str = "user", is_superuser: bool = False, auth_version: int = 1):
    return SimpleNamespace(
        id=uuid4(),
        role=role,
        is_superuser=is_superuser,
        auth_version=auth_version,
    )


def test_superuser_is_admin():
    actor = user("user", is_superuser=True)

    assert actor_role(actor) == "admin"
    assert has_scope(actor, ADMIN_SCOPE)
    assert has_scope(actor, "traces:read")


def test_admin_claims_use_agentos_admin_scope():
    actor_claims = scope_claims(user("admin"))

    assert actor_claims.role == "admin"
    assert actor_claims.scopes == [ADMIN_SCOPE]


def test_user_scopes_cover_normal_workspace_operations():
    actor = user()

    for scope in (
        "sessions:read",
        "sessions:write",
        "workflows:read",
        "workflows:write",
        "workflows:run",
        "traces:read",
        "memories:read",
        "memories:write",
        "memories:delete",
        "metrics:read",
        "collect:read",
        "collect:write",
        "cve:read",
        "knowledge:read",
        "knowledge:write",
        "knowledge:delete",
        "mcp:read",
        "mcp:submit",
        "skill:read",
        "skill:submit",
        "approvals:read",
        "approvals:write",
        "config:read",
        "evals:read",
    ):
        assert has_scope(actor, scope), scope

    for scope in (
        "config:write",
        "mcp:write",
        "skill:write",
        "evals:write",
        "evals:delete",
        "audit:read",
        ADMIN_SCOPE,
    ):
        assert not has_scope(actor, scope), scope


def test_scope_claims_are_expanded_as_agentos_scopes():
    actor_claims = scope_claims(user())

    assert actor_claims.role == "user"
    assert "sessions:read" in actor_claims.scopes
    assert "approvals:write" in actor_claims.scopes
    assert "audit:read" not in actor_claims.scopes
    assert "session:read:own" not in actor_claims.scopes
    assert "agent_eval:read" not in actor_claims.scopes


def test_user_read_rejects_noncanonical_roles_and_aligns_superusers():
    from api.auth.schemas import UserRead

    with pytest.raises(ValidationError):
        UserRead.model_validate(
            {
                "id": uuid4(),
                "email": "member@example.com",
                "role": "author",
                "is_active": True,
                "is_superuser": False,
                "is_verified": False,
            }
        )
    superuser = UserRead(
        id=uuid4(),
        email="admin@example.com",
        role="user",
        is_active=True,
        is_superuser=True,
        is_verified=False,
    ).model_dump()

    assert superuser["role"] == "admin"
    assert superuser["scopes"] == [ADMIN_SCOPE]


def test_public_user_schemas_do_not_expose_role_assignment():
    from api.auth.schemas import UserCreate, UserUpdate

    assert "role" not in UserCreate.model_fields
    assert "role" not in UserUpdate.model_fields
    with pytest.raises(ValidationError):
        UserCreate.model_validate(
            {
                "email": "member@example.com",
                "password": "secure-password",
                "role": "admin",
            }
        )
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({"role": "admin"})
    with pytest.raises(ValidationError):
        UserCreate.model_validate(
            {
                "email": "member@example.com",
                "password": "secure-password",
                "is_superuser": True,
            }
        )
    with pytest.raises(ValidationError):
        UserUpdate.model_validate({"is_superuser": True})


def test_admin_role_update_only_accepts_the_two_product_roles():
    from api.auth.router import AdminRoleUpdate

    assert AdminRoleUpdate(role="admin").role == "admin"
    assert AdminRoleUpdate(role="user").role == "user"
    with pytest.raises(ValidationError):
        AdminRoleUpdate.model_validate({"role": "author"})


@pytest.mark.asyncio
async def test_role_catalog_is_admin_only_and_contains_two_roles():
    dependency = route_dependency(auth_router.router, "list_role_presets")
    with pytest.raises(HTTPException) as exc:
        dependency(user=user())
    assert exc.value.status_code == 403

    catalog = await auth_router.list_role_presets(_admin=user("admin"))

    assert [preset["role"] for preset in catalog["data"]] == ["admin", "user"]


def test_scope_user_id_uses_actor_for_ordinary_users():
    actor = SimpleNamespace(id="u1", role="user", is_superuser=False)

    assert scope_user_id(actor, "other-user") == "u1"


def test_scope_user_id_allows_admin_requested_user_or_all_users():
    admin = user("admin")

    assert scope_user_id(admin, "u2") == "u2"
    assert scope_user_id(admin, None) is None


@pytest.mark.asyncio
async def test_fastapi_users_jwt_embeds_agentos_scopes():
    from api.auth.users import ScopedJWTStrategy

    actor = user("admin")
    secret = "test-secret-with-at-least-32-bytes"
    strategy = ScopedJWTStrategy(secret=secret, lifetime_seconds=60)

    token = await strategy.write_token(actor)
    payload = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"verify_aud": False},
    )

    assert payload["sub"] == str(actor.id)
    assert payload["aud"] == ["fastapi-users:auth"]
    assert payload["role"] == "admin"
    assert payload["scopes"] == [ADMIN_SCOPE]
    assert payload["auth_version"] == 1


@pytest.mark.asyncio
async def test_fastapi_users_jwt_rejects_stale_or_legacy_authorization_versions():
    from api.auth.users import ScopedJWTStrategy

    actor = user(auth_version=4)
    secret = "test-secret-with-at-least-32-bytes"
    strategy = ScopedJWTStrategy(secret=secret, lifetime_seconds=60)

    class UserManager:
        def parse_id(self, value: str):
            return value

        async def get(self, _user_id: str):
            return actor

    manager = cast(Any, UserManager())
    current_token = await strategy.write_token(actor)
    assert await strategy.read_token(current_token, manager) is actor

    actor.auth_version = 5
    assert await strategy.read_token(current_token, manager) is None

    legacy_token = jwt.encode(
        {
            "sub": str(actor.id),
            "aud": ["fastapi-users:auth"],
            "role": "user",
            "scopes": ["sessions:read"],
        },
        secret,
        algorithm="HS256",
    )
    assert await strategy.read_token(legacy_token, manager) is None


@pytest.mark.asyncio
async def test_password_update_advances_authorization_version(
    monkeypatch: pytest.MonkeyPatch,
):
    from api.auth.schemas import UserUpdate
    from api.auth.users import UserManager

    target = _role_target(role="user", is_superuser=False, auth_version=7)
    manager = UserManager(AsyncMock())
    captured: dict[str, object] = {}

    async def update_user(row, values):
        captured.update(values)
        row.auth_version = values["auth_version"]
        return row

    on_after_update = AsyncMock()
    monkeypatch.setattr(manager, "_update", update_user)
    monkeypatch.setattr(manager, "on_after_update", on_after_update)

    result = await manager.update(UserUpdate(password="new-secure-password"), target)

    assert result is target
    assert target.auth_version == 8
    assert captured == {"password": "new-secure-password", "auth_version": 8}
    assert on_after_update.await_args is not None
    update_args = on_after_update.await_args
    assert update_args.args[0] is target
    assert update_args.args[1] == captured


@pytest.mark.asyncio
async def test_token_version_middleware_rejects_stale_jwt_before_route_execution(
    monkeypatch: pytest.MonkeyPatch,
):
    from api.auth import token_version
    from api.auth.token_version import UserTokenVersionMiddleware
    from api.auth.users import ScopedJWTStrategy

    actor = user(auth_version=1)
    secret = "test-secret-with-at-least-32-bytes"
    token = await ScopedJWTStrategy(secret=secret, lifetime_seconds=60).write_token(actor)
    app = FastAPI()
    app.add_middleware(UserTokenVersionMiddleware, secret=secret)

    @app.get("/protected")
    async def protected():
        return {"ok": True}

    monkeypatch.setattr(
        token_version,
        "active_account_authorization_version",
        AsyncMock(return_value=2),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/protected", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication token is no longer valid"


class _RoleSession:
    def __init__(self, row, *, active_admin_count: int = 0) -> None:
        self.row = row
        self.active_admin_count = active_admin_count
        self.locked = False
        self.committed = False
        self.refreshed = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _tb):
        return None

    async def execute(self, _statement):
        self.locked = True

    async def get(self, _model, _user_id, **_kwargs):
        return self.row

    async def scalar(self, _statement):
        return self.active_admin_count

    def add(self, _row):
        return None

    async def commit(self):
        self.committed = True

    async def refresh(self, _row):
        self.refreshed = True


def _role_target(*, role: str, is_superuser: bool, auth_version: int = 1, active: bool = True):
    from api.auth.models import User

    return User(
        id=uuid4(),
        email="target@example.com",
        hashed_password="hashed",
        is_active=active,
        is_superuser=is_superuser,
        is_verified=True,
        role=role,
        auth_version=auth_version,
    )


@pytest.mark.asyncio
async def test_admin_role_update_promotes_and_revokes_prior_tokens(
    monkeypatch: pytest.MonkeyPatch,
):
    target = _role_target(role="user", is_superuser=False, auth_version=7)
    session = _RoleSession(target)
    audit = AsyncMock()
    monkeypatch.setattr(auth_router, "async_session_maker", lambda: session)
    monkeypatch.setattr(auth_router, "record_audit_event_async", audit)
    monkeypatch.setattr(auth_router, "audit_request_context", lambda _request: {})

    result = await auth_router.set_user_role(
        target.id,
        auth_router.AdminRoleUpdate(role="admin"),
        cast(Request, SimpleNamespace()),
        admin=cast(User, user("admin", is_superuser=True)),
    )

    assert session.locked and session.committed and session.refreshed
    assert target.role == "admin"
    assert target.is_superuser is True
    assert target.auth_version == 8
    assert result.role == "admin"
    assert audit.await_args is not None
    audit_args = audit.await_args
    assert audit_args.kwargs["metadata"]["from"] == "user"
    assert audit_args.kwargs["metadata"]["to"] == "admin"
    assert audit_args.kwargs["metadata"]["auth_version"] == 8


@pytest.mark.asyncio
async def test_admin_role_update_can_demote_nonfinal_admin_and_revokes_tokens(
    monkeypatch: pytest.MonkeyPatch,
):
    target = _role_target(role="admin", is_superuser=True, auth_version=2)
    session = _RoleSession(target, active_admin_count=2)
    monkeypatch.setattr(auth_router, "async_session_maker", lambda: session)
    monkeypatch.setattr(auth_router, "record_audit_event_async", AsyncMock())
    monkeypatch.setattr(auth_router, "audit_request_context", lambda _request: {})

    await auth_router.set_user_role(
        target.id,
        auth_router.AdminRoleUpdate(role="user"),
        cast(Request, SimpleNamespace()),
        admin=cast(User, user("admin", is_superuser=True)),
    )

    assert target.role == "user"
    assert target.is_superuser is False
    assert target.auth_version == 3


@pytest.mark.asyncio
async def test_admin_role_update_protects_self_and_last_active_admin(
    monkeypatch: pytest.MonkeyPatch,
):
    target = _role_target(role="admin", is_superuser=True)
    session = _RoleSession(target, active_admin_count=1)
    monkeypatch.setattr(auth_router, "async_session_maker", lambda: session)

    with pytest.raises(HTTPException) as final_admin:
        await auth_router.set_user_role(
            target.id,
            auth_router.AdminRoleUpdate(role="user"),
            cast(Request, SimpleNamespace()),
            admin=cast(User, user("admin", is_superuser=True)),
        )
    assert final_admin.value.status_code == 409

    with pytest.raises(HTTPException) as self_change:
        await auth_router.set_user_role(
            target.id,
            auth_router.AdminRoleUpdate(role="user"),
            cast(Request, SimpleNamespace()),
            admin=cast(
                User,
                SimpleNamespace(id=target.id, role="admin", is_superuser=True),
            ),
        )
    assert self_change.value.status_code == 403


def test_main_app_installs_jwt_middleware():
    from api.auth.token_version import UserTokenVersionMiddleware
    from api.main import JWT_EXCLUDED_ROUTE_PATHS, app

    assert claims.ADMIN_SCOPE == ADMIN_SCOPE
    middleware = next(
        (item for item in app.user_middleware if item.cls is JWTMiddleware),
        None,
    )

    assert middleware is not None
    assert middleware.kwargs["algorithm"] == "HS256"
    assert middleware.kwargs["authorization"] is True
    assert middleware.kwargs["admin_scope"] == ADMIN_SCOPE
    assert middleware.kwargs["user_isolation"] is True
    assert any(item.cls is UserTokenVersionMiddleware for item in app.user_middleware)
    assert "/api/auth/*" in JWT_EXCLUDED_ROUTE_PATHS
    assert "/" in JWT_EXCLUDED_ROUTE_PATHS
