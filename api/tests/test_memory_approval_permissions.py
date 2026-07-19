from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agno.memory import UserMemory
from fastapi import HTTPException
import pytest
from starlette.requests import Request

from api.auth.claims import has_scope
from api.routes import memory
from api.services import memory_service


def actor(user_id: str, role: str = "user"):
    return SimpleNamespace(id=user_id, role=role, is_superuser=False)


def request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/memories", "headers": []})


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
        self.upserted: list[UserMemory] = []
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

    async def upsert_user_memory(self, memory: UserMemory, deserialize=True):
        self.upserted.append(memory)
        if self.upsert_returns_none:
            return None
        return memory


def test_guest_cannot_mutate_memory():
    with pytest.raises(HTTPException) as context:
        memory.require_memory_write_permission(user=actor("g1", "guest"))
    assert context.value.status_code == 403


@pytest.mark.asyncio
async def test_delete_memory_route_records_audit():
    current_actor = actor("u1")
    deleted = {"memory_id": "mem-1", "user_id": "u1", "deleted": True}
    with (
        patch.object(memory, "delete_memory_record", new=AsyncMock(return_value=deleted)) as delete_mock,
        patch.object(memory, "record_policy_event", new=AsyncMock()) as audit_mock,
    ):
        result = await memory.delete_memory(
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
        memory,
        "delete_memory_record",
        new=AsyncMock(side_effect=memory.MemoryMutationNotFound("missing")),
    ):
        with pytest.raises(HTTPException) as context:
            await memory.delete_memory("missing", request=request(), user=actor("u1"))
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
    body = memory.MemoryUpdateRequest(
        user_id="other-user",
        memory="Updated memory",
        topics=["preference", "security"],
    )
    with (
        patch.object(memory, "update_memory_record", new=AsyncMock(return_value=payload)) as update_mock,
        patch.object(memory, "record_policy_event", new=AsyncMock()) as audit_mock,
    ):
        result = await memory.update_memory(
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


def test_memory_write_permission_is_not_granted_to_guest():
    assert has_scope(actor("u1", "user"), "memories:write")
    assert not has_scope(actor("guest", "guest"), "memories:write")


@pytest.mark.asyncio
async def test_list_memories_scopes_ordinary_actor_to_own_user_id():
    db = FakeMemoryDb()
    with patch.object(memory_service, "get_async_agno_postgres_db", return_value=db):
        payload = await memory_service.list_memories_native(
            actor("u1"),
            user_id="other-user",
            topic="preference",
            search_content="concise",
        )

    assert db.memory_kwargs["user_id"] == "u1"
    assert db.memory_kwargs["topics"] == ["preference"]
    assert db.memory_kwargs["search_content"] == "concise"
    assert db.stats_kwargs["user_id"] == "u1"
    assert len(payload["data"]) == 1
    assert payload["data"][0]["memory_id"] == "mem-1"
    assert payload["data"][0]["status"] == "review"
    assert "id" not in payload["data"][0]
    assert has_scope(actor("u1"), "memories:read")


@pytest.mark.asyncio
async def test_list_memories_admin_can_filter_requested_user():
    db = FakeMemoryDb()
    with patch.object(memory_service, "get_async_agno_postgres_db", return_value=db):
        payload = await memory_service.list_memories_native(
            actor("admin", "admin"),
            user_id="u2",
        )
    assert db.memory_kwargs["user_id"] == "u2"
    assert db.stats_kwargs["user_id"] == "u2"
    assert payload["data"][0]["user_id"] == "u2"


@pytest.mark.asyncio
async def test_list_memories_without_actor_still_returns_data():
    db = FakeMemoryDb()
    with patch.object(memory_service, "get_async_agno_postgres_db", return_value=db):
        payload = await memory_service.list_memories_native(None)
    assert payload["meta"]["total_count"] == 1
    assert payload["data"][0]["memory_id"] == "mem-1"


@pytest.mark.asyncio
async def test_memory_delete_scopes_ordinary_actor_to_own_user_id():
    db = FakeMemoryMutationDb()
    with patch.object(memory_service, "get_async_agno_postgres_db", return_value=db):
        result = await memory_service.delete_memory_record(
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
    with patch.object(memory_service, "get_async_agno_postgres_db", return_value=db):
        with pytest.raises(memory_service.MemoryMutationNotFound):
            await memory_service.delete_memory_record(
                actor("owner-1"),
                memory_id="missing",
            )

    assert db.deleted == []


@pytest.mark.asyncio
async def test_memory_delete_raises_when_delete_does_not_persist():
    db = FakeMemoryMutationDb()
    db.delete_noop = True
    with patch.object(memory_service, "get_async_agno_postgres_db", return_value=db):
        with pytest.raises(memory_service.MemoryMutationFailed):
            await memory_service.delete_memory_record(
                actor("owner-1"),
                memory_id="mem-1",
            )

    assert db.deleted == [("mem-1", "owner-1")]


@pytest.mark.asyncio
async def test_memory_update_scopes_ordinary_actor_and_replaces_content():
    db = FakeMemoryMutationDb()
    now = datetime(2026, 7, 5, tzinfo=UTC)
    with (
        patch.object(memory_service, "get_async_agno_postgres_db", return_value=db),
        patch.object(memory_service, "now_utc", return_value=now),
    ):
        result = await memory_service.update_memory_record(
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
    with patch.object(memory_service, "get_async_agno_postgres_db", return_value=db):
        with pytest.raises(memory_service.MemoryMutationFailed):
            await memory_service.update_memory_record(
                actor("owner-1"),
                memory_id="mem-1",
                memory="Updated memory",
                topics=["preference"],
            )

    assert len(db.upserted) == 1


@pytest.mark.asyncio
async def test_memory_update_returns_not_found_when_memory_not_in_scope():
    db = FakeMemoryMutationDb()
    with patch.object(memory_service, "get_async_agno_postgres_db", return_value=db):
        with pytest.raises(memory_service.MemoryMutationNotFound):
            await memory_service.update_memory_record(
                actor("owner-1"),
                memory_id="missing",
                memory="Updated memory",
                topics=["preference"],
            )

    assert db.upserted == []


@pytest.mark.asyncio
async def test_list_memories_native_envelope():
    db = FakeMemoryDb()
    with patch.object(memory_service, "get_async_agno_postgres_db", return_value=db):
        payload = await memory_service.list_memories_native(
            actor("u1"),
            search_content="incident",
            page=1,
            limit=20,
        )

    assert db.memory_kwargs["search_content"] == "incident"
    assert db.memory_kwargs["page"] == 1
    assert db.memory_kwargs["limit"] == 20
    assert set(payload.keys()) == {"data", "meta"}
    assert payload["meta"]["page"] == 1
    assert payload["meta"]["limit"] == 20
    assert payload["meta"]["total_count"] == 1
    assert payload["meta"]["total_pages"] == 1
    assert len(payload["data"]) == 1
    assert payload["data"][0]["memory_id"] == "mem-1"
    assert "id" not in payload["data"][0]


@pytest.mark.asyncio
async def test_list_memories_admin_unscoped_stats_uses_page_users_only():
    """Admin all-users list resolves stats only for users on the requested page."""
    db = FakeMemoryDb()
    stats_calls: list[dict[str, object]] = []

    async def tracking_stats(**kwargs: object):
        stats_calls.append(kwargs)
        return (
            [{"user_id": kwargs.get("user_id") or "u1", "total_memories": 12, "last_memory_updated_at": 1}],
            1,
        )

    with (
        patch.object(db, "get_user_memory_stats", tracking_stats),
        patch.object(memory_service, "get_async_agno_postgres_db", return_value=db),
    ):
        payload = await memory_service.list_memories_native(actor("admin", "admin"))
    assert payload["data"][0]["user_id"] == "u1"
    assert len(stats_calls) == 1
    assert stats_calls[0].get("user_id") == "u1"
    assert stats_calls[0].get("limit") == 1
    assert all(call.get("limit") != 500 for call in stats_calls)


@pytest.mark.asyncio
async def test_list_memories_scopes_stats_to_actor_user():
    """Ordinary actors must not trigger unscoped memory stats scans."""
    db = FakeMemoryDb()
    with patch.object(memory_service, "get_async_agno_postgres_db", return_value=db):
        await memory_service.list_memories_native(actor("u1"))
    assert db.stats_kwargs.get("user_id") == "u1"
    assert db.stats_kwargs.get("limit") == 1



@pytest.mark.asyncio
async def test_list_memories_admin_batches_multi_user_stats():
    """Admin page with multiple users uses one GROUP BY when table API exists."""
    class MultiUserDb(FakeMemoryDb):
        async def get_user_memories(self, **kwargs):
            self.memory_kwargs = kwargs
            return (
                [
                    {
                        "memory_id": "m1",
                        "memory": "a",
                        "topics": [],
                        "user_id": "u1",
                        "created_at": 1,
                        "updated_at": 1,
                    },
                    {
                        "memory_id": "m2",
                        "memory": "b",
                        "topics": [],
                        "user_id": "u2",
                        "created_at": 2,
                        "updated_at": 2,
                    },
                ],
                2,
            )

        # No _get_table / async_session_factory → per-user stats fallback.

    stats_calls: list[dict[str, object]] = []

    db = MultiUserDb()

    async def tracking_stats(**kwargs: object):
        stats_calls.append(kwargs)
        uid = kwargs.get("user_id") or "u1"
        total = 51 if uid == "u1" else 3
        return ([{"user_id": uid, "total_memories": total, "last_memory_updated_at": 1}], 1)

    with (
        patch.object(db, "get_user_memory_stats", tracking_stats),
        patch.object(memory_service, "get_async_agno_postgres_db", return_value=db),
    ):
        payload = await memory_service.list_memories_native(actor("admin", "admin"))
    assert {row["user_id"] for row in payload["data"]} == {"u1", "u2"}
    assert {call.get("user_id") for call in stats_calls} == {"u1", "u2"}
    by_user = {row["user_id"]: row["status"] for row in payload["data"]}
    assert by_user["u1"] == "review"
    assert by_user["u2"] == "healthy"
