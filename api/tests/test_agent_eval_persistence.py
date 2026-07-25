import asyncio
from typing import Any
from unittest.mock import ANY, AsyncMock

import pytest
from sqlalchemy.dialects import postgresql

from api.persistence import agent_evals as persistence
from api.persistence.durable_jobs import JobKind
from api.utils.async_once import AsyncOnce


def _suite_run_values(*, suite_run_id: str = "suite-run-1") -> dict[str, Any]:
    return {
        "id": suite_run_id,
        "suite_id": "suite-1",
        "status": "queued",
        "started_by": "user-1",
        "execution_snapshot": {
            "run_manifest": {"actor": {"id": "user-1"}},
        },
    }


def _work_item_values(
    *,
    suite_run_id: str = "suite-run-1",
    case_id: str = "case-1",
    index: int = 0,
) -> dict[str, Any]:
    return {
        "id": f"case-run-{index + 1}",
        "suite_run_id": suite_run_id,
        "case_id": case_id,
        "work_item_index": index,
        "status": "queued",
        "definition_snapshot": {"id": case_id},
        "execution_provenance": {"target": {"kind": "agent", "id": "agent-1"}},
    }


@pytest.mark.asyncio
async def test_ensure_agent_eval_tables_serializes_concurrent_schema_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(persistence, "_agent_eval_tables_once", AsyncOnce())
    schema_check = AsyncMock()
    monkeypatch.setattr(
        persistence,
        "ensure_control_plane_schema_current",
        schema_check,
    )

    await asyncio.gather(
        persistence.ensure_agent_eval_tables_async(),
        persistence.ensure_agent_eval_tables_async(),
    )

    schema_check.assert_awaited_once_with()


def test_case_table_has_structured_guidelines_and_json_tags() -> None:
    table = persistence.agent_eval_cases_table()

    assert "judge_mode" in table.c
    assert table.c.judge_mode.nullable is False
    assert "additional_guidelines" in table.c
    assert table.c.additional_guidelines.nullable is False
    assert "tags" in table.c
    assert table.c.tags.nullable is False
    assert any(index.name == "idx_agent_eval_cases_tags" for index in table.indexes)


def test_run_tables_have_private_immutable_snapshot_columns() -> None:
    suite_runs = persistence.agent_eval_suite_runs_table()
    case_runs = persistence.agent_eval_case_runs_table()

    assert "execution_snapshot" in suite_runs.c
    assert suite_runs.c.execution_snapshot.nullable is False
    assert "definition_snapshot" in case_runs.c
    assert "execution_provenance" in case_runs.c
    assert "terminal_checkpoint" in case_runs.c
    assert "active_job_id" in suite_runs.c
    assert "active_lease_epoch" in suite_runs.c
    assert "lease_job_id" in case_runs.c
    assert "lease_epoch" in case_runs.c
    assert "work_item_index" in case_runs.c
    assert case_runs.c.definition_snapshot.nullable is False
    assert case_runs.c.execution_provenance.nullable is False
    assert case_runs.c.terminal_checkpoint.nullable is False
    assert any(
        index.name == "uq_agent_eval_case_runs_fenced_suite_case"
        and index.unique
        for index in case_runs.indexes
    )
    assert {
        "uq_agent_eval_case_runs_work_item_order",
        "uq_agent_eval_case_runs_work_item_case",
    }.issubset({index.name for index in case_runs.indexes})


def test_pack_removal_requires_an_unambiguous_strict_tag_pair() -> None:
    assert persistence._matches_exact_imported_pack_tags(
        ["safety", "pack:harmbench", "pack_version:2026.07.1"],
        pack_id="harmbench",
        pack_version="2026.07.1",
    )
    assert not persistence._matches_exact_imported_pack_tags(
        ["safety", "harmbench", "pack_version:2026.07.1"],
        pack_id="harmbench",
        pack_version="2026.07.1",
    )
    assert not persistence._matches_exact_imported_pack_tags(
        [
            "safety",
            "pack:harmbench",
            "pack:other",
            "pack_version:2026.07.1",
        ],
        pack_id="harmbench",
        pack_version="2026.07.1",
    )


@pytest.mark.asyncio
async def test_child_writes_take_key_share_locks_on_their_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A suite-tree delete cannot race a Case or run insertion into an orphan."""

    class Result:
        def __init__(
            self,
            *,
            parent_id: str | None = None,
            row: dict[str, Any] | None = None,
        ) -> None:
            self.parent_id = parent_id
            self.row = row

        def scalar_one_or_none(self) -> str | None:
            return self.parent_id

        def mappings(self):
            return self

        def one(self) -> dict[str, Any]:
            assert self.row is not None
            return self.row

    parent_ids = iter(["suite-1", "suite-1", None, "suite-run-1", "case-1"])
    executed: list[Any] = []

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            if statement.is_select:
                return Result(parent_id=next(parent_ids))
            return Result(row={"id": f"row-{len(executed)}"})

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(
        persistence,
        "ensure_agent_eval_tables_async",
        AsyncMock(),
    )
    monkeypatch.setattr(
        persistence,
        "get_async_control_plane_engine",
        lambda: Engine(),
    )
    monkeypatch.setattr(
        persistence.durable_job_store,
        "enqueue_job_in_transaction",
        AsyncMock(return_value=object()),
    )

    await persistence.create_case_row_async({"id": "case-1", "suite_id": "suite-1"})
    await persistence.create_suite_run_with_case_runs_and_enqueue_job_async(
        _suite_run_values(),
        case_run_values=[_work_item_values()],
        kind=JobKind.EVAL_SUITE_RUN,
        payload={"suite_run_id": "suite-run-1"},
        idempotency_key="eval-suite-run:suite-run-1",
    )
    await persistence.create_case_run_row_async(
        {"id": "case-run-1", "suite_run_id": "suite-run-1"}
    )
    await persistence.create_case_run_row_async(
        {"id": "case-run-direct", "suite_run_id": "", "case_id": "case-1"}
    )

    lock_sql = [
        str(statement.compile(dialect=postgresql.dialect()))
        for statement in executed
        if statement.is_select
    ]
    assert len(lock_sql) == 5
    assert "FOR KEY SHARE" in lock_sql[0]
    assert "FOR UPDATE" in lock_sql[1]
    assert "FOR UPDATE" in lock_sql[2]
    assert "FOR KEY SHARE" in lock_sql[3]
    assert "FOR KEY SHARE" in lock_sql[4]
    assert "agent_eval_suites" in lock_sql[0]
    assert "agent_eval_suites" in lock_sql[1]
    assert "agent_eval_suite_runs" in lock_sql[2]
    assert "agent_eval_suite_runs" in lock_sql[3]
    assert "agent_eval_cases" in lock_sql[4]


@pytest.mark.asyncio
async def test_snapshot_backed_replay_locks_source_case_run_not_deleted_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = {"id": "case-1", "input": "private prompt"}
    executed: list[Any] = []

    class Result:
        def __init__(
            self,
            *,
            row: dict[str, Any] | None = None,
        ) -> None:
            self.row = row

        def mappings(self):
            return self

        def one_or_none(self) -> dict[str, Any] | None:
            return self.row

        def one(self) -> dict[str, Any]:
            assert self.row is not None
            return self.row

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            if statement.is_select:
                return Result(
                    row={
                        "id": "case-run-source",
                        "case_id": "case-1",
                        "definition_snapshot": snapshot,
                    }
                )
            return Result(row={"id": "case-run-replay", "case_id": "case-1"})

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())

    row = await persistence.create_case_run_row_async(
        {
            "id": "case-run-replay",
            "suite_run_id": "",
            "case_id": "case-1",
            "replay_of_case_run_id": "case-run-source",
            "definition_snapshot": snapshot,
        },
        replay_source_case_run_id="case-run-source",
    )

    assert row["id"] == "case-run-replay"
    lock_sql = str(executed[0].compile(dialect=postgresql.dialect()))
    assert "agent_eval_case_runs" in lock_sql
    assert "agent_eval_cases" not in lock_sql
    assert "FOR KEY SHARE" in lock_sql


@pytest.mark.asyncio
async def test_replay_row_rejects_a_snapshot_that_does_not_match_its_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        def mappings(self):
            return self

        def one_or_none(self) -> dict[str, Any]:
            return {
                "id": "case-run-source",
                "case_id": "case-1",
                "definition_snapshot": {"input": "source prompt"},
            }

    class Connection:
        async def execute(self, _statement):
            return Result()

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())

    with pytest.raises(ValueError, match="must match"):
        await persistence.create_case_run_row_async(
            {
                "id": "case-run-replay",
                "suite_run_id": "",
                "case_id": "case-1",
                "replay_of_case_run_id": "case-run-source",
                "definition_snapshot": {"input": "tampered prompt"},
            },
            replay_source_case_run_id="case-run-source",
        )


@pytest.mark.asyncio
async def test_run_snapshot_columns_cannot_be_updated_after_insert() -> None:
    with pytest.raises(ValueError, match="execution_snapshot is immutable"):
        await persistence.update_suite_run_row_async(
            "suite-run-1", {"execution_snapshot": {"target": "changed"}}
        )
    with pytest.raises(ValueError, match="immutable"):
        await persistence.update_case_run_row_async(
            "case-run-1", {"definition_snapshot": {"input": "changed"}}
        )
    with pytest.raises(ValueError, match="immutable"):
        await persistence.update_case_run_row_async(
            "case-run-1", {"terminal_checkpoint": {"version": 1}}
        )
    for immutable_identity in (
        {"suite_run_id": "other-suite-run"},
        {"case_id": "other-case"},
        {"work_item_index": 2},
    ):
        with pytest.raises(ValueError, match="immutable"):
            await persistence.update_case_run_row_async(
                "case-run-1", immutable_identity
            )


@pytest.mark.asyncio
async def test_complete_case_run_cas_requires_queued_row_and_empty_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first terminal writer owns the checkpoint; stale workers update nothing."""

    executed: list[Any] = []

    class Result:
        def mappings(self):
            return self

        def one_or_none(self) -> dict[str, Any] | None:
            return None

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            return Result()

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())

    result = await persistence.complete_case_run_row_if_queued_async(
        "case-run-1",
        values={"status": "passed", "completed_at": "2026-07-25T00:00:00Z"},
        terminal_checkpoint={"version": 1, "status": "passed"},
    )

    assert result is None
    assert len(executed) == 1
    compiled = executed[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "UPDATE " in sql
    assert "agent_eval_case_runs" in sql
    assert "terminal_checkpoint" in sql
    # The SQL-level CAS guards both lifecycle state and the virgin JSONB
    # sentinel. A later worker receives None and cannot replace evidence.
    assert "status" in sql
    assert any(
        value == "queued" or (isinstance(value, (list, tuple)) and "queued" in value)
        for value in compiled.params.values()
    )
    assert any(value == {} for value in compiled.params.values())


@pytest.mark.asyncio
async def test_fenced_case_completion_requires_the_current_suite_lease(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A fenced Case completion locks its SuiteRun before its CaseRun row."""

    executed: list[Any] = []

    class Result:
        def __init__(self, *, suite_run_id: str | None = None) -> None:
            self.suite_run_id = suite_run_id

        def scalar_one_or_none(self) -> str | None:
            return self.suite_run_id

        def mappings(self):
            return self

        def one_or_none(self) -> None:
            return None

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            if statement.is_select:
                return Result(suite_run_id="suite-run-1")
            return Result()

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())

    result = await persistence.complete_case_run_row_if_queued_async(
        "case-run-1",
        values={"status": "passed"},
        terminal_checkpoint={"version": 1, "status": "passed"},
        job_id="job-1",
        lease_epoch=4,
    )

    assert result is None
    assert len(executed) == 3
    durable_lock_compiled = executed[0].compile(dialect=postgresql.dialect())
    durable_lock_sql = str(durable_lock_compiled)
    suite_lock_compiled = executed[1].compile(dialect=postgresql.dialect())
    suite_lock_sql = str(suite_lock_compiled)
    update_compiled = executed[2].compile(dialect=postgresql.dialect())
    update_sql = str(update_compiled)
    assert "SELECT" in durable_lock_sql
    assert "durable_jobs" in durable_lock_sql
    assert "FOR UPDATE OF durable_jobs" in durable_lock_sql
    assert "eval_suite_run" in str(durable_lock_compiled.params.values())
    assert "running" in str(durable_lock_compiled.params.values())
    assert "lease_epoch" in durable_lock_sql
    assert "lease_expires_at > clock_timestamp()" in durable_lock_sql
    assert "suite_run_id" in str(durable_lock_compiled.params.values())
    assert "SELECT" in suite_lock_sql
    assert "agent_eval_suite_runs" in suite_lock_sql
    assert "FOR UPDATE OF agent_eval_suite_runs" in suite_lock_sql
    assert "active_job_id" in suite_lock_sql
    assert "active_lease_epoch" in suite_lock_sql
    assert "UPDATE" in update_sql
    assert "EXISTS" not in update_sql
    assert "lease_job_id" in update_sql
    assert "lease_epoch" in update_sql
    assert "job-1" in durable_lock_compiled.params.values()
    assert 4 in durable_lock_compiled.params.values()


@pytest.mark.asyncio
async def test_fenced_case_update_stops_before_suite_or_case_write_when_durable_lease_changed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A newer durable epoch rejects a stale CaseRun write before SuiteRun/CaseRun."""

    executed: list[Any] = []

    class Result:
        def scalar_one_or_none(self) -> None:
            return None

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            return Result()

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())

    result = await persistence.update_case_run_row_if_execution_lease_async(
        "case-run-1",
        job_id="job-1",
        lease_epoch=4,
        values={"error_summary": "stale worker"},
    )

    assert result is None
    assert len(executed) == 1
    compiled = executed[0].compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "SELECT" in sql
    assert "FOR UPDATE OF durable_jobs" in sql
    assert "lease_expires_at > clock_timestamp()" in sql
    assert executed[0].is_update is False


@pytest.mark.asyncio
async def test_suite_execution_claim_only_accepts_a_newer_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Claim SQL binds status, job identity, and monotonic epoch in one CAS."""

    executed: list[Any] = []

    class Result:
        def scalar_one_or_none(self) -> str:
            return "suite-run-1"

        def mappings(self):
            return self

        def one_or_none(self) -> None:
            return None

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            return Result()

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())

    result = await persistence.claim_suite_run_execution_row_async(
        "suite-run-1",
        job_id="job-1",
        lease_epoch=4,
    )

    assert result is None
    assert len(executed) == 2
    durable_compiled = executed[0].compile(dialect=postgresql.dialect())
    durable_sql = str(durable_compiled)
    claim_compiled = executed[1].compile(dialect=postgresql.dialect())
    claim_sql = str(claim_compiled)
    assert "FOR UPDATE OF durable_jobs" in durable_sql
    assert "lease_expires_at > clock_timestamp()" in durable_sql
    assert "suite_run_id" in str(durable_compiled.params.values())
    assert "active_job_id" in claim_sql
    assert "active_lease_epoch" in claim_sql
    assert "<" in claim_sql
    assert "queued" in str(claim_compiled.params.values())
    assert "running" in str(claim_compiled.params.values())
    assert "cancelling" in str(claim_compiled.params.values())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("expected_statuses", "values"),
    [
        (("running",), {"summary": {"completed_cases": 1}}),
        (
            ("running",),
            {
                "status": "passed",
                "summary": {"completed_cases": 1},
                "error_summary": "",
            },
        ),
    ],
    ids=("progress", "terminal"),
)
async def test_fenced_suite_write_locks_the_live_durable_job_first(
    monkeypatch: pytest.MonkeyPatch,
    expected_statuses: tuple[str, ...],
    values: dict[str, Any],
) -> None:
    """Progress and terminal Suite writes both reject an expired/stale job lease."""

    executed: list[Any] = []

    class Result:
        def scalar_one_or_none(self) -> str:
            return "suite-run-1"

        def mappings(self):
            return self

        def one_or_none(self) -> None:
            return None

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            return Result()

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())

    result = await persistence.update_suite_run_row_if_execution_lease_async(
        "suite-run-1",
        expected_statuses=expected_statuses,
        job_id="job-1",
        lease_epoch=4,
        values=values,
    )

    assert result is None
    assert len(executed) == 2
    durable_sql = str(executed[0].compile(dialect=postgresql.dialect()))
    suite_sql = str(executed[1].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE OF durable_jobs" in durable_sql
    assert "lease_expires_at > clock_timestamp()" in durable_sql
    assert "UPDATE" in suite_sql
    assert "active_job_id" in suite_sql
    assert "active_lease_epoch" in suite_sql


@pytest.mark.asyncio
async def test_fenced_case_claim_locks_durable_job_before_suite_and_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A CaseRun claim observes durable job -> SuiteRun -> CaseRun lock order."""

    values = _work_item_values()
    existing_row = {
        **values,
        "terminal_checkpoint": {},
        "lease_job_id": "",
        "lease_epoch": 0,
    }
    claimed_row = {
        **existing_row,
        "status": "running",
        "lease_job_id": "job-1",
        "lease_epoch": 4,
    }
    executed: list[Any] = []
    select_count = 0

    class Result:
        def __init__(
            self,
            *,
            scalar: str | None = None,
            row: dict[str, Any] | None = None,
        ) -> None:
            self.scalar = scalar
            self.row = row

        def scalar_one_or_none(self) -> str | None:
            return self.scalar

        def mappings(self):
            return self

        def one_or_none(self) -> dict[str, Any] | None:
            return self.row

        def one(self) -> dict[str, Any]:
            assert self.row is not None
            return self.row

    class Connection:
        async def execute(self, statement):
            nonlocal select_count
            executed.append(statement)
            if statement.is_select:
                select_count += 1
                if select_count == 1:
                    return Result(scalar="suite-run-1")
                if select_count == 2:
                    return Result(
                        row={
                            "id": "suite-run-1",
                            "active_job_id": "job-1",
                            "active_lease_epoch": 4,
                            "status": "running",
                        }
                    )
                return Result(row=existing_row)
            return Result(row=claimed_row)

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())

    claimed = await persistence.claim_suite_case_run_row_async(
        values,
        job_id="job-1",
        lease_epoch=4,
    )

    assert claimed == (claimed_row, True)
    assert len(executed) == 4
    durable_sql = str(executed[0].compile(dialect=postgresql.dialect()))
    suite_sql = str(executed[1].compile(dialect=postgresql.dialect()))
    case_sql = str(executed[2].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE OF durable_jobs" in durable_sql
    assert "FOR UPDATE" in suite_sql
    assert "agent_eval_suite_runs" in suite_sql
    assert "FOR UPDATE" in case_sql
    assert "agent_eval_case_runs" in case_sql
    assert executed[3].is_update


@pytest.mark.asyncio
async def test_suite_run_and_durable_job_share_one_parent_locked_transaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        def __init__(
            self,
            *,
            parent_id: str | None = None,
            row: dict[str, Any] | None = None,
        ) -> None:
            self.parent_id = parent_id
            self.row = row

        def scalar_one_or_none(self) -> str | None:
            return self.parent_id

        def mappings(self):
            return self

        def one(self) -> dict[str, Any]:
            assert self.row is not None
            return self.row

    executed: list[Any] = []
    select_count = 0

    class Connection:
        async def execute(self, statement):
            nonlocal select_count
            executed.append(statement)
            if statement.is_select:
                select_count += 1
                return Result(parent_id="suite-1" if select_count == 1 else None)
            return Result(row={"id": "suite-run-1", "suite_id": "suite-1"})

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    enqueue = AsyncMock(return_value=object())
    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())
    monkeypatch.setattr(
        persistence.durable_job_store,
        "enqueue_job_in_transaction",
        enqueue,
    )

    row, job = await persistence.create_suite_run_with_case_runs_and_enqueue_job_async(
        _suite_run_values(),
        case_run_values=[_work_item_values()],
        kind=JobKind.EVAL_SUITE_RUN,
        payload={"suite_run_id": "suite-run-1"},
        idempotency_key="eval-suite-run:suite-run-1",
    )

    assert row["id"] == "suite-run-1"
    assert job is enqueue.return_value
    assert len(executed) == 4
    lock_sql = str(executed[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in lock_sql
    assert executed[2].is_insert
    assert executed[3].is_insert
    enqueue.assert_awaited_once_with(
        ANY,
        kind=JobKind.EVAL_SUITE_RUN,
        payload={"suite_run_id": "suite-run-1"},
        idempotency_key="eval-suite-run:suite-run-1",
        max_attempts=5,
        priority=0,
    )


@pytest.mark.asyncio
async def test_atomic_suite_enqueue_rejects_an_existing_active_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        def __init__(self, value: str | None) -> None:
            self.value = value

        def scalar_one_or_none(self) -> str | None:
            return self.value

    values = iter(("suite-1", "existing-run"))

    class Connection:
        async def execute(self, _statement):
            return Result(next(values))

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    enqueue = AsyncMock()
    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())
    monkeypatch.setattr(
        persistence.durable_job_store,
        "enqueue_job_in_transaction",
        enqueue,
    )

    with pytest.raises(persistence.ActiveEvalSuiteRunError, match="existing-run"):
        await persistence.create_suite_run_with_case_runs_and_enqueue_job_async(
            _suite_run_values(suite_run_id="suite-run-2"),
            case_run_values=[_work_item_values(suite_run_id="suite-run-2")],
            kind=JobKind.EVAL_SUITE_RUN,
            payload={"suite_run_id": "suite-run-2"},
            idempotency_key="eval-suite-run:suite-run-2",
        )

    enqueue.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("values", "payload", "message"),
    [
        (
            _suite_run_values(),
            {"suite_run_id": "other-run"},
            "payload must contain only its suite_run_id",
        ),
        (
            {**_suite_run_values(), "started_by": "other-user"},
            {"suite_run_id": "suite-run-1"},
            "started_by must match",
        ),
    ],
)
async def test_atomic_suite_enqueue_rejects_mismatched_private_identity(
    values: dict[str, Any],
    payload: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        await persistence.create_suite_run_with_case_runs_and_enqueue_job_async(
            values,
            case_run_values=[_work_item_values()],
            kind=JobKind.EVAL_SUITE_RUN,
            payload=payload,
            idempotency_key="eval-suite-run:suite-run-1",
        )


@pytest.mark.asyncio
async def test_cancel_suite_run_locks_latest_summary_before_marking_cancelling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation must merge worker progress committed before its row lock."""

    locked_row = {
        "id": "suite-run-1",
        "suite_id": "suite-1",
        "status": "running",
        "started_by": "user-1",
        "error_summary": "",
        "summary": {
            "completed_cases": 2,
            "total": 4,
            "cases": [{"case_id": "case-1", "status": "passed"}],
        },
        "started_at": "2026-07-25T00:00:00+00:00",
        "completed_at": None,
    }
    requested_at = "2026-07-25T00:00:01+00:00"
    merged_summary = {
        **locked_row["summary"],
        "cancel_requested": True,
        "cancel_requested_at": requested_at,
    }
    updated_row = {
        **locked_row,
        "status": "cancelling",
        "error_summary": "Eval suite cancellation requested",
        "summary": merged_summary,
    }

    class Result:
        def __init__(self, row: dict[str, Any]) -> None:
            self.row = row

        def mappings(self):
            return self

        def one_or_none(self) -> dict[str, Any]:
            return self.row

    rows = iter((locked_row, updated_row))
    executed: list[Any] = []

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            return Result(next(rows))

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())

    result = await persistence.request_suite_run_cancel_row_async(
        "suite-run-1",
        cancel_requested_at=requested_at,
    )

    assert result == updated_row
    assert len(executed) == 2
    lock_sql = str(executed[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in lock_sql
    assert "agent_eval_suite_runs" in lock_sql
    update_params = executed[1].compile(dialect=postgresql.dialect()).params
    assert update_params["status"] == "cancelling"
    assert update_params["summary"] == merged_summary
    assert update_params["error_summary"] == "Eval suite cancellation requested"


@pytest.mark.asyncio
async def test_child_write_rejects_a_parent_deleted_before_its_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        def scalar_one_or_none(self) -> None:
            return None

    executed: list[Any] = []

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            return Result()

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(
        persistence,
        "ensure_agent_eval_tables_async",
        AsyncMock(),
    )
    monkeypatch.setattr(
        persistence,
        "get_async_control_plane_engine",
        lambda: Engine(),
    )

    with pytest.raises(ValueError, match="Eval suite not found"):
        await persistence.create_case_row_async(
            {"id": "case-1", "suite_id": "suite-removed"}
        )

    assert len(executed) == 1
    assert executed[0].is_select


@pytest.mark.asyncio
async def test_pack_removal_deletes_all_cases_in_the_strictly_owned_suite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case metadata never gates deletion once the Suite identity is exact."""

    class Result:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self.rows = rows

        def mappings(self):
            return self

        def all(self) -> list[dict[str, object]]:
            return self.rows

    select_rows = iter(
        [
            [
                {
                    "id": "suite-harmbench",
                    "tags": [
                        "safety",
                        "pack:harmbench",
                        "pack_version:2026.07.1",
                    ],
                }
            ],
            [
                {
                    "id": "case-imported",
                    "suite_id": "suite-harmbench",
                    # A stale historical metadata value must not block the
                    # Suite-owned artifact from being removed.
                    "metadata": {"pack_id": "old-wrong-value"},
                }
            ],
            [{"id": "suite-run-1", "status": "passed"}],
            [{"id": "case-run-1"}],
            [{"id": "eval-job-1"}],
        ]
    )
    executed: list[Any] = []

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            if statement.is_select:
                return Result(next(select_rows))
            return Result([])

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(
        persistence,
        "ensure_agent_eval_tables_async",
        AsyncMock(),
    )
    monkeypatch.setattr(
        persistence,
        "get_async_control_plane_engine",
        lambda: Engine(),
    )

    result = await persistence.remove_imported_pack_rows_async(
        "harmbench",
        pack_version="2026.07.1",
    )

    assert result == {
        "pack_id": "harmbench",
        "pack_version": "2026.07.1",
        "suite_ids": ["suite-harmbench"],
        "suites_deleted": 1,
        "cases_deleted": 1,
        "suite_runs_deleted": 1,
        "case_runs_deleted": 1,
        "durable_jobs_deleted": 1,
    }
    deleted_tables = [
        statement.table.name for statement in executed if statement.is_delete
    ]
    assert deleted_tables == [
        "durable_jobs",
        "agent_eval_case_runs",
        "agent_eval_suite_runs",
        "agent_eval_cases",
        "agent_eval_suites",
    ]


@pytest.mark.asyncio
async def test_manual_suite_removal_reuses_the_atomic_suite_tree_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self.rows = rows

        def mappings(self):
            return self

        def all(self) -> list[dict[str, object]]:
            return self.rows

        def one_or_none(self) -> dict[str, object] | None:
            return self.rows[0] if self.rows else None

    select_rows = iter(
        [
            [{"id": "suite-manual", "tags": ["release"]}],
            [{"id": "case-manual", "suite_id": "suite-manual"}],
            [{"id": "suite-run-1", "status": "passed"}],
            [{"id": "case-run-1"}],
            [],
        ]
    )
    executed: list[Any] = []

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            if statement.is_select:
                return Result(next(select_rows))
            return Result([])

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(
        persistence,
        "ensure_agent_eval_tables_async",
        AsyncMock(),
    )
    monkeypatch.setattr(
        persistence,
        "get_async_control_plane_engine",
        lambda: Engine(),
    )

    result = await persistence.delete_suite_rows_async(" suite-manual ")

    assert result == {
        "suite_ids": ["suite-manual"],
        "suites_deleted": 1,
        "cases_deleted": 1,
        "suite_runs_deleted": 1,
        "case_runs_deleted": 1,
        "durable_jobs_deleted": 0,
    }
    deleted_tables = [
        statement.table.name for statement in executed if statement.is_delete
    ]
    assert deleted_tables == [
        "agent_eval_case_runs",
        "agent_eval_suite_runs",
        "agent_eval_cases",
        "agent_eval_suites",
    ]


@pytest.mark.asyncio
async def test_pack_removal_rejects_active_suite_run_before_deleting_artifacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Result:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self.rows = rows

        def mappings(self):
            return self

        def all(self) -> list[dict[str, object]]:
            return self.rows

    select_rows = iter(
        [
            [
                {
                    "id": "suite-harmbench",
                    "tags": [
                        "safety",
                        "pack:harmbench",
                        "pack_version:2026.07.1",
                    ],
                }
            ],
            [],
            [{"id": "suite-run-active", "status": "running"}],
        ]
    )
    executed: list[Any] = []

    class Connection:
        async def execute(self, statement):
            executed.append(statement)
            if statement.is_select:
                return Result(next(select_rows))
            return Result([])

    class Transaction:
        async def __aenter__(self) -> Connection:
            return Connection()

        async def __aexit__(self, exc_type, exc, traceback) -> bool:
            return False

    class Engine:
        def begin(self) -> Transaction:
            return Transaction()

    monkeypatch.setattr(persistence, "ensure_agent_eval_tables_async", AsyncMock())
    monkeypatch.setattr(persistence, "get_async_control_plane_engine", lambda: Engine())

    with pytest.raises(persistence.ActiveEvalSuiteRunError, match="suite-run-active"):
        await persistence.remove_imported_pack_rows_async(
            "harmbench",
            pack_version="2026.07.1",
        )

    assert not [statement for statement in executed if statement.is_delete]
