from __future__ import annotations

from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Request

from api.auth.models import User
from api.routes import settings
from api.services import cve_source_settings_service
from api.tests.route_fakes import route_dependency


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/api/settings/cve-sources",
            "headers": [(b"user-agent", b"settings-browser")],
            "client": ("10.0.0.9", 44321),
        }
    )


def test_cve_source_settings_write_requires_admin_scope() -> None:
    dependency = route_dependency(settings.router, "patch_cve_source_settings")

    with pytest.raises(HTTPException) as exc:
        dependency(user=SimpleNamespace(role="user", is_superuser=False))

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_patch_cve_source_settings_persists_and_audits() -> None:
    actor = SimpleNamespace(id="admin-1", role="admin", is_superuser=False)
    body = settings.CVESourceSettingsUpdate(sources={"marcio-cve": False})
    saved_sources = [
        {"source": "github", "enabled": True},
        {"source": "marcio-cve", "enabled": False},
        {"source": "exploit-db", "enabled": True},
    ]

    with (
        patch.object(
            settings,
            "update_cve_source_settings",
            new=AsyncMock(return_value=saved_sources),
        ) as save_mock,
        patch.object(settings, "record_audit_event_async", new=AsyncMock()) as audit_mock,
    ):
        result = await settings.patch_cve_source_settings(
            _request(),
            body,
            user=cast(User, actor),
        )

    assert result == {"sources": saved_sources}
    save_mock.assert_awaited_once_with({"marcio-cve": False}, settings.DATA_SOURCES)
    audit_call = audit_mock.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "settings.cve_sources.update"
    assert audit_call.kwargs["metadata"] == {"sources": {"marcio-cve": False}}


@pytest.mark.asyncio
async def test_patch_cve_source_settings_rejects_unknown_source() -> None:
    body = settings.CVESourceSettingsUpdate(sources={"unknown-source": False})

    with patch.object(
        settings,
        "update_cve_source_settings",
        new=AsyncMock(side_effect=ValueError("Unknown CVE source(s): unknown-source")),
    ):
        with pytest.raises(HTTPException) as exc:
            await settings.patch_cve_source_settings(
                _request(),
                body,
                user=cast(User, SimpleNamespace(id="admin-1", role="admin")),
            )

    assert exc.value.status_code == 400
    assert "unknown-source" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_service_preserves_order_and_defaults_unknown_rows_to_enabled() -> None:
    with patch.object(
        cve_source_settings_service,
        "get_cve_source_enabled_map",
        new=AsyncMock(return_value={"github": False, "marcio-cve": True}),
    ):
        sources = await cve_source_settings_service.get_cve_source_settings(
            ["github", "marcio-cve", "exploit-db"]
        )
        enabled = await cve_source_settings_service.get_enabled_cve_source_names(
            ["github", "marcio-cve", "exploit-db"]
        )

    assert sources == [
        {"source": "github", "enabled": False},
        {"source": "marcio-cve", "enabled": True},
        {"source": "exploit-db", "enabled": True},
    ]
    assert enabled == ["marcio-cve", "exploit-db"]
