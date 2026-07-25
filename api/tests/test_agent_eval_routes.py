from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from pydantic import ValidationError

from api.routes import agent_evals
from api.tests.route_fakes import route_dependency


def actor(role: str = "admin"):
    return SimpleNamespace(
        id="user-1", email="operator@example.com", role=role, is_superuser=False
    )


def route(endpoint_name: str) -> APIRoute:
    for item in agent_evals.router.routes:
        if (
            isinstance(item, APIRoute)
            and getattr(item.endpoint, "__name__", "") == endpoint_name
        ):
            return item
    raise AssertionError(f"missing route {endpoint_name}")


@pytest.mark.asyncio
async def test_create_suite_route_derives_actor_and_calls_store():
    with patch.object(
        agent_evals.case_store,
        "create_suite",
        new=AsyncMock(return_value={"id": "suite-1"}),
    ) as create_mock:
        result = await agent_evals.create_eval_suite(
            agent_evals.EvalSuiteCreateRequest(
                name="Security Regression",
                target={"kind": "agent", "id": "security-operations"},
                tags=["security"],
            ),
            user=actor(),
        )

    assert result == {"id": "suite-1"}
    create_call = create_mock.await_args
    assert create_call is not None
    assert create_call.args[1].email == "operator@example.com"


@pytest.mark.asyncio
async def test_list_eval_packs_returns_catalog_envelope():
    with patch.object(
        agent_evals.pack_service,
        "list_pack_catalog",
        return_value=[
            {
                "id": "fixture-synthetic",
                "title": "Synthetic",
                "status": "ready",
                "importable": True,
                "has_local_cases": True,
            }
        ],
    ) as catalog_mock:
        result = await agent_evals.list_eval_packs(ready_only=True, user=actor())

    assert result["data"][0]["id"] == "fixture-synthetic"
    assert result["meta"]["total_count"] == 1
    catalog_mock.assert_called_once_with(ready_only=True)


@pytest.mark.asyncio
async def test_list_eval_execution_targets_returns_availability_catalog():
    targets = [
        {
            "kind": "agent",
            "id": "security-operations",
            "name": "Security Operations",
            "available": True,
        },
        {
            "kind": "team",
            "id": "research-analysis-team",
            "name": "Research Analysis Team",
            "available": False,
            "unavailable_reason": "TAIS_ENABLE_AGNO_TEAM=1 is required",
        },
    ]
    with patch.object(
        agent_evals,
        "list_eval_targets",
        return_value=targets,
    ) as targets_mock:
        result = await agent_evals.list_eval_execution_targets(user=actor())

    assert result["data"] == targets
    assert result["meta"]["total_count"] == 2
    targets_mock.assert_called_once_with()


@pytest.mark.asyncio
async def test_list_eval_cases_uses_the_bounded_browser_page_contract():
    expected = {
        "data": [{"id": "case-51", "suite_id": "suite-1"}],
        "meta": {"page": 2, "limit": 50, "total_count": 501},
    }
    with patch.object(
        agent_evals.case_store,
        "list_cases_page",
        new=AsyncMock(return_value=expected),
    ) as list_mock:
        result = await agent_evals.list_eval_cases(
            suite_id="suite-1",
            page=2,
            limit=50,
            user=actor(),
        )

    assert result == expected
    list_mock.assert_awaited_once_with(
        suite_id="suite-1",
        enabled=None,
        tag=None,
        name=None,
        page=2,
        limit=50,
    )


def test_import_eval_pack_route_requires_write_permission():
    with pytest.raises(HTTPException) as exc:
        route_dependency(agent_evals.router, "import_eval_pack")(user=actor("user"))
    assert exc.value.status_code == 403


def test_remove_eval_pack_route_requires_delete_permission():
    with pytest.raises(HTTPException) as exc:
        route_dependency(agent_evals.router, "remove_eval_pack")(user=actor("user"))
    assert exc.value.status_code == 403


def test_delete_eval_suite_route_requires_delete_permission():
    with pytest.raises(HTTPException) as exc:
        route_dependency(agent_evals.router, "delete_eval_suite")(user=actor("user"))
    assert exc.value.status_code == 403


def test_delete_eval_case_route_requires_delete_permission():
    with pytest.raises(HTTPException) as exc:
        route_dependency(agent_evals.router, "delete_eval_case")(user=actor("user"))
    assert exc.value.status_code == 403


def test_export_eval_suite_report_requires_write_permission():
    with pytest.raises(HTTPException) as exc:
        route_dependency(agent_evals.router, "export_eval_suite_run_report")(
            user=actor("user")
        )
    assert exc.value.status_code == 403


def test_imported_pack_mutation_conflict_is_reported_as_409():
    error = agent_evals._http_from_value_error(
        ValueError("Imported eval pack suites are immutable")
    )

    assert error.status_code == 409


def test_case_request_validates_structured_additional_guidelines():
    request = agent_evals.EvalCaseCreateRequest(
        suite_id="suite-1",
        name="Guided Case",
        input="prompt",
        eval_types=["agent_as_judge"],
        additional_guidelines=["Use the policy's strictest interpretation."],
    )
    assert request.additional_guidelines == [
        "Use the policy's strictest interpretation."
    ]

    with pytest.raises(ValidationError):
        agent_evals.EvalCaseCreateRequest(
            suite_id="suite-1",
            name="Too many guidance rows",
            input="prompt",
            eval_types=["agent_as_judge"],
            additional_guidelines=["x"] * 21,
        )


@pytest.mark.asyncio
async def test_import_eval_pack_route_calls_service_and_audits():
    import_result = {
        "pack_id": "fixture-synthetic",
        "pack_version": "2026.07.1",
        "suite_id": "suite-1",
        "suite_name": "safety-L1-fixture-synthetic@2026.07.1",
        "created_suite": True,
        "cases_total": 4,
        "cases_created": 4,
        "cases_updated": 0,
        "cases_in_suite": 4,
    }
    with (
        patch.object(
            agent_evals.pack_service,
            "import_pack",
            new=AsyncMock(return_value=import_result),
        ) as import_mock,
        patch.object(
            agent_evals,
            "record_audit_event_async",
            new=AsyncMock(),
        ) as audit_mock,
    ):
        result = await agent_evals.import_eval_pack(
            agent_evals.EvalPackImportRequest(pack_id="fixture-synthetic"),
            user=actor(),
        )

    assert result["suite_id"] == "suite-1"
    import_call = import_mock.await_args
    assert import_call is not None
    assert import_call.args[0] == "fixture-synthetic"
    assert import_call.kwargs["require_ready"] is True
    audit_mock.assert_awaited_once()
    audit_call = audit_mock.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "evals.pack_import"


@pytest.mark.asyncio
async def test_remove_eval_pack_route_calls_service_and_audits():
    remove_result = {
        "pack_id": "fixture-synthetic",
        "pack_version": "2026.07.1",
        "suite_ids": ["suite-1"],
        "suites_deleted": 1,
        "cases_deleted": 4,
        "suite_runs_deleted": 2,
        "case_runs_deleted": 8,
    }
    with (
        patch.object(
            agent_evals.pack_service,
            "remove_imported_pack",
            new=AsyncMock(return_value=remove_result),
        ) as remove_mock,
        patch.object(
            agent_evals,
            "record_audit_event_async",
            new=AsyncMock(),
        ) as audit_mock,
    ):
        result = await agent_evals.remove_eval_pack(
            " fixture-synthetic ", pack_version=" 2026.07.1 ", user=actor()
        )

    assert result == remove_result
    remove_mock.assert_awaited_once_with(
        "fixture-synthetic",
        pack_version="2026.07.1",
    )
    audit_mock.assert_awaited_once()
    audit_call = audit_mock.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "evals.pack_remove"
    assert audit_call.kwargs["metadata"]["pack_version"] == "2026.07.1"
    assert audit_call.kwargs["metadata"]["case_runs_deleted"] == 8


@pytest.mark.asyncio
async def test_delete_eval_suite_route_cascades_and_audits():
    delete_result = {
        "suite_ids": ["suite-1"],
        "suites_deleted": 1,
        "cases_deleted": 4,
        "suite_runs_deleted": 2,
        "case_runs_deleted": 8,
    }
    with (
        patch.object(
            agent_evals.case_store,
            "delete_suite",
            new=AsyncMock(return_value=delete_result),
        ) as delete_mock,
        patch.object(
            agent_evals,
            "record_audit_event_async",
            new=AsyncMock(),
        ) as audit_mock,
    ):
        result = await agent_evals.delete_eval_suite("suite-1", user=actor())

    assert result == delete_result
    delete_mock.assert_awaited_once_with("suite-1")
    audit_mock.assert_awaited_once()
    audit_call = audit_mock.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "evals.suite_delete"
    assert audit_call.kwargs["metadata"]["case_runs_deleted"] == 8


@pytest.mark.asyncio
async def test_delete_eval_case_route_retains_historical_result_artifacts():
    with (
        patch.object(
            agent_evals.case_store,
            "delete_case",
            new=AsyncMock(return_value={"id": "case-1", "suite_id": "suite-1"}),
        ) as delete_mock,
        patch.object(
            agent_evals,
            "record_audit_event_async",
            new=AsyncMock(),
        ) as audit_mock,
    ):
        result = await agent_evals.delete_eval_case("case-1", user=actor())

    assert result == {
        "case_id": "case-1",
        "suite_id": "suite-1",
        "run_history_retained": True,
    }
    delete_mock.assert_awaited_once_with("case-1")
    audit_mock.assert_awaited_once()
    audit_call = audit_mock.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "evals.case_delete"
    assert audit_call.kwargs["metadata"]["run_history_retained"] is True


def test_run_case_route_requires_run_permission():
    with pytest.raises(HTTPException) as exc:
        route_dependency(agent_evals.router, "run_eval_case")(user=actor("user"))
    assert exc.value.status_code == 403


def test_run_suite_route_requires_write_permission():
    with pytest.raises(HTTPException) as exc:
        route_dependency(agent_evals.router, "run_eval_suite")(user=actor("user"))
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
async def test_run_suite_route_prepares_queued_run_and_enqueues_durable_job():
    user = actor()
    plan = {
        "suite_id": "suite-1",
        "selected_tag": "smoke",
        "selected_name": None,
        "default_timeout": 120,
        "case_ids": ["case-1", "case-2"],
    }
    initial_summary = {
        "selected_cases": 2,
        "completed_cases": 0,
        "total": 2,
        "cases": [],
    }
    suite_run = {
        "id": "suite-run-1",
        "suite_id": "suite-1",
        "status": "queued",
        "summary": initial_summary,
    }

    with (
        patch.object(
            agent_evals.agent_eval_runner,
            "prepare_suite_run",
            new=AsyncMock(return_value=plan),
        ) as prepare_mock,
        patch.object(
            agent_evals.agent_eval_runner,
            "initial_suite_run_summary",
            return_value=initial_summary,
        ) as summary_mock,
        patch.object(
            agent_evals,
            "enqueue_suite_run",
            new=AsyncMock(return_value=(suite_run, "job-1")),
        ) as enqueue_mock,
    ):
        result = await agent_evals.run_eval_suite(
            "suite-1",
            body=agent_evals.EvalSuiteRunRequest(tag=" smoke "),
            user=user,
        )

    assert result == {**suite_run, "job_id": "job-1"}
    prepare_mock.assert_awaited_once_with(
        "suite-1",
        tag=" smoke ",
        name=None,
        default_timeout=120,
    )
    summary_mock.assert_called_once_with(plan)
    enqueue_mock.assert_awaited_once_with(
        suite_id="suite-1",
        actor=user,
        plan=plan,
        summary=initial_summary,
    )
    assert route("run_eval_suite").status_code == 202


@pytest.mark.asyncio
async def test_run_suite_route_rejects_an_empty_prepared_selection():
    with (
        patch.object(
            agent_evals.agent_eval_runner,
            "prepare_suite_run",
            new=AsyncMock(
                return_value={
                    "suite_id": "suite-1",
                    "case_ids": [],
                    "selected_tag": None,
                    "selected_name": None,
                    "default_timeout": 120,
                }
            ),
        ),
        patch.object(
            agent_evals,
            "enqueue_suite_run",
            new=AsyncMock(
                side_effect=ValueError("Eval suite run requires at least one selected case")
            ),
        ) as enqueue_mock,
    ):
        with pytest.raises(HTTPException) as exc:
            await agent_evals.run_eval_suite("suite-1", user=actor())

    assert exc.value.status_code == 422
    assert "at least one selected case" in str(exc.value.detail)
    enqueue_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_suite_route_surfaces_atomic_enqueue_failure():
    plan = {
        "suite_id": "suite-1",
        "selected_tag": None,
        "selected_name": "Smoke check",
        "default_timeout": 120,
        "case_ids": ["case-1"],
    }
    initial_summary = {"selected_cases": 1, "completed_cases": 0, "cases": []}
    user = actor()
    with (
        patch.object(
            agent_evals.agent_eval_runner,
            "prepare_suite_run",
            new=AsyncMock(return_value=plan),
        ),
        patch.object(
            agent_evals.agent_eval_runner,
            "initial_suite_run_summary",
            return_value=initial_summary,
        ),
        patch.object(
            agent_evals,
            "enqueue_suite_run",
            new=AsyncMock(side_effect=RuntimeError("queue unavailable")),
        ) as enqueue_mock,
    ):
        with pytest.raises(HTTPException) as exc:
            await agent_evals.run_eval_suite(
                "suite-1",
                body=agent_evals.EvalSuiteRunRequest(name="Smoke check"),
                user=user,
            )

    assert exc.value.status_code == 500
    enqueue_mock.assert_awaited_once_with(
        suite_id="suite-1",
        actor=user,
        plan=plan,
        summary=initial_summary,
    )


@pytest.mark.asyncio
async def test_run_suite_route_rejects_concurrent_active_run() -> None:
    plan = {
        "suite_id": "suite-1",
        "selected_tag": None,
        "selected_name": None,
        "default_timeout": 120,
        "case_ids": ["case-1"],
    }
    with (
        patch.object(
            agent_evals.agent_eval_runner,
            "prepare_suite_run",
            new=AsyncMock(return_value=plan),
        ),
        patch.object(
            agent_evals.agent_eval_runner,
            "initial_suite_run_summary",
            return_value={"total": 1, "cases": []},
        ),
        patch.object(
            agent_evals,
            "enqueue_suite_run",
            new=AsyncMock(
                side_effect=agent_evals.ActiveEvalSuiteRunError(
                    "Eval suite already has an active run: suite-run-1"
                )
            ),
        ),
    ):
        with pytest.raises(HTTPException) as exc:
            await agent_evals.run_eval_suite("suite-1", user=actor())

    assert exc.value.status_code == 409
    assert "active run" in str(exc.value.detail)


def test_cancel_suite_run_route_requires_write_permission():
    with pytest.raises(HTTPException) as exc:
        route_dependency(agent_evals.router, "cancel_eval_suite_run")(user=actor("user"))
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_cancel_suite_run_route_requests_cancellation_and_audits():
    user = actor()
    suite_run = {
        "id": "suite-run-1",
        "suite_id": "suite-1",
        "status": "cancelling",
        "summary": {"cancel_requested": True},
    }
    with (
        patch.object(
            agent_evals.case_store,
            "request_suite_run_cancel",
            new=AsyncMock(return_value=suite_run),
        ) as cancel_mock,
        patch.object(
            agent_evals,
            "record_audit_event_async",
            new=AsyncMock(),
        ) as audit_mock,
    ):
        result = await agent_evals.cancel_eval_suite_run("suite-run-1", user=user)

    assert result == suite_run
    cancel_mock.assert_awaited_once_with("suite-run-1")
    audit_mock.assert_awaited_once_with(
        user,
        action="evals.suite_run_cancel",
        resource_type="eval_suite_run",
        resource_id="suite-run-1",
        metadata={
            "suite_id": "suite-1",
            "status": "cancelling",
            "cancel_requested": True,
        },
    )
    assert route("cancel_eval_suite_run").status_code == 202


@pytest.mark.asyncio
async def test_cancel_suite_run_route_returns_404_for_unknown_run():
    with patch.object(
        agent_evals.case_store,
        "request_suite_run_cancel",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await agent_evals.cancel_eval_suite_run("missing", user=actor())

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_eval_cases_forwards_tag_and_name_selectors():
    payload = {"data": [], "meta": {"total_count": 0}}
    with patch.object(
        agent_evals.case_store,
        "list_cases_page",
        new=AsyncMock(return_value=payload),
    ) as list_mock:
        result = await agent_evals.list_eval_cases(
            suite_id="suite-1",
            enabled=True,
            tag="smoke",
            name="Smoke check",
            user=actor(),
        )

    assert result is payload
    list_mock.assert_awaited_once_with(
        suite_id="suite-1",
        enabled=True,
        tag="smoke",
        name="Smoke check",
        page=1,
        limit=100,
    )


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
                        "name": "CVE baseline",
                        "eval_type": "accuracy",
                        "passed": False,
                        "eval_data": {},
                        "eval_input": {},
                    },
                    {
                        "id": "eval-2",
                        "name": "No local case run",
                        "eval_type": "reliability",
                        "passed": False,
                        "eval_data": {},
                        "eval_input": {},
                    },
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

    assert isinstance(result, dict)
    assert "data" in result and "meta" in result
    items = result["data"]
    assert result["meta"]["page"] == 1
    assert result["meta"]["limit"] == 10
    assert result["meta"]["total_count"] == 2
    assert items[0]["case_run_id"] == "case-run-1"
    assert items[0]["case_id"] == "case-1"
    assert items[0]["suite_run_id"] == "suite-run-1"
    assert items[0]["eval_data"]["case_run_id"] == "case-run-1"
    assert "case_run_id" not in items[1]
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


def test_case_request_rejects_invalid_eval_type_threshold_and_judge_mode():
    with pytest.raises(ValidationError):
        agent_evals.EvalCaseCreateRequest(
            suite_id="suite-1",
            name="Missing checks",
            input="check this",
        )
    with pytest.raises(ValidationError):
        agent_evals.EvalCaseCreateRequest(
            suite_id="suite-1",
            name="Empty checks",
            input="check this",
            eval_types=[],
        )
    with pytest.raises(ValidationError):
        agent_evals.EvalCaseCreateRequest(
            suite_id="suite-1",
            name="Bad eval",
            input="check this",
            threshold=11,
            eval_types=cast(Any, ["unsupported"]),
        )
    with pytest.raises(ValidationError):
        agent_evals.EvalCaseCreateRequest(
            suite_id="suite-1",
            name="Bad judge mode",
            input="check this",
            judge_mode=cast(Any, "ordinal"),
        )


def test_case_request_accepts_tags() -> None:
    request = agent_evals.EvalCaseCreateRequest(
        suite_id="suite-1",
        name="Smoke check",
        input="check",
        eval_types=["agent_as_judge"],
        tags=["smoke", "release"],
    )

    assert request.tags == ["smoke", "release"]
    assert request.judge_mode == "binary"
    assert request.allow_additional_tool_calls is True


def test_case_request_uses_a_complete_bounded_performance_contract() -> None:
    request = agent_evals.EvalCaseCreateRequest(
        suite_id="suite-1",
        name="Performance smoke",
        input="check",
        eval_types=["performance"],
        performance_config={"num_iterations": 5},
    )

    assert request.performance_config.model_dump() == {
        "warmup_runs": 1,
        "num_iterations": 5,
        "measure_runtime": True,
        "measure_memory": False,
    }

    for invalid in (
        {"num_iterations": 101},
        {"unknown": True},
        {"measure_runtime": False, "measure_memory": False},
        {"warmup_runs": True},
        {"num_iterations": "3"},
        {"measure_runtime": "true"},
        {"measure_memory": 1},
    ):
        with pytest.raises(ValidationError):
            agent_evals.EvalCaseCreateRequest(
                suite_id="suite-1",
                name="Invalid performance smoke",
                input="check",
                eval_types=["performance"],
                performance_config=cast(Any, invalid),
            )


@pytest.mark.asyncio
async def test_list_eval_suite_and_case_runs_forwards_pagination():
    suite_payload = {
        "data": [],
        "meta": {
            "page": 2,
            "limit": 10,
            "total_count": 0,
            "total_pages": 0,
            "search_time_ms": 0.0,
        },
    }
    case_payload = {
        "data": [],
        "meta": {
            "page": 1,
            "limit": 25,
            "total_count": 0,
            "total_pages": 0,
            "search_time_ms": 0.0,
        },
    }
    with (
        patch.object(
            agent_evals.case_store,
            "list_suite_runs",
            new=AsyncMock(return_value=suite_payload),
        ) as suite_mock,
        patch.object(
            agent_evals.case_store,
            "list_case_runs",
            new=AsyncMock(return_value=case_payload),
        ) as case_mock,
    ):
        suite = await agent_evals.list_eval_suite_runs(
            suite_id="s1",
            status="completed",
            page=2,
            limit=10,
            user=actor(),
        )
        case = await agent_evals.list_eval_case_runs(
            case_id="c1",
            status="failed",
            page=1,
            limit=25,
            user=actor(),
        )

    assert suite is suite_payload
    assert case is case_payload
    assert suite_mock.await_args is not None
    assert suite_mock.await_args.kwargs == {
        "suite_id": "s1",
        "status": "completed",
        "page": 2,
        "limit": 10,
    }
    assert case_mock.await_args is not None
    assert case_mock.await_args.kwargs == {
        "case_id": "c1",
        "status": "failed",
        "page": 1,
        "limit": 25,
    }


@pytest.mark.asyncio
async def test_list_suite_run_case_runs_404_when_suite_run_missing():
    with patch.object(
        agent_evals.case_store,
        "get_suite_run",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await agent_evals.list_eval_suite_run_case_runs(
                suite_run_id="missing",
                status=None,
                page=1,
                limit=50,
                user=actor(),
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_list_suite_run_case_runs_filters_by_suite_run_id():
    payload = {
        "data": [
            {
                "id": "cr-1",
                "suite_run_id": "sr-1",
                "case_id": "case-1",
                "status": "failed",
                "session_id": "eval_cr-1",
            }
        ],
        "meta": {
            "page": 1,
            "limit": 50,
            "total_count": 1,
            "total_pages": 1,
            "search_time_ms": 0.0,
        },
    }
    with (
        patch.object(
            agent_evals.case_store,
            "get_suite_run",
            new=AsyncMock(
                return_value={"id": "sr-1", "suite_id": "s1", "status": "failed"}
            ),
        ) as get_mock,
        patch.object(
            agent_evals.case_store,
            "list_case_runs",
            new=AsyncMock(return_value=payload),
        ) as list_mock,
    ):
        result = await agent_evals.list_eval_suite_run_case_runs(
            suite_run_id="sr-1",
            status="failed",
            page=1,
            limit=50,
            user=actor(),
        )

    assert result is payload
    get_mock.assert_awaited_once_with("sr-1")
    assert list_mock.await_args is not None
    assert list_mock.await_args.kwargs == {
        "suite_run_id": "sr-1",
        "status": "failed",
        "page": 1,
        "limit": 50,
    }


@pytest.mark.asyncio
async def test_export_eval_suite_report_returns_report_and_audits() -> None:
    suite_run = {
        "id": "sr-1",
        "suite_id": "suite-1",
        "status": "passed",
        "summary": {"passed": 1, "failed": 0, "cases": []},
    }
    report = {
        "format": "tais.eval-suite-report.v1",
        "suite_run": {"id": "sr-1", "suite_id": "suite-1", "status": "passed"},
        "summary": {"total": 1, "passed": 1, "failed": 0, "status": "PASS"},
        "cases": [],
        "case_results_available": True,
        "privacy": {"inputs_included": False, "outputs_included": False},
    }
    with (
        patch.object(
            agent_evals.case_store,
            "get_suite_run",
            new=AsyncMock(return_value=suite_run),
        ) as get_mock,
        patch.object(
            agent_evals.case_store,
            "list_suite_run_case_result_lites",
            new=AsyncMock(return_value=[]),
        ) as case_results_mock,
        patch.object(
            agent_evals.report_service,
            "build_suite_run_report",
            return_value=report,
        ) as build_mock,
        patch.object(
            agent_evals,
            "record_audit_event_async",
            new=AsyncMock(),
        ) as audit_mock,
    ):
        result = await agent_evals.export_eval_suite_run_report("sr-1", user=actor())

    assert result == report
    get_mock.assert_awaited_once_with("sr-1")
    case_results_mock.assert_awaited_once_with("sr-1")
    build_mock.assert_called_once_with(suite_run, case_results=[])
    audit_mock.assert_awaited_once()
    audit_call = audit_mock.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "evals.suite_report_export"
    assert audit_call.kwargs["resource_id"] == "sr-1"
    assert audit_call.kwargs["metadata"] == {
        "suite_id": "suite-1",
        "format": "tais.eval-suite-report.v1",
        "case_count": 0,
        "case_results_available": True,
        "raw_inputs_included": False,
        "raw_outputs_included": False,
    }


@pytest.mark.asyncio
async def test_export_eval_suite_report_returns_404_for_missing_run() -> None:
    with patch.object(
        agent_evals.case_store,
        "get_suite_run",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(HTTPException) as exc:
            await agent_evals.export_eval_suite_run_report("missing", user=actor())

    assert exc.value.status_code == 404
