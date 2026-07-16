from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.services import agent_eval_case_store as store


def actor():
    return SimpleNamespace(id="user-1", email="operator@example.com", role="admin", is_superuser=False)


@pytest.mark.asyncio
async def test_create_case_rejects_unknown_eval_type():
    with pytest.raises(ValueError, match="Unsupported eval type"):
        await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "bad",
                "input": "x",
                "eval_types": ["made_up"],
            }
        )


@pytest.mark.asyncio
async def test_create_suite_derives_created_by_from_actor():
    with patch.object(
        store,
        "create_suite_row_async",
        new=AsyncMock(
            return_value={
                "id": "suite-1",
                "name": "Security Regression",
                "description": "",
                "target_agent_id": "security-operations",
                "enabled": True,
                "tags": ["security"],
                "created_by": "user-1",
                "created_at": "2026-07-06T00:00:00Z",
                "updated_at": "2026-07-06T00:00:00Z",
            }
        ),
    ) as create_mock:
        result = await store.create_suite({"name": "Security Regression", "tags": ["security"]}, actor())

    assert result["id"] == "suite-1"
    create_call = create_mock.await_args
    assert create_call is not None
    assert create_call.kwargs["values"]["created_by"] == "user-1"


@pytest.mark.asyncio
async def test_create_case_sets_defaults_and_preserves_reliability_config():
    with patch.object(
        store,
        "create_case_row_async",
        new=AsyncMock(
            return_value={
                "id": "case-1",
                "suite_id": "suite-1",
                "name": "CVE lookup calls MCP",
                "description": "",
                "target_agent_id": "security-operations",
                "input": "Lookup CVE-2026-20700",
                "expected_output": "",
                "criteria": "",
                "threshold": 7,
                "eval_types": ["reliability"],
                "expected_tool_calls": ["playbook.cve_lookup"],
                "expected_tool_call_arguments": {"playbook.cve_lookup": {"cve": "CVE-2026-20700"}},
                "allow_additional_tool_calls": False,
                "performance_config": {},
                "metadata": {},
                "enabled": True,
                "created_at": "2026-07-06T00:00:00Z",
                "updated_at": "2026-07-06T00:00:00Z",
            }
        ),
    ) as create_mock:
        result = await store.create_case(
            {
                "suite_id": "suite-1",
                "name": "CVE lookup calls MCP",
                "input": "Lookup CVE-2026-20700",
                "eval_types": ["reliability"],
                "expected_tool_calls": ["playbook.cve_lookup"],
                "expected_tool_call_arguments": {"playbook.cve_lookup": {"cve": "CVE-2026-20700"}},
            }
        )

    assert result["eval_types"] == ["reliability"]
    assert result["expected_tool_calls"] == ["playbook.cve_lookup"]
    create_call = create_mock.await_args
    assert create_call is not None
    assert create_call.kwargs["values"]["allow_additional_tool_calls"] is False


@pytest.mark.asyncio
async def test_update_suite_filters_unknown_fields():
    with patch.object(
        store,
        "update_suite_row_async",
        new=AsyncMock(
            return_value={
                "id": "suite-1",
                "name": "Updated",
                "description": "new",
                "target_agent_id": "security-operations",
                "enabled": False,
                "tags": ["nightly"],
                "created_by": "user-1",
                "created_at": "2026-07-06T00:00:00Z",
                "updated_at": "2026-07-06T01:00:00Z",
            }
        ),
    ) as update_mock:
        result = await store.update_suite("suite-1", {"name": "Updated", "enabled": False, "bogus": "x"})

    assert result is not None
    assert result["name"] == "Updated"
    update_call = update_mock.await_args
    assert update_call is not None
    assert update_call.args == ("suite-1", {"name": "Updated", "enabled": False})


@pytest.mark.asyncio
async def test_update_case_revalidates_eval_types_and_rejects_empty_patch():
    with pytest.raises(ValueError, match="Unsupported eval type"):
        await store.update_case("case-1", {"eval_types": ["unknown"]})

    with pytest.raises(ValueError, match="No supported fields to update"):
        await store.update_case("case-1", {"bogus": "x"})


@pytest.mark.asyncio
async def test_create_suite_run_derives_started_by_from_actor():
    with patch.object(
        store,
        "create_suite_run_row_async",
        new=AsyncMock(
            return_value={
                "id": "suite-run-1",
                "suite_id": "suite-1",
                "status": "queued",
                "started_by": "user-1",
                "error_summary": "",
                "summary": {},
                "started_at": "2026-07-06T00:00:00Z",
                "completed_at": None,
            }
        ),
    ) as create_mock:
        result = await store.create_suite_run("suite-1", actor())

    assert result["status"] == "queued"
    create_call = create_mock.await_args
    assert create_call is not None
    assert create_call.kwargs["values"]["started_by"] == "user-1"


@pytest.mark.asyncio
async def test_mark_case_run_filters_values_and_sets_status():
    with patch.object(
        store,
        "update_case_run_row_async",
        new=AsyncMock(
            return_value={
                "id": "case-run-1",
                "suite_run_id": "suite-run-1",
                "case_id": "case-1",
                "status": "passed",
                "agent_run_id": "agent-run-1",
                "session_id": "",
                "trace_id": "trace-1",
                "agno_eval_run_ids": ["eval-1"],
                "error_type": "",
                "error_summary": "",
                "replay_of_case_run_id": "",
                "started_at": "2026-07-06T00:00:00Z",
                "completed_at": "2026-07-06T00:01:00Z",
            }
        ),
    ) as update_mock:
        result = await store.mark_case_run(
            "case-run-1",
            "passed",
            {"agent_run_id": "agent-run-1", "trace_id": "trace-1", "agno_eval_run_ids": ["eval-1"], "bogus": "x"},
        )

    assert result is not None
    assert result["agno_eval_run_ids"] == ["eval-1"]
    update_call = update_mock.await_args
    assert update_call is not None
    sent_values = update_call.args[1]
    assert sent_values["status"] == "passed"
    assert sent_values["agent_run_id"] == "agent-run-1"
    assert "bogus" not in sent_values


@pytest.mark.asyncio
async def test_create_case_run_sets_defaults_and_replay_link():
    with patch.object(
        store,
        "create_case_run_row_async",
        new=AsyncMock(
            return_value={
                "id": "case-run-1",
                "suite_run_id": "",
                "case_id": "case-1",
                "status": "queued",
                "agent_run_id": "",
                "session_id": "",
                "trace_id": "",
                "agno_eval_run_ids": [],
                "error_type": "",
                "error_summary": "",
                "replay_of_case_run_id": "case-run-0",
                "started_at": "2026-07-06T00:00:00Z",
                "completed_at": None,
            }
        ),
    ) as create_mock:
        result = await store.create_case_run("case-1", replay_of_case_run_id="case-run-0")

    assert result["status"] == "queued"
    assert result["replay_of_case_run_id"] == "case-run-0"
    create_call = create_mock.await_args
    assert create_call is not None
    assert create_call.kwargs["values"]["suite_run_id"] == ""


@pytest.mark.asyncio
async def test_get_case_run_by_agno_eval_run_id_normalizes_row():
    with patch.object(
        store,
        "get_case_run_by_agno_eval_run_id_row_async",
        new=AsyncMock(
            return_value={
                "id": "case-run-1",
                "suite_run_id": "suite-run-1",
                "case_id": "case-1",
                "status": "failed",
                "agent_run_id": "agent-run-1",
                "session_id": "",
                "trace_id": "",
                "agno_eval_run_ids": ["eval-1"],
                "error_type": "assertion",
                "error_summary": "Missing tool call",
                "replay_of_case_run_id": "",
                "started_at": "2026-07-06T00:00:00Z",
                "completed_at": "2026-07-06T00:01:00Z",
            }
        ),
    ) as get_mock:
        result = await store.get_case_run_by_agno_eval_run_id("eval-1")

    assert result is not None
    assert result["id"] == "case-run-1"
    assert result["agno_eval_run_ids"] == ["eval-1"]
    get_call = get_mock.await_args
    assert get_call is not None
    assert get_call.args == ("eval-1",)


@pytest.mark.asyncio
async def test_list_case_runs_by_agno_eval_run_ids_maps_each_eval_id():
    with patch.object(
        store,
        "list_case_runs_by_agno_eval_run_ids_rows_async",
        new=AsyncMock(
            return_value=[
                {
                    "id": "case-run-1",
                    "suite_run_id": "suite-run-1",
                    "case_id": "case-1",
                    "status": "failed",
                    "agent_run_id": "agent-run-1",
                    "session_id": "",
                    "trace_id": "",
                    "agno_eval_run_ids": ["eval-1", "eval-2"],
                    "error_type": "assertion",
                    "error_summary": "Missing tool call",
                    "replay_of_case_run_id": "",
                    "started_at": "2026-07-06T00:00:00Z",
                    "completed_at": "2026-07-06T00:01:00Z",
                }
            ]
        ),
    ) as list_mock:
        result = await store.list_case_runs_by_agno_eval_run_ids(["eval-2", "eval-1", "eval-2", ""])

    assert result["eval-1"]["id"] == "case-run-1"
    assert result["eval-2"]["id"] == "case-run-1"
    list_call = list_mock.await_args
    assert list_call is not None
    assert list_call.args == (["eval-2", "eval-1"],)


@pytest.mark.asyncio
async def test_mark_suite_and_case_run_allow_status_only_updates():
    suite_run_row = {
        "id": "suite-run-1",
        "suite_id": "suite-1",
        "status": "completed",
        "started_by": "user-1",
        "error_summary": "",
        "summary": {"passed": 1},
        "started_at": "2026-07-06T00:00:00Z",
        "completed_at": "2026-07-06T00:01:00Z",
    }
    case_run_row = {
        "id": "case-run-1",
        "suite_run_id": "suite-run-1",
        "case_id": "case-1",
        "status": "running",
        "agent_run_id": "",
        "session_id": "",
        "trace_id": "",
        "agno_eval_run_ids": [],
        "error_type": "",
        "error_summary": "",
        "replay_of_case_run_id": "",
        "started_at": "2026-07-06T00:00:00Z",
        "completed_at": None,
    }
    with (
        patch.object(store, "update_suite_run_row_async", new=AsyncMock(return_value=suite_run_row)) as suite_update,
        patch.object(store, "update_case_run_row_async", new=AsyncMock(return_value=case_run_row)) as case_update,
    ):
        suite_result = await store.mark_suite_run("suite-run-1", "completed", {"passed": 1})
        case_result = await store.mark_case_run("case-run-1", "running", {})

    assert suite_result is not None
    assert case_result is not None
    assert suite_result["summary"] == {"passed": 1}
    assert case_result["status"] == "running"
    suite_call = suite_update.await_args
    case_call = case_update.await_args
    assert suite_call is not None
    assert case_call is not None
    assert suite_call.args[1]["status"] == "completed"
    assert case_call.args[1] == {"status": "running"}


@pytest.mark.asyncio
async def test_list_and_get_helpers_normalize_rows():
    suite_row = {
        "id": "suite-1",
        "name": "Security",
        "description": "",
        "target_agent_id": "security-operations",
        "enabled": True,
        "tags": ["security"],
        "created_by": "user-1",
        "created_at": "2026-07-06T00:00:00Z",
        "updated_at": "2026-07-06T00:00:00Z",
    }
    with (
        patch.object(store, "list_suite_rows_async", new=AsyncMock(return_value=[suite_row])) as list_mock,
        patch.object(store, "get_suite_row_async", new=AsyncMock(return_value=suite_row)) as get_mock,
    ):
        listed = await store.list_suites(enabled=True)
        fetched = await store.get_suite("suite-1")

    assert listed == [fetched]
    list_call = list_mock.await_args
    get_call = get_mock.await_args
    assert list_call is not None
    assert get_call is not None
    assert list_call.kwargs["enabled"] is True
    assert get_call.args == ("suite-1",)



@pytest.mark.asyncio
async def test_list_suite_and_case_runs_default_limit():
    with (
        patch.object(store, "list_suite_run_rows_async", new=AsyncMock(return_value=[])) as suite_list,
        patch.object(store, "list_case_run_rows_async", new=AsyncMock(return_value=[])) as case_list,
    ):
        await store.list_suite_runs(suite_id="s1", status="completed")
        await store.list_case_runs(case_id="c1", status="failed")

    assert suite_list.await_args is not None
    assert suite_list.await_args.kwargs["limit"] == 100
    assert case_list.await_args is not None
    assert case_list.await_args.kwargs["limit"] == 100
