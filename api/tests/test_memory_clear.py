"""Memory clear + user-scoped bulk delete."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from api.services.memory_service import clear_memory_records


class FakeClearDb:
    def __init__(self):
        self.rows = [
            {"memory_id": "m1", "user_id": "u1", "memory": "a"},
            {"memory_id": "m2", "user_id": "u1", "memory": "b"},
            {"memory_id": "m3", "user_id": "u2", "memory": "c"},
        ]
        self.cleared_all = False
        self.deleted_batches: list[tuple[list[str], str | None]] = []

    async def clear_memories(self):
        self.cleared_all = True
        self.rows = []

    async def get_user_memories(self, **kwargs):
        uid = kwargs.get("user_id")
        limit = int(kwargs.get("limit") or 100)
        filtered = [r for r in self.rows if uid is None or r["user_id"] == uid]
        page = filtered[:limit]
        return page, len(filtered)

    async def delete_user_memories(self, memory_ids, user_id=None):
        ids = set(memory_ids)
        self.deleted_batches.append((list(memory_ids), user_id))
        self.rows = [
            r
            for r in self.rows
            if r["memory_id"] not in ids
            or (user_id is not None and r["user_id"] != user_id)
        ]


@pytest.mark.asyncio
async def test_clear_user_memories(monkeypatch):
    fake = FakeClearDb()
    monkeypatch.setattr(
        "api.services.memory_service.get_async_agno_postgres_db",
        lambda: fake,
    )
    actor = SimpleNamespace(id="u1", role="user", is_superuser=False)
    result = await clear_memory_records(actor, user_id="someone-else")
    assert result["user_id"] == "u1"
    assert result["deleted"] == 2
    assert result["all_users"] is False
    assert all(r["user_id"] != "u1" for r in fake.rows)


@pytest.mark.asyncio
async def test_clear_all_requires_admin(monkeypatch):
    fake = FakeClearDb()
    monkeypatch.setattr(
        "api.services.memory_service.get_async_agno_postgres_db",
        lambda: fake,
    )
    actor = SimpleNamespace(id="u1", role="user", is_superuser=False)
    with pytest.raises(PermissionError):
        await clear_memory_records(actor, all_users=True)
    assert fake.cleared_all is False


@pytest.mark.asyncio
async def test_clear_all_admin(monkeypatch):
    fake = FakeClearDb()
    monkeypatch.setattr(
        "api.services.memory_service.get_async_agno_postgres_db",
        lambda: fake,
    )
    actor = SimpleNamespace(id="admin", role="admin", is_superuser=True)
    result = await clear_memory_records(actor, all_users=True)
    assert result["all_users"] is True
    assert result["deleted"] == -1
    assert fake.cleared_all is True
