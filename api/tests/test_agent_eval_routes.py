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
