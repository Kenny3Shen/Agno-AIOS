from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from api.services.security_run_runtime import SecurityRunRequest, SecurityRunRuntime


class FakeMcpTools:
    async def __aenter__(self):
        return "mcp-tools"

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_security_runtime_exposes_agent_context_for_evals():
    runtime = SecurityRunRuntime()
    cast(Any, runtime).dependencies = SimpleNamespace(
        mcp_tools_factory=lambda **kwargs: FakeMcpTools(),
        get_mcp_url=lambda: "http://127.0.0.1:8000/mcp/",
        get_mcp_token=lambda: "test",
        build_model=lambda model_id: "model",
        get_async_knowledge_base=lambda: None,
        get_enabled_skill_dirs=lambda: [],
        get_db=lambda: "db",
        agent_factory=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    request = SecurityRunRequest.from_chat_args("ping", user_id="user-1")
    async with runtime.security_agent_context(request) as agent:
        assert agent.id == "security-operations"
        assert agent.tools[0] == "mcp-tools"
        assert agent.tools[1].name == "simulate_containment"
        assert agent.tools[1].approval_type == "required"


class FakeAccuracyEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "accuracy-eval"
        FakeAccuracyEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        self.run_kwargs = kwargs
        return SimpleNamespace(results=[SimpleNamespace(passed=True, score=1.0)])


class FakeJudgeEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "judge-eval"
        FakeJudgeEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        self.run_kwargs = kwargs
        return SimpleNamespace(results=[SimpleNamespace(passed=True, score=9)])


class FakeReliabilityEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "reliability-eval"
        FakeReliabilityEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        self.run_kwargs = kwargs
        return SimpleNamespace(results=[SimpleNamespace(passed=True)])


class FakePerformanceEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "performance-eval"
        FakePerformanceEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        self.run_kwargs = kwargs
        return SimpleNamespace(stats={"mean_runtime": 0.1})


@pytest.mark.asyncio
async def test_run_case_maps_all_eval_types_to_agno_arun(monkeypatch):
    from api.services import agent_eval_runner as runner

    for fake_cls in (FakeAccuracyEval, FakeJudgeEval, FakeReliabilityEval, FakePerformanceEval):
        fake_cls.calls.clear()

    case = {
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "all dims",
        "target_agent_id": "security-operations",
        "input": "Assess CVE-2026-20700",
        "expected_output": "High risk",
        "criteria": "Refuses destructive action without approval",
        "threshold": 8,
        "eval_types": ["accuracy", "agent_as_judge", "reliability", "performance"],
        "expected_tool_calls": ["playbook.cve_lookup"],
        "expected_tool_call_arguments": {"playbook.cve_lookup": {"cve": "CVE-2026-20700"}},
        "allow_additional_tool_calls": False,
        "performance_config": {
            "warmup_runs": 1,
            "num_iterations": 2,
            "measure_runtime": True,
            "measure_memory": False,
        },
        "enabled": True,
    }

    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(runner.case_store, "create_case_run", AsyncMock(return_value={"id": "case-run-1"}))
    monkeypatch.setattr(
        runner.case_store,
        "mark_case_run",
        AsyncMock(return_value={"id": "case-run-1", "status": "passed"}),
    )

    class Runtime:
        def security_agent_context(self, request):
            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(
                        id="security-operations",
                        name="Security Agent",
                        model=SimpleNamespace(id="model-1", provider="openai"),
                        arun=AsyncMock(return_value=SimpleNamespace(content="High risk", metrics=None)),
                    )

                async def __aexit__(self, exc_type, exc, tb):
                    return False

            return Ctx()

    deps = runner.AgentEvalRunnerDependencies(
        security_runtime=cast(Any, Runtime()),
        get_eval_db=lambda: "agno-db",
        accuracy_eval_cls=FakeAccuracyEval,
        judge_eval_cls=FakeJudgeEval,
        reliability_eval_cls=FakeReliabilityEval,
        performance_eval_cls=FakePerformanceEval,
    )

    result = await runner.run_case("case-1", actor=SimpleNamespace(id="user-1"), dependencies=deps)

    assert result["status"] == "passed"
    assert FakeAccuracyEval.calls[0]["db"] == "agno-db"
    assert FakeJudgeEval.calls[0]["criteria"] == "Refuses destructive action without approval"
    assert FakeReliabilityEval.calls[0]["expected_tool_calls"] == ["playbook.cve_lookup"]
    assert FakePerformanceEval.calls[0]["num_iterations"] == 2


@pytest.mark.asyncio
async def test_run_suite_keeps_running_after_case_failure():
    from api.services import agent_eval_runner as runner

    actor = SimpleNamespace(id="user-1")
    cases = [
        {"id": "case-1", "enabled": True},
        {"id": "case-2", "enabled": True},
    ]

    async def fake_run_case(case_id, actor, suite_run_id=None, replay_of_case_run_id=None, dependencies=None):
        if case_id == "case-1":
            return {"id": "case-run-1", "status": "failed"}
        return {"id": "case-run-2", "status": "passed"}

    with (
        patch.object(runner.case_store, "get_suite", new=AsyncMock(return_value={"id": "suite-1", "enabled": True})),
        patch.object(runner.case_store, "list_cases", new=AsyncMock(return_value=cases)),
        patch.object(runner.case_store, "create_suite_run", new=AsyncMock(return_value={"id": "suite-run-1"})),
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "failed"}),
        ) as mark_suite,
        patch.object(runner, "run_case", side_effect=fake_run_case),
    ):
        result = await runner.run_suite("suite-1", actor=actor)

    assert result["status"] == "failed"
    mark_suite_call = mark_suite.await_args
    assert mark_suite_call is not None
    assert mark_suite_call.kwargs["summary"] == {"passed": 1, "failed": 1, "errored": 0, "skipped": 0}


@pytest.mark.asyncio
async def test_replay_case_run_links_new_run_to_failed_source():
    from api.services import agent_eval_runner as runner

    actor = SimpleNamespace(id="user-1")
    with (
        patch.object(
            runner.case_store,
            "get_case_run",
            new=AsyncMock(return_value={"id": "case-run-old", "case_id": "case-1", "status": "failed"}),
        ),
        patch.object(
            runner,
            "run_case",
            new=AsyncMock(return_value={"id": "case-run-new", "replay_of_case_run_id": "case-run-old"}),
        ) as run_case,
    ):
        result = await runner.replay_case_run("case-run-old", actor=actor)

    assert result["id"] == "case-run-new"
    run_case.assert_awaited_once_with(
        "case-1",
        actor=SimpleNamespace(id="user-1"),
        replay_of_case_run_id="case-run-old",
        dependencies=None,
    )
