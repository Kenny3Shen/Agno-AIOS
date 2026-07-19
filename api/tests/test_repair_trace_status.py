from unittest.mock import AsyncMock, patch

import pytest

from api.tasks import repair_trace_status


@pytest.mark.asyncio
async def test_session_error_run_ids_reads_all_agno_pages() -> None:
    class FakeDb:
        calls: list[dict[str, object]] = []

        async def get_sessions(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["page"] == 1:
                return ([{"runs": [{"run_id": "run-1", "status": "ERROR"}]}], 201)
            return ([{"runs": [{"run_id": "run-2", "status": "FAILED"}]}], 201)

    db = FakeDb()
    with patch.object(repair_trace_status, "get_async_agno_postgres_db", return_value=db):
        run_ids = await repair_trace_status._session_error_run_ids()

    assert run_ids == {"run-1", "run-2"}
    assert [call["page"] for call in db.calls] == [1, 2]
    assert all(call["deserialize"] is False for call in db.calls)


@pytest.mark.asyncio
async def test_repair_report_includes_session_errors_missing_audit() -> None:
    traces_table = object()
    db = AsyncMock()
    db._get_table.return_value = traces_table
    with (
        patch.object(repair_trace_status, "get_async_agno_postgres_db", return_value=db),
        patch.object(
            repair_trace_status,
            "repair_failed_chat_trace_statuses_async",
            AsyncMock(return_value={"candidate_traces": 2, "updated_traces": 2}),
        ) as repair,
        patch.object(
            repair_trace_status,
            "_session_error_run_ids",
            AsyncMock(return_value={"run-audited", "run-missing"}),
        ),
        patch.object(
            repair_trace_status,
            "failed_chat_run_ids_async",
            AsyncMock(return_value={"run-audited"}),
        ),
    ):
        report = await repair_trace_status.repair_trace_statuses(apply=True)

    repair.assert_awaited_once_with(traces_table, apply=True)
    assert report["session_error_runs"] == 2
    assert report["session_errors_without_audit"] == 1
    assert report["session_errors_without_audit_sample"] == ["run-missing"]
