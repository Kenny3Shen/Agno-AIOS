from unittest.mock import AsyncMock, patch

import pytest

from api.services import trace_status_service


@pytest.mark.asyncio
async def test_reconcile_trace_statuses_overlays_only_failed_chat_runs() -> None:
    traces = [
        {"trace_id": "trace-failed", "run_id": "run-failed", "status": "OK"},
        {"trace_id": "trace-ok", "run_id": "run-ok", "status": "OK"},
    ]
    with patch.object(
        trace_status_service,
        "failed_chat_run_ids_async",
        AsyncMock(return_value={"run-failed"}),
    ) as failed_ids:
        result = await trace_status_service.reconcile_trace_statuses(
            traces, actor_user_id="u1"
        )

    assert result[0]["status"] == "ERROR"
    assert result[1]["status"] == "OK"
    assert traces[0]["status"] == "OK"
    assert failed_ids.await_args is not None
    assert failed_ids.await_args.kwargs["actor_user_id"] == "u1"


@pytest.mark.asyncio
async def test_reconcile_trace_statuses_falls_back_when_audit_is_unavailable() -> None:
    traces = [{"trace_id": "trace-1", "run_id": "run-1", "status": "OK"}]
    with patch.object(
        trace_status_service,
        "failed_chat_run_ids_async",
        AsyncMock(side_effect=RuntimeError("audit unavailable")),
    ):
        result = await trace_status_service.reconcile_trace_statuses(traces)

    assert result == traces
