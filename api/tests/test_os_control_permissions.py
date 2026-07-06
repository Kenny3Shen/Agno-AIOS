from datetime import UTC, datetime, timedelta
import threading
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from starlette.requests import Request
from api.auth.permissions import has_permission
from api.routes import os_control
from api.services import os_control_service
import pytest


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/os/memory", "headers": []})


class FakeMemoryDb:
    def __init__(self):
        self.memory_kwargs: dict[str, object] = {}
        self.stats_kwargs: dict[str, object] = {}
        self.topics_user_id: str | None = None

    async def get_user_memories(self, **kwargs):
        self.memory_kwargs = kwargs
        return (
            [
                {
                    "memory_id": "mem-1",
                    "memory": "Prefers concise incident summaries",
                    "topics": ["preference"],
                    "input": "Please keep incident summaries short.",
                    "user_id": kwargs.get("user_id") or "u1",
                    "agent_id": "security-operations",
                    "created_at": 1714560000,
                    "updated_at": 1714560300,
                }
            ],
            1,
        )

    async def get_user_memory_stats(self, **kwargs):
        self.stats_kwargs = kwargs
        return (
            [
                {
                    "user_id": kwargs.get("user_id") or "u1",
                    "total_memories": 51,
                    "last_memory_updated_at": 1714560300,
                }
            ],
            1,
        )

    async def get_all_memory_topics(self, user_id=None):
        self.topics_user_id = user_id
        return ["preference"]


class FakeMemoryMutationDb(FakeMemoryDb):
    def __init__(self):
        super().__init__()
        self.get_memory_kwargs: dict[str, object] = {}
        self.deleted: list[tuple[str, str | None]] = []
        self.deleted_ids: set[str] = set()
        self.delete_noop = False
        self.upsert_returns_none = False
        self.upserted: list[Any] = []
        self.now = datetime(2026, 7, 5, tzinfo=UTC)

    async def get_user_memory(self, memory_id, **kwargs):
        self.get_memory_kwargs = {"memory_id": memory_id, **kwargs}
        if memory_id == "missing" or memory_id in self.deleted_ids:
            return None
        return {
            "memory_id": memory_id,
            "memory": "Prefers concise incident summaries",
            "topics": ["preference"],
            "input": "Please keep incident summaries short.",
            "user_id": kwargs.get("user_id") or "owner-1",
            "agent_id": "security-operations",
            "created_at": self.now - timedelta(days=120),
            "updated_at": self.now - timedelta(days=120),
        }

    async def get_user_memories(self, **kwargs):
        self.memory_kwargs = kwargs
        return (
            [
                {
                    "memory_id": "old-1",
                    "memory": "Old memory",
                    "topics": ["preference"],
                    "input": "old",
                    "user_id": kwargs.get("user_id") or "owner-1",
                    "agent_id": "security-operations",
                    "created_at": self.now - timedelta(days=130),
                    "updated_at": self.now - timedelta(days=120),
                },
                {
                    "memory_id": "fresh-1",
                    "memory": "Fresh memory",
                    "topics": ["preference"],
                    "input": "fresh",
                    "user_id": kwargs.get("user_id") or "owner-1",
                    "agent_id": "security-operations",
                    "created_at": self.now - timedelta(days=4),
                    "updated_at": self.now - timedelta(days=3),
                },
            ],
            2,
        )

    async def delete_user_memory(self, memory_id, user_id=None):
        self.deleted.append((memory_id, user_id))
        if not self.delete_noop:
            self.deleted_ids.add(memory_id)

    async def upsert_user_memory(self, memory, deserialize=True):
        self.upserted.append(memory)
        if self.upsert_returns_none:
            return None
        return memory


def test_guest_cannot_access_studio_inventory():
    with pytest.raises(HTTPException) as context:
        os_control.require_os_module_permission("studio", user=actor("g1", "guest"))
    assert context.value.status_code == 403


def test_unknown_module_is_rejected_before_payload_lookup():
    with pytest.raises(HTTPException) as context:
        os_control.require_os_module_permission("unknown", user=actor("u1"))
    assert context.value.status_code == 404


def test_guest_cannot_mutate_memory():
    with pytest.raises(HTTPException) as context:
        os_control.require_memory_write_permission(user=actor("g1", "guest"))
    assert context.value.status_code == 403


@pytest.mark.asyncio
async def test_route_passes_actor_to_service():
    current_actor = actor("u1")
    with patch.object(
        os_control, "get_control_payload", new=AsyncMock(return_value={"module": "sessions"})
    ) as mocked:
        result = await os_control.get_os_control_module("sessions", user=current_actor)
    assert result["module"] == "sessions"
    mocked.assert_awaited_once_with("sessions", actor=current_actor, query=None)


@pytest.mark.asyncio
async def test_sync_control_payload_handler_runs_off_event_loop():
    event_loop_thread_id = threading.get_ident()
    handler_thread_id: int | None = None

    def sync_handler(actor=None):
        nonlocal handler_thread_id
        del actor
        handler_thread_id = threading.get_ident()
        return {"module": "threaded"}

    with patch.dict(os_control_service.MODULE_HANDLERS, {"threaded": sync_handler}):
        result = await os_control_service.get_control_payload("threaded", actor=actor("u1"))

    assert result == {"module": "threaded"}
    assert handler_thread_id is not None
    assert handler_thread_id != event_loop_thread_id


@pytest.mark.asyncio
async def test_delete_memory_route_records_audit():
    current_actor = actor("u1")
    deleted = {"memory_id": "mem-1", "user_id": "u1", "deleted": True}
    with (
        patch.object(os_control, "delete_memory_record", new=AsyncMock(return_value=deleted)) as delete_mock,
        patch.object(os_control, "record_policy_event", new=AsyncMock()) as audit_mock,
    ):
        result = await os_control.delete_os_memory(
            "mem-1",
            request=request(),
            user_id="other-user",
            user=current_actor,
        )

    assert result == deleted
    delete_mock.assert_awaited_once_with(
        current_actor,
        memory_id="mem-1",
        user_id="other-user",
    )
    audit_mock.assert_awaited_once()
    event = audit_mock.call_args.args[1]
    assert event.action == "memory.delete"
    assert event.resource_id == "mem-1"
    assert event.metadata == {"user_id": "u1"}


@pytest.mark.asyncio
async def test_delete_memory_route_maps_missing_to_404():
    with patch.object(
        os_control,
        "delete_memory_record",
        new=AsyncMock(side_effect=os_control_service.MemoryMutationNotFound("missing")),
    ):
        with pytest.raises(HTTPException) as context:
            await os_control.delete_os_memory("missing", request=request(), user=actor("u1"))
    assert context.value.status_code == 404


@pytest.mark.asyncio
async def test_update_memory_route_records_audit():
    current_actor = actor("u1")
    payload = {
        "memory_id": "mem-1",
        "user_id": "u1",
        "memory": "Updated memory",
        "topics": ["preference", "security"],
    }
    body = os_control.MemoryUpdateRequest(
        user_id="other-user",
        memory="Updated memory",
        topics=["preference", "security"],
    )
    with (
        patch.object(os_control, "update_memory_record", new=AsyncMock(return_value=payload)) as update_mock,
        patch.object(os_control, "record_policy_event", new=AsyncMock()) as audit_mock,
    ):
        result = await os_control.update_os_memory(
            "mem-1",
            body,
            request=request(),
            user=current_actor,
        )

    assert result == payload
    update_mock.assert_awaited_once_with(
        current_actor,
        memory_id="mem-1",
        user_id="other-user",
        memory="Updated memory",
        topics=["preference", "security"],
    )
    audit_mock.assert_awaited_once()
    event = audit_mock.call_args.args[1]
    assert event.action == "memory.update"
    assert event.resource_id == "mem-1"
    assert event.metadata == {"user_id": "u1", "topics": 2}


@pytest.mark.asyncio
async def test_session_payload_filters_to_current_user():
    captured: dict[str, object] = {}

    async def fake_get_all_sessions(
        *, owner_user_id: str | None, include_archived: bool = False
    ):
        captured["owner_user_id"] = owner_user_id
        captured["include_archived"] = include_archived
        return []

    with patch.object(os_control_service, "get_all_sessions_async", fake_get_all_sessions):
        await os_control_service.get_sessions_payload(actor("u1"))
    assert captured["owner_user_id"] == "u1"
    assert captured["include_archived"] is True


@pytest.mark.asyncio
async def test_admin_session_payload_can_read_all_users():
    captured: dict[str, object] = {}

    async def fake_get_all_sessions(
        *, owner_user_id: str | None, include_archived: bool = False
    ):
        captured["owner_user_id"] = owner_user_id
        return []

    with patch.object(os_control_service, "get_all_sessions_async", fake_get_all_sessions):
        await os_control_service.get_sessions_payload(actor("admin", "admin"))
    assert captured["owner_user_id"] is None


def test_metrics_user_scope_uses_current_user():
    assert os_control_service._owner_user_id(actor("u1"), "trace:read:any") == "u1"


def test_metrics_admin_scope_reads_all_users():
    assert os_control_service._owner_user_id(actor("admin", "admin"), "trace:read:any") is None


def test_memory_write_permission_is_not_granted_to_guest():
    assert has_permission(actor("u1", "user"), "memory:write:own")
    assert not has_permission(actor("guest", "guest"), "memory:write:own")


@pytest.mark.asyncio
async def test_memory_payload_uses_current_user_for_ordinary_actor():
    db = FakeMemoryDb()
    with patch.object(os_control_service, "get_async_agno_postgres_db", return_value=db):
        payload = await os_control_service.get_memory_payload(
            actor("u1"), user_id="other-user", topic="preference", search="concise"
        )
    assert db.memory_kwargs["user_id"] == "u1"
    assert db.memory_kwargs["topics"] == ["preference"]
    assert db.memory_kwargs["search_content"] == "concise"
    assert db.stats_kwargs["user_id"] == "u1"
    assert db.topics_user_id == "u1"
    assert payload["memory_filters"]["user_id"] == "u1"
    assert payload["memory_users"][0]["status"] == "review"
    assert payload["memories"][0]["status"] == "review"
    assert payload["records"][0]["status"] == "review"


@pytest.mark.asyncio
async def test_memory_payload_admin_can_filter_requested_user():
    db = FakeMemoryDb()
    with patch.object(os_control_service, "get_async_agno_postgres_db", return_value=db):
        payload = await os_control_service.get_memory_payload(
            actor("admin", "admin"), user_id="u2"
        )
    assert db.memory_kwargs["user_id"] == "u2"
    assert db.stats_kwargs["user_id"] is None
    assert db.topics_user_id == "u2"
    assert payload["memory_filters"]["user_id"] == "u2"
    assert payload["memory_mode"]["update_memory_on_run"]
    assert payload["memory_mode"]["enable_session_summaries"]


@pytest.mark.asyncio
async def test_memory_payload_without_actor_is_readonly():
    db = FakeMemoryDb()
    with patch.object(os_control_service, "get_async_agno_postgres_db", return_value=db):
        payload = await os_control_service.get_memory_payload(None)
    assert payload["memory_mode"]["readonly"] is True


@pytest.mark.asyncio
async def test_memory_delete_scopes_ordinary_actor_to_own_user_id():
    db = FakeMemoryMutationDb()
    with patch.object(os_control_service, "get_async_agno_postgres_db", return_value=db):
        result = await os_control_service.delete_memory_record(
            actor("owner-1"),
            memory_id="mem-1",
            user_id="other-user",
        )

    assert db.get_memory_kwargs["memory_id"] == "mem-1"
    assert db.get_memory_kwargs["user_id"] == "owner-1"
    assert db.deleted == [("mem-1", "owner-1")]
    assert result["deleted"] is True
    assert result["user_id"] == "owner-1"


@pytest.mark.asyncio
async def test_memory_delete_returns_not_found_when_memory_not_in_scope():
    db = FakeMemoryMutationDb()
    with patch.object(os_control_service, "get_async_agno_postgres_db", return_value=db):
        with pytest.raises(os_control_service.MemoryMutationNotFound):
            await os_control_service.delete_memory_record(
                actor("owner-1"),
                memory_id="missing",
            )

    assert db.deleted == []


@pytest.mark.asyncio
async def test_memory_delete_raises_when_delete_does_not_persist():
    db = FakeMemoryMutationDb()
    db.delete_noop = True
    with patch.object(os_control_service, "get_async_agno_postgres_db", return_value=db):
        with pytest.raises(os_control_service.MemoryMutationFailed):
            await os_control_service.delete_memory_record(
                actor("owner-1"),
                memory_id="mem-1",
            )

    assert db.deleted == [("mem-1", "owner-1")]


@pytest.mark.asyncio
async def test_memory_update_scopes_ordinary_actor_and_replaces_content():
    db = FakeMemoryMutationDb()
    now = datetime(2026, 7, 5, tzinfo=UTC)
    with (
        patch.object(os_control_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(os_control_service, "_now", return_value=now),
    ):
        result = await os_control_service.update_memory_record(
            actor("owner-1"),
            memory_id="mem-1",
            user_id="other-user",
            memory="Updated memory",
            topics=["preference", "security", "preference", ""],
        )

    assert db.get_memory_kwargs["memory_id"] == "mem-1"
    assert db.get_memory_kwargs["user_id"] == "owner-1"
    assert len(db.upserted) == 1
    saved = db.upserted[0]
    assert saved.memory_id == "mem-1"
    assert saved.user_id == "owner-1"
    assert saved.memory == "Updated memory"
    assert saved.topics == ["preference", "security"]
    assert saved.input == "Please keep incident summaries short."
    assert saved.agent_id == "security-operations"
    assert result["memory"] == "Updated memory"
    assert result["topics"] == ["preference", "security"]
    assert result["user_id"] == "owner-1"


@pytest.mark.asyncio
async def test_memory_update_raises_when_upsert_fails():
    db = FakeMemoryMutationDb()
    db.upsert_returns_none = True
    with patch.object(os_control_service, "get_async_agno_postgres_db", return_value=db):
        with pytest.raises(os_control_service.MemoryMutationFailed):
            await os_control_service.update_memory_record(
                actor("owner-1"),
                memory_id="mem-1",
                memory="Updated memory",
                topics=["preference"],
            )

    assert len(db.upserted) == 1


@pytest.mark.asyncio
async def test_memory_update_returns_not_found_when_memory_not_in_scope():
    db = FakeMemoryMutationDb()
    with patch.object(os_control_service, "get_async_agno_postgres_db", return_value=db):
        with pytest.raises(os_control_service.MemoryMutationNotFound):
            await os_control_service.update_memory_record(
                actor("owner-1"),
                memory_id="missing",
                memory="Updated memory",
                topics=["preference"],
            )

    assert db.upserted == []
