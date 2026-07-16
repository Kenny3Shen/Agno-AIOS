"""Role preset catalog and admin assignment endpoints."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from api.auth import router as auth_router
from api.auth.claims import ROLE_SCOPES


def test_role_catalog_covers_product_presets():
    for role in ("admin", "user", "analyst", "author", "approver", "auditor", "guest"):
        assert role in ROLE_SCOPES


@pytest.mark.asyncio
async def test_list_roles_requires_auth_and_returns_presets():
    app = FastAPI()
    app.include_router(auth_router.router)

    admin = SimpleNamespace(
        id=uuid4(),
        email="admin@example.com",
        role="admin",
        is_superuser=True,
        is_active=True,
        is_verified=True,
    )

    app.dependency_overrides[auth_router.current_active_user] = lambda: admin

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/auth/roles")
    assert response.status_code == 200
    roles = {item["role"] for item in response.json()["data"]}
    assert {"analyst", "author", "approver", "auditor", "user", "guest", "admin"} <= roles
