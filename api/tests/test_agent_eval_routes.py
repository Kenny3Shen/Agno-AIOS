from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from api.routes import agent_evals


def actor(role: str = "admin"):
    return SimpleNamespace(id="user-1", email="operator@example.com", role=role, is_superuser=False)


@pytest.mark.asyncio
async def test_create_suite_route_derives_actor_and_calls_store():
    with patch.object(
        agent_evals.case_store,
        "create_suite",
        new=AsyncMock(return_value={"id": "suite-1"}),
    ) as create_mock:
        result = await agent_evals.create_eval_suite(
            agent_evals.EvalSuiteCreateRequest(name="Security Regression", tags=["security"]),
            user=actor(),
        )

    assert result == {"id": "suite-1"}
    create_call = create_mock.await_args
    assert create_call is not None
    assert create_call.args[1].email == "operator@example.com"


@pytest.mark.asyncio
async def test_run_case_route_requires_run_permission():
    with pytest.raises(HTTPException) as exc:
        await agent_evals.require_agent_eval_run_permission(user=actor("user"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_run_case_route_calls_runner_with_actor():
    with patch.object(
        agent_evals.agent_eval_runner,
        "run_case",
        new=AsyncMock(return_value={"id": "case-run-1"}),
    ) as run_mock:
        result = await agent_evals.run_eval_case("case-1", user=actor())

    assert result == {"id": "case-run-1"}
    run_call = run_mock.await_args
    assert run_call is not None
    assert run_call.kwargs["actor"].email == "operator@example.com"


@pytest.mark.asyncio
async def test_missing_agno_eval_run_returns_404():
    with patch.object(
        agent_evals.result_service,
        "get_agno_eval_run",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await agent_evals.get_agno_eval_run("missing", user=actor())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_failure_route_enriches_agno_runs_with_case_run_ids_in_batch():
    with (
        patch.object(
            agent_evals.result_service,
            "list_failed_eval_runs",
            new=AsyncMock(
                return_value=[
                    {
                        "id": "eval-1",
                        "run_id": "eval-1",
                        "name": "CVE baseline",
                        "eval_type": "accuracy",
                        "passed": False,
                        "data": {},
                        "eval_input": {},
                    },
                    {
                        "id": "eval-2",
                        "run_id": "eval-2",
                        "name": "No local case run",
                        "eval_type": "reliability",
                        "passed": False,
                        "data": {},
                        "eval_input": {},
                    }
                ]
            ),
        ) as list_mock,
        patch.object(
            agent_evals.case_store,
            "list_case_runs_by_agno_eval_run_ids",
            new=AsyncMock(
                return_value={
                    "eval-1": {
                        "id": "case-run-1",
                        "case_id": "case-1",
                        "suite_run_id": "suite-run-1",
                    }
                }
            ),
        ) as list_case_runs_mock,
    ):
        result = await agent_evals.list_eval_failures(limit=10, user=actor())

    assert result[0]["case_run_id"] == "case-run-1"
    assert result[0]["case_id"] == "case-1"
    assert result[0]["suite_run_id"] == "suite-run-1"
    assert result[0]["data"]["case_run_id"] == "case-run-1"
    assert "case_run_id" not in result[1]
    assert list_mock.await_args is not None
    assert list_mock.await_args.kwargs["limit"] == 10
    assert list_case_runs_mock.await_args is not None
    assert list_case_runs_mock.await_args.args == (["eval-1", "eval-2"],)


@pytest.mark.asyncio
async def test_runner_value_error_maps_to_4xx():
    with patch.object(
        agent_evals.agent_eval_runner,
        "run_case",
        new=AsyncMock(side_effect=ValueError("Eval case not found: case-404")),
    ):
        with pytest.raises(HTTPException) as exc:
            await agent_evals.run_eval_case("case-404", user=actor())

    assert exc.value.status_code == 404


def test_case_request_rejects_invalid_eval_type_and_threshold():
    with pytest.raises(ValidationError):
        agent_evals.EvalCaseCreateRequest(
            suite_id="suite-1",
            name="Bad eval",
            input="check this",
            threshold=11,
            eval_types=cast(Any, ["unsupported"]),
        )
