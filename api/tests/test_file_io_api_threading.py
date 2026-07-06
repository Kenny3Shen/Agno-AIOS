from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

from fastapi import Request
import pytest

from api.auth.models import User
from api.routes import mcp, skills
from api.services.mcp_config_service import McpConfigChange

FAKE_REQUEST = cast(Request, None)
FAKE_USER = cast(User, object())


async def async_noop(*_args, **_kwargs) -> None:
    return None


@pytest.mark.asyncio
async def test_mcp_update_config_runs_file_io_off_event_loop() -> None:
    thread_calls: list[str] = []
    body = mcp.ServiceToggle(id="playbook", enabled=False)
    change = McpConfigChange(
        response={"success": True},
        action="mcp.config_update",
        resource_type="mcp_service",
        resource_id="playbook",
    )

    async def fake_run_sync(func, *args):
        thread_calls.append(func.__name__)
        return func(*args)

    def fake_apply_service_toggle(_service_id: str, _enabled: bool) -> McpConfigChange:
        return change

    fake_apply_service_toggle.__name__ = "apply_service_toggle"

    with (
        patch.object(mcp, "apply_service_toggle", fake_apply_service_toggle),
        patch.object(mcp, "_record_config_change", async_noop),
        patch.object(
            mcp,
            "to_thread",
            SimpleNamespace(run_sync=fake_run_sync),
            create=True,
        ),
    ):
        result = await mcp.update_config(
            request=FAKE_REQUEST,
            body=body,
            user=FAKE_USER,
        )

    assert result == {"success": True}
    assert thread_calls == ["apply_service_toggle"]


@pytest.mark.asyncio
async def test_mcp_upload_runs_file_io_off_event_loop() -> None:
    thread_calls: list[str] = []
    body = mcp.McpUploadRequest(
        name="Filesystem",
        manifest='{"mcpServers":{"filesystem":{"command":"python"}}}',
    )
    change = McpConfigChange(
        response={
            "success": True,
            "name": "Filesystem",
            "kind": "mcp-json",
            "restart_required": True,
        },
        action="mcp.upload",
        resource_type="mcp",
        resource_id="Filesystem",
    )

    async def fake_run_sync(func, *args):
        thread_calls.append(func.func.__name__ if hasattr(func, "func") else func.__name__)
        return func(*args)

    def fake_apply_mcp_upload(**_kwargs) -> McpConfigChange:
        return change

    fake_apply_mcp_upload.__name__ = "apply_mcp_upload"

    with (
        patch.object(mcp, "apply_mcp_upload", fake_apply_mcp_upload),
        patch.object(mcp, "_record_config_change", async_noop),
        patch.object(
            mcp,
            "to_thread",
            SimpleNamespace(run_sync=fake_run_sync),
            create=True,
        ),
    ):
        result = await mcp.upload_mcp(
            request=FAKE_REQUEST,
            body=body,
            user=FAKE_USER,
        )

    assert result.name == "Filesystem"
    assert thread_calls == ["apply_mcp_upload"]


@pytest.mark.asyncio
async def test_skill_toggle_runs_file_io_off_event_loop() -> None:
    thread_calls: list[str] = []

    async def fake_run_sync(func, *args):
        thread_calls.append(func.__name__)
        return func(*args)

    def fake_set_skill_enabled(_skill_name: str, _enabled: bool) -> str:
        return "triage"

    fake_set_skill_enabled.__name__ = "set_skill_enabled"

    with (
        patch.object(skills, "set_skill_enabled", fake_set_skill_enabled),
        patch.object(skills, "record_audit_event_async", async_noop),
        patch.object(
            skills,
            "to_thread",
            SimpleNamespace(run_sync=fake_run_sync),
            create=True,
        ),
    ):
        result = await skills.toggle_skill(
            request=FAKE_REQUEST,
            skill_name="triage",
            body=skills.SkillToggleRequest(enabled=False),
            user=FAKE_USER,
        )

    assert result.name == "triage"
    assert result.enabled is False
    assert thread_calls == ["set_skill_enabled"]
