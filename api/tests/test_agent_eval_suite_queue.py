from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.persistence.durable_jobs import JobKind
from api.services import agent_eval_suite_queue as queue


def _actor() -> SimpleNamespace:
    return SimpleNamespace(
        id="user-1",
        email="operator@example.test",
        role="user",
        is_superuser=False,
    )


def _plan() -> dict[str, object]:
    return {
        "suite_id": "suite-1",
        "_suite": {
            "id": "suite-1",
            "name": "Snapshot suite",
            "target": {"kind": "agent", "id": "security-operations"},
            "tags": ["safety"],
        },
        "selected_tag": "smoke",
        "selected_name": None,
        "default_timeout": 120,
        "case_ids": ["case-1", "case-2"],
        # This deliberately resembles an in-memory runner plan.  The queue
        # must never serialize it into a durable job payload.
        "_cases": [
            {
                "id": "case-1",
                "suite_id": "suite-1",
                "name": "First",
                "input": "sensitive prompt",
                "expected_output": "private expected output",
                "eval_types": ["accuracy"],
            },
            {
                "id": "case-2",
                "suite_id": "suite-1",
                "name": "Second",
                "input": "another sensitive prompt",
                "expected_output": "another private expected output",
                "eval_types": ["accuracy"],
            },
        ],
    }


@pytest.mark.asyncio
async def test_enqueue_suite_run_projects_plan_and_uses_atomic_persistence() -> None:
    actor = _actor()
    summary = {"total": 2, "completed_cases": 0}
    persisted_row = {
        "id": "suite-run-1",
        "suite_id": "suite-1",
        "status": "queued",
        "started_by": "user-1",
        "error_summary": "",
        "summary": summary,
        "started_at": None,
        "completed_at": None,
    }
    with (
        patch.object(queue, "uuid4", return_value=SimpleNamespace(hex="suite-run-1")),
        patch.object(
            queue,
            "get_eval_judge_model_id",
            new=AsyncMock(return_value="judge-model-1"),
        ),
        patch.object(
            queue,
            "create_suite_run_with_case_runs_and_enqueue_job_async",
            new=AsyncMock(
                return_value=(persisted_row, SimpleNamespace(id="job-1"))
            ),
        ) as persist,
    ):
        suite_run, job_id = await queue.enqueue_suite_run(
            suite_id="suite-1",
            actor=actor,
            plan=_plan(),
            summary=summary,
        )

    assert suite_run["id"] == "suite-run-1"
    assert suite_run["status"] == "queued"
    assert job_id == "job-1"
    call = persist.await_args
    assert call is not None
    assert call.kwargs["kind"] is JobKind.EVAL_SUITE_RUN
    assert call.kwargs["idempotency_key"] == "eval-suite-run:suite-run-1"
    assert call.args[0]["id"] == "suite-run-1"
    payload = call.kwargs["payload"]
    assert payload == {"suite_run_id": "suite-run-1"}
    assert "sensitive prompt" not in str(payload)
    snapshot = call.args[0]["execution_snapshot"]
    assert "cases" not in snapshot
    assert "sensitive prompt" not in str(snapshot)
    assert snapshot["run_manifest"] == {
        "version": queue.case_store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
        "actor": {"id": "user-1", "role": "user", "is_superuser": False},
        "selected_tag": "smoke",
        "selected_name": None,
        "case_count": 2,
        "default_timeout": 120,
        "judge_model_config_id": "judge-model-1",
    }
    work_items = call.kwargs["case_run_values"]
    assert [item["case_id"] for item in work_items] == ["case-1", "case-2"]
    assert [item["work_item_index"] for item in work_items] == [0, 1]
    assert all(item["status"] == "queued" for item in work_items)
    assert "sensitive prompt" in str(work_items[0]["definition_snapshot"])


@pytest.mark.parametrize(
    "case_ids",
    [[], ["case-1", "case-1"], ["case-1", ""], "case-1"],
)
@pytest.mark.asyncio
async def test_enqueue_suite_run_rejects_invalid_frozen_case_selection(
    case_ids: object,
) -> None:
    plan = _plan()
    plan["case_ids"] = case_ids
    with patch.object(
        queue,
        "create_suite_run_with_case_runs_and_enqueue_job_async",
        new=AsyncMock(),
    ) as persist:
        with pytest.raises(ValueError):
            await queue.enqueue_suite_run(
                suite_id="suite-1",
                actor=_actor(),
                plan=plan,
                summary={},
            )

    persist.assert_not_awaited()
