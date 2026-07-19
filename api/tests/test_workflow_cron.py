from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.dialects import postgresql

from api.persistence import workflows as workflow_store
from api.persistence.durable_jobs import JobKind
from api.services.workflow_cron import next_cron_timestamp, tick_workflow_crons


def test_next_cron_timestamp_minute():
    now = datetime(2026, 1, 1, 12, 0, 10, tzinfo=timezone.utc).timestamp()
    nxt = next_cron_timestamp("* * * * *", last_run_at=0, now=now)
    assert nxt is not None
    assert nxt > now
    assert next_cron_timestamp("not-a-cron", now=now) is None


@pytest.mark.asyncio
async def test_tick_skips_when_atomic_claim_lost():
    row = {
        "id": "wf-1",
        "enabled": True,
        "owner_user_id": "owner-1",
        "triggers": {
            "cron": {"enabled": True, "expression": "* * * * *", "last_run_at": 0},
            "webhook": {"enabled": False, "secret": ""},
        },
        "published_definition": {
            "name": "x",
            "description": "",
            "steps": [
                {
                    "id": "s1",
                    "type": "step",
                    "name": "S",
                    "executor": {"kind": "agent", "ref": "safe-fallback"},
                }
            ],
        },
    }
    with (
        patch(
            "api.services.workflow_cron.workflow_store.list_workflows_for_cron",
            AsyncMock(return_value=[row]),
        ),
        patch.object(
            workflow_store,
            "claim_cron_run_and_enqueue_job",
            AsyncMock(return_value=False),
        ) as claim_and_enqueue,
    ):
        started = await tick_workflow_crons()
    assert started == 0
    claim_and_enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_tick_claims_and_queues_durable_dispatch():
    last_run_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc).timestamp()
    now = datetime(2026, 1, 1, 12, 1, 5, tzinfo=timezone.utc).timestamp()
    scheduled_at = datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc).timestamp()
    row = {
        "id": "wf-2",
        "enabled": True,
        "owner_user_id": "owner-2",
        "triggers": {
            "cron": {
                "enabled": True,
                "expression": "* * * * *",
                "last_run_at": last_run_at,
            },
            "webhook": {"enabled": False, "secret": ""},
        },
        "published_definition": {
            "name": "x",
            "description": "",
            "steps": [
                {
                    "id": "s1",
                    "type": "step",
                    "name": "S",
                    "executor": {"kind": "agent", "ref": "safe-fallback"},
                }
            ],
        },
    }
    with (
        patch(
            "api.services.workflow_cron.workflow_store.list_workflows_for_cron",
            AsyncMock(return_value=[row]),
        ),
        patch.object(
            workflow_store,
            "claim_cron_run_and_enqueue_job",
            AsyncMock(return_value=True),
        ) as claim_and_enqueue,
        patch("api.services.workflow_cron.time.time", return_value=now),
        patch(
            "api.services.workflow_cron.uuid4",
            side_effect=["run-2", "session-2"],
        ),
    ):
        started = await tick_workflow_crons()

    assert started == 1
    claim_and_enqueue.assert_awaited_once_with(
        "wf-2",
        expected_last_run_at=last_run_at,
        claim_ts=now,
        kind=JobKind.WORKFLOW_CRON_DISPATCH,
        idempotency_key=f"workflow-cron:wf-2:{scheduled_at:.6f}",
        payload={
            "workflow_id": "wf-2",
            "definition": {
                "name": "x",
                "description": "",
                "steps": [
                    {
                        "id": "s1",
                        "type": "step",
                        "name": "S",
                        "executor": {"kind": "agent", "ref": "safe-fallback"},
                        "instructions": "",
                        "requires_confirmation": False,
                        "requires_user_input": False,
                        "requires_output_review": False,
                    }
                ],
            },
            "owner_user_id": "owner-2",
            "run_id": "run-2",
            "session_id": "session-2",
            "expression": "* * * * *",
            "scheduled_at": scheduled_at,
        },
    )


class _MappingResult:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    def mappings(self) -> "_MappingResult":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._row


class _UpdateResult:
    def __init__(self, rowcount: int = 1) -> None:
        self.rowcount = rowcount


class _TransactionalConnection:
    def __init__(self, row: dict[str, Any]) -> None:
        self._row = row
        self.statements: list[object] = []

    async def execute(self, statement: object) -> _MappingResult | _UpdateResult:
        self.statements.append(statement)
        if len(self.statements) == 1:
            return _MappingResult(self._row)
        return _UpdateResult()


class _Transaction:
    def __init__(self, connection: _TransactionalConnection) -> None:
        self.connection = connection
        self.exit_exception: type[BaseException] | None = None

    async def __aenter__(self) -> _TransactionalConnection:
        return self.connection

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: object,
    ) -> bool:
        self.exit_exception = exc_type
        return False


class _TransactionalEngine:
    def __init__(self, transaction: _Transaction) -> None:
        self.transaction = transaction

    def begin(self) -> _Transaction:
        return self.transaction


def _cron_row(*, last_run_at: float = 100.0) -> dict[str, Any]:
    return {
        "id": "wf-atomic",
        "triggers": {
            "cron": {
                "enabled": True,
                "expression": "* * * * *",
                "last_run_at": last_run_at,
            }
        },
    }


@pytest.mark.asyncio
async def test_atomic_cron_enqueue_locks_row_and_uses_the_same_transaction() -> None:
    connection = _TransactionalConnection(_cron_row())
    transaction = _Transaction(connection)
    enqueue = AsyncMock()
    with (
        patch.object(workflow_store, "ensure_workflows_table_async", AsyncMock()),
        patch.object(
            workflow_store,
            "get_async_control_plane_engine",
            return_value=_TransactionalEngine(transaction),
        ),
        patch.object(
            workflow_store.durable_job_store,
            "enqueue_job_in_transaction",
            enqueue,
        ),
    ):
        claimed = await workflow_store.claim_cron_run_and_enqueue_job(
            "wf-atomic",
            expected_last_run_at=100.0,
            claim_ts=120.0,
            kind=JobKind.WORKFLOW_CRON_DISPATCH,
            payload={"workflow_id": "wf-atomic"},
            idempotency_key="workflow-cron:wf-atomic:120.000000",
        )

    assert claimed is True
    assert transaction.exit_exception is None
    enqueue.assert_awaited_once()
    enqueue_call = enqueue.await_args
    assert enqueue_call is not None
    assert enqueue_call.args[0] is connection
    assert len(connection.statements) == 2
    lock_sql = str(
        connection.statements[0].compile(dialect=postgresql.dialect())
    )
    assert "FOR UPDATE" in lock_sql
    update_params = connection.statements[1].compile(
        dialect=postgresql.dialect()
    ).params
    assert update_params["triggers"]["cron"]["last_run_at"] == 120.0


@pytest.mark.asyncio
async def test_atomic_cron_enqueue_failure_does_not_advance_last_run() -> None:
    connection = _TransactionalConnection(_cron_row())
    transaction = _Transaction(connection)
    with (
        patch.object(workflow_store, "ensure_workflows_table_async", AsyncMock()),
        patch.object(
            workflow_store,
            "get_async_control_plane_engine",
            return_value=_TransactionalEngine(transaction),
        ),
        patch.object(
            workflow_store.durable_job_store,
            "enqueue_job_in_transaction",
            AsyncMock(side_effect=RuntimeError("queue unavailable")),
        ),
        pytest.raises(RuntimeError, match="queue unavailable"),
    ):
        await workflow_store.claim_cron_run_and_enqueue_job(
            "wf-atomic",
            expected_last_run_at=100.0,
            claim_ts=120.0,
            kind=JobKind.WORKFLOW_CRON_DISPATCH,
            payload={"workflow_id": "wf-atomic"},
            idempotency_key="workflow-cron:wf-atomic:120.000000",
        )

    # The claim update is deliberately after queue insertion.  On a real
    # SQLAlchemy transaction this propagated exception triggers rollback too.
    assert transaction.exit_exception is RuntimeError
    assert len(connection.statements) == 1


@pytest.mark.asyncio
async def test_atomic_cron_enqueue_loses_stale_multi_instance_claim() -> None:
    connection = _TransactionalConnection(_cron_row(last_run_at=101.0))
    transaction = _Transaction(connection)
    enqueue = AsyncMock()
    with (
        patch.object(workflow_store, "ensure_workflows_table_async", AsyncMock()),
        patch.object(
            workflow_store,
            "get_async_control_plane_engine",
            return_value=_TransactionalEngine(transaction),
        ),
        patch.object(
            workflow_store.durable_job_store,
            "enqueue_job_in_transaction",
            enqueue,
        ),
    ):
        claimed = await workflow_store.claim_cron_run_and_enqueue_job(
            "wf-atomic",
            expected_last_run_at=100.0,
            claim_ts=120.0,
            kind=JobKind.WORKFLOW_CRON_DISPATCH,
            payload={"workflow_id": "wf-atomic"},
            idempotency_key="workflow-cron:wf-atomic:120.000000",
        )

    assert claimed is False
    assert len(connection.statements) == 1
    enqueue.assert_not_awaited()
