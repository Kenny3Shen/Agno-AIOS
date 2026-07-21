"""Unit tests for memory prune algorithm and durable handler wiring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.persistence.durable_jobs import JobKind
from api.services.durable_job_handlers import build_durable_job_registry
from api.services.durable_job_service import DurableJobStore
from api.services.memory_prune_service import (
    memory_top_k_score,
    select_memory_ids_to_prune,
    run_memory_prune,
)


def _row(
    memory_id: str,
    *,
    days_ago: float,
    text: str = "User prefers concise security reports with severity levels.",
    topics: list[str] | None = None,
    now: datetime | None = None,
) -> dict:
    wall = now or datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    updated = wall - timedelta(days=days_ago)
    return {
        "memory_id": memory_id,
        "memory": text,
        "topics": topics or [],
        "updated_at": int(updated.timestamp()),
        "created_at": int(updated.timestamp()),
        "user_id": "u1",
    }


def test_select_prunes_stale_by_updated_at() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    rows = [
        _row("fresh", days_ago=10, now=now),
        _row("stale", days_ago=100, now=now),
    ]
    deleted = select_memory_ids_to_prune(
        rows, retention_days=90, top_k=50, now=now
    )
    assert deleted == ["stale"]


def test_select_keeps_top_k_by_score() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    rows = [
        _row("oldish", days_ago=40, text="x", now=now),
        _row(
            "rich",
            days_ago=1,
            text="User owns asset group finance-core and prefers high severity alerts.",
            topics=["assets", "alerts"],
            now=now,
        ),
        _row(
            "mid",
            days_ago=5,
            text="User prefers Chinese language responses for reports.",
            topics=["prefs"],
            now=now,
        ),
        _row("stub", days_ago=2, text="ok", now=now),
    ]
    deleted = select_memory_ids_to_prune(
        rows, retention_days=90, top_k=2, now=now
    )
    # Keep top-2 by score; stub/oldish should go.
    assert "rich" not in deleted
    assert "mid" not in deleted
    assert set(deleted) == {"oldish", "stub"}


def test_top_k_score_prefers_recent_rich_memories() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    rich = memory_top_k_score(
        _row(
            "a",
            days_ago=1,
            text="User is a SOC analyst focusing on ransomware playbooks.",
            topics=["role"],
            now=now,
        ),
        now=now,
    )
    stub = memory_top_k_score(_row("b", days_ago=1, text="hi", now=now), now=now)
    stale = memory_top_k_score(
        _row(
            "c",
            days_ago=60,
            text="User is a SOC analyst focusing on ransomware playbooks.",
            topics=["role"],
            now=now,
        ),
        now=now,
    )
    assert rich > stub
    assert rich > stale


@pytest.mark.asyncio
async def test_run_memory_prune_deletes_selected_ids() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    rows = [
        _row("keep", days_ago=1, now=now),
        _row("drop", days_ago=120, now=now),
    ]

    class FakeDb:
        def __init__(self) -> None:
            self.deleted: list[tuple[list[str], str | None]] = []

        async def get_user_memory_stats(self, limit=None, page=None, user_id=None):
            return [{"user_id": "u1", "total_memories": 2}], 1

        async def get_user_memories(self, **kwargs):
            return rows, len(rows)

        async def delete_user_memories(self, ids, user_id=None):
            self.deleted.append((list(ids), user_id))

    db = FakeDb()
    with patch(
        "api.services.memory_prune_service.get_chat_settings",
        new=AsyncMock(
            return_value={
                "memory_prune_retention_days": 90,
                "memory_prune_top_k": 50,
            }
        ),
    ):
        result = await run_memory_prune(db=db, now=now)
    assert result["deleted"] == 1
    assert result["users"] == 1
    assert db.deleted == [(["drop"], "u1")]


def test_memory_prune_handler_registered() -> None:
    registry = build_durable_job_registry()
    assert JobKind.MEMORY_PRUNE in registry.kinds


@pytest.mark.asyncio
async def test_handle_memory_prune_skips_when_disabled() -> None:
    from datetime import UTC, datetime

    from api.persistence.durable_jobs import DurableJob, JobState
    from api.services import memory_durable_jobs as mod
    from api.services.durable_job_service import JobExecutionContext

    now = datetime.now(UTC)
    job = DurableJob(
        id="job-1",
        kind=JobKind.MEMORY_PRUNE,
        payload={"schedule_next": False},
        idempotency_key="k1",
        state=JobState.RUNNING,
        priority=50,
        attempt_count=1,
        max_attempts=3,
        available_at=now,
        lease_owner="w1",
        lease_expires_at=now,
        heartbeat_at=now,
        last_error=None,
        result=None,
        created_at=now,
        updated_at=now,
        started_at=now,
        finished_at=None,
    )
    context = JobExecutionContext(
        job=job,
        worker_id="w1",
        lease_seconds=30.0,
        lease_lost=__import__("asyncio").Event(),
        _store=cast(DurableJobStore, MagicMock()),
    )
    with (
        patch.object(
            mod,
            "get_chat_settings",
            new=AsyncMock(return_value={"memory_prune_enabled": False}),
        ),
        patch.object(mod, "run_memory_prune", new=AsyncMock()) as prune_mock,
    ):
        result = await mod._handle_memory_prune(job, context)  # noqa: SLF001
    assert result == {"skipped": True, "reason": "memory_prune_enabled=false"}
    prune_mock.assert_not_awaited()
