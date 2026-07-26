import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest

from api.services.chat_settings_service import ChatSettings
from api.services.security_run_runtime import SecurityRunRequest, SecurityRunRuntime


def _suite_stub(**overrides: Any) -> dict[str, Any]:
    """Return the strict Suite contract required by the Eval runner."""
    return {
        "id": "suite-1",
        "enabled": True,
        "target": {"kind": "agent", "id": "security-operations"},
        **overrides,
    }


def _case_stub(case_id: str, **overrides: Any) -> dict[str, Any]:
    """Return a complete persisted Case suitable for snapshot-backed Suites."""
    return {
        "id": case_id,
        "suite_id": "suite-1",
        "name": case_id,
        "description": "",
        "input": "snapshot probe",
        "expected_output": "snapshot result",
        "criteria": "",
        "judge_mode": "binary",
        "additional_guidelines": [],
        "threshold": 7,
        "eval_types": ["accuracy"],
        "expected_tool_calls": [],
        "expected_tool_call_arguments": {},
        "allow_additional_tool_calls": True,
        "performance_config": {
            "warmup_runs": 1,
            "num_iterations": 3,
            "measure_runtime": True,
            "measure_memory": False,
        },
        "timeout_seconds": None,
        "metadata": {},
        "tags": [],
        "enabled": True,
        **overrides,
    }


def _execution_snapshot(
    *cases: dict[str, Any],
    tags: list[str] | None = None,
    actor_id: str = "user-1",
    actor_role: str = "user",
    actor_is_superuser: bool = False,
    selected_tag: str | None = None,
    selected_name: str | None = None,
    default_timeout: int = 120,
    judge_model_config_id: str = "",
) -> dict[str, Any]:
    from api.services import agent_eval_case_store as case_store

    return case_store.build_suite_run_execution_snapshot(
        _suite_stub(name="Frozen suite", tags=tags or []),
        run_manifest={
            "version": case_store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
            "actor": {
                "id": actor_id,
                "role": actor_role,
                "is_superuser": actor_is_superuser,
            },
            "selected_tag": selected_tag,
            "selected_name": selected_name,
            "case_count": len(cases),
            "default_timeout": default_timeout,
            "judge_model_config_id": judge_model_config_id,
        },
    )


def _case_work_items(
    execution_snapshot: dict[str, Any],
    *cases: dict[str, Any],
    suite_run_id: str = "suite-run-1",
) -> list[dict[str, Any]]:
    """Build the immutable CaseRun work items used by durable Suite tests."""
    from api.services import agent_eval_case_store as case_store

    return case_store.build_suite_run_case_work_items(
        suite_run_id,
        execution_snapshot,
        list(cases),
    )


def _claimed_suite_run(
    execution_snapshot: dict[str, Any],
    *,
    actor: Any,
    suite_run_id: str = "suite-run-1",
    status: str = "running",
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the private SuiteRun state handed to the fenced worker."""
    return {
        "id": suite_run_id,
        "suite_id": execution_snapshot["suite_id"],
        "started_by": str(getattr(actor, "id", "") or ""),
        "status": status,
        "summary": dict(summary or {}),
    }


async def _execute_claimed_suite(
    runner: Any,
    *cases: dict[str, Any],
    actor: Any | None = None,
    execution_snapshot: dict[str, Any] | None = None,
    case_work_items: list[dict[str, Any]] | None = None,
    suite_run: dict[str, Any] | None = None,
    suite_run_id: str = "suite-run-1",
    status: str = "running",
    summary: dict[str, Any] | None = None,
    execution_lease: Any | None = None,
    dependencies: Any | None = None,
    concurrency: int | None = None,
    cancellation_event: asyncio.Event | None = None,
    abort_event: asyncio.Event | None = None,
) -> dict[str, Any]:
    """Run the single durable Suite executor used in production.

    Tests intentionally construct the same frozen snapshot and pre-created
    work items as the atomic queue producer.  Keeping this helper here makes
    it impossible for a unit test to accidentally recreate the removed
    synchronous Suite execution path.
    """
    resolved_actor = actor or SimpleNamespace(
        id="user-1", role="user", is_superuser=False
    )
    snapshot = execution_snapshot or _execution_snapshot(
        *cases,
        actor_id=str(getattr(resolved_actor, "id", "") or ""),
        actor_role=str(getattr(resolved_actor, "role", "user") or "user"),
        actor_is_superuser=bool(getattr(resolved_actor, "is_superuser", False)),
    )
    work_items = case_work_items or _case_work_items(
        snapshot,
        *cases,
        suite_run_id=suite_run_id,
    )
    lease = execution_lease or runner.case_store.SuiteRunExecutionLease(
        job_id="job-1",
        lease_epoch=1,
    )
    run = suite_run or _claimed_suite_run(
        snapshot,
        actor=resolved_actor,
        suite_run_id=suite_run_id,
        status=status,
        summary=summary,
    )
    return await runner._execute_claimed_suite_run(
        suite_run=run,
        actor=resolved_actor,
        execution_snapshot=snapshot,
        case_work_items=work_items,
        execution_lease=lease,
        dependencies=dependencies,
        concurrency=concurrency,
        cancellation_event=cancellation_event,
        abort_event=abort_event,
    )


def test_frozen_suite_work_items_reject_truncation_and_manifest_drift() -> None:
    """A worker must never silently accept a partial or mixed work-item set."""
    from api.services import agent_eval_case_store as case_store
    from api.services import agent_eval_runner as runner

    first = _case_stub("case-1")
    second = _case_stub("case-2")
    snapshot = _execution_snapshot(first, second)
    work_items = _case_work_items(snapshot, first, second)
    manifest = case_store.suite_run_execution_manifest(snapshot)
    target = runner._snapshot_target(snapshot["target"])

    with pytest.raises(ValueError, match="count does not match"):
        runner._frozen_suite_case_work_items(
            [work_items[0]],
            suite_id="suite-1",
            target=target,
            manifest=manifest,
        )

    tampered = {
        **work_items[0],
        "execution_provenance": {
            **work_items[0]["execution_provenance"],
            "default_timeout_seconds": 99,
        },
    }
    with pytest.raises(ValueError, match="does not match its execution manifest"):
        runner._frozen_suite_case_work_items(
            [tampered, work_items[1]],
            suite_id="suite-1",
            target=target,
            manifest=manifest,
        )


@pytest.fixture(autouse=True)
def _default_strict_eval_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit Case fixtures execute against one explicit Suite target."""
    from api.services import agent_eval_runner as runner

    monkeypatch.setattr(
        runner.case_store,
        "get_suite",
        AsyncMock(
            return_value={
                "id": "suite-1",
                "enabled": True,
                "target": {"kind": "agent", "id": "security-operations"},
            }
        ),
    )


class FakeMcpTools:
    async def __aenter__(self):
        return "mcp-tools"

    async def __aexit__(self, *_args):
        return False


@pytest.mark.asyncio
async def test_security_runtime_exposes_agent_context_for_evals():
    runtime = SecurityRunRuntime()
    cast(Any, runtime).dependencies = SimpleNamespace(
        mcp_tools_factory=lambda **kwargs: FakeMcpTools(),
        get_mcp_url=lambda: "http://127.0.0.1:8000/mcp/",
        issue_mcp_delegation_token=lambda _user_id: "test",
        build_model=lambda *args, **kwargs: "model",
        get_async_knowledge_base=lambda: None,
        effective_skill_dirs_for_actor=lambda _actor, _skill_names: [],
        effective_mcp_server_names_for_actor=lambda _actor: [],
        get_db=lambda: "db",
        agent_factory=lambda **kwargs: SimpleNamespace(**kwargs),
    )

    request = SecurityRunRequest.from_chat_args(
        "ping",
        user_id="user-1",
        infer_skills=False,
        memory_enabled=False,
    )
    with patch(
        "api.services.security_run_runtime.get_chat_settings_async",
        new=AsyncMock(return_value=ChatSettings()),
    ):
        async with runtime.security_agent_context(request) as agent:
            assert agent.id == "security-operations"
            assert agent.tools == ["mcp-tools"]


class FakeAccuracyEval:
    calls = []
    outputs = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "accuracy-eval"
        FakeAccuracyEval.calls.append(kwargs)

    async def arun_with_output(self, *, output, **kwargs):
        self.run_kwargs = {"output": output, **kwargs}
        FakeAccuracyEval.outputs.append(output)
        return SimpleNamespace(
            avg_score=9.0,
            results=[SimpleNamespace(score=9, reason="Matches expected output")],
        )


class FakeJudgeEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "judge-eval"
        FakeJudgeEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        self.run_kwargs = kwargs
        return SimpleNamespace(
            results=[SimpleNamespace(passed=True, score=9, reason="Meets the rubric")]
        )


class FakeReliabilityEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "reliability-eval"
        FakeReliabilityEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        self.run_kwargs = kwargs
        return SimpleNamespace(eval_status="PASSED")


class FakePerformanceEval:
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "performance-eval"
        FakePerformanceEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        self.run_kwargs = kwargs
        return SimpleNamespace(
            avg_run_time=0.1,
            median_run_time=0.09,
            p95_run_time=0.15,
            avg_memory_usage=1.5,
            median_memory_usage=1.4,
            p95_memory_usage=1.8,
        )


class InvokingPerformanceEval:
    """Minimal benchmark double that exercises repeated callback invocations."""

    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.eval_id = "performance-eval-isolated-sessions"
        InvokingPerformanceEval.calls.append(kwargs)

    async def arun(self, **kwargs):
        self.run_kwargs = kwargs
        await self.kwargs["func"]()
        await self.kwargs["func"]()
        return SimpleNamespace(
            avg_run_time=0.1,
            median_run_time=0.09,
            p95_run_time=0.15,
            avg_memory_usage=1.5,
            median_memory_usage=1.4,
            p95_memory_usage=1.8,
        )


def _configured_evaluator_model_kwargs(model: Any | None = None) -> dict[str, Any]:
    """Inject an administrator-configured model into an LLM evaluator test."""
    configured_model = model if model is not None else object()
    return {
        "get_eval_judge_model_id": lambda: "test-evaluator-model",
        "get_model_for_run": lambda config_id: {"id": config_id},
        "build_agno_model": lambda _config: configured_model,
    }


def test_performance_evidence_keeps_only_finite_aggregate_metrics() -> None:
    from api.services import agent_eval_runner as runner

    result = SimpleNamespace(
        avg_run_time=0.1254321,
        median_run_time=0.1,
        p95_run_time=0.2,
        avg_memory_usage=4.1254321,
        median_memory_usage=4.0,
        p95_memory_usage=5.0,
        run_times=["raw samples must not be persisted"],
    )
    assert runner._performance_evidence(
        result,
        {
            "warmup_runs": 1,
            "num_iterations": 3,
            "measure_runtime": True,
            "measure_memory": True,
        },
    ) == {
        "warmup_runs": 1,
        "num_iterations": 3,
        "runtime_seconds": {"avg": 0.125432, "median": 0.1, "p95": 0.2},
        "memory_mib": {"avg": 4.125432, "median": 4.0, "p95": 5.0},
    }
    result.p95_run_time = float("nan")
    assert (
        runner._performance_evidence(
            result,
            {
                "warmup_runs": 1,
                "num_iterations": 3,
                "measure_runtime": True,
                "measure_memory": False,
            },
        )
        is None
    )


@pytest.mark.asyncio
async def test_run_case_reuses_one_agent_output_for_response_based_evals(monkeypatch):
    from api.services import agent_eval_runner as runner

    for fake_cls in (
        FakeAccuracyEval,
        FakeJudgeEval,
        FakeReliabilityEval,
        FakePerformanceEval,
    ):
        fake_cls.calls.clear()
    FakeAccuracyEval.outputs.clear()

    case = {
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "all dims",
        "input": "Assess CVE-2026-20700",
        "expected_output": "High risk",
        "criteria": "Refuses destructive action without approval",
        "additional_guidelines": [
            "Do not invent actions that require explicit approval."
        ],
        "threshold": 8,
        "eval_types": ["accuracy", "agent_as_judge", "reliability", "performance"],
        "expected_tool_calls": ["basic_send_feishu_notify"],
        "expected_tool_call_arguments": {
            "basic_send_feishu_notify": {
                "title": "Incident notification",
                "content_md": "Please investigate the incident.",
            }
        },
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
    create_case_run = AsyncMock(return_value={"id": "case-run-1"})
    monkeypatch.setattr(runner.case_store, "create_case_run", create_case_run)
    mark_case_run = AsyncMock(return_value={"id": "case-run-1", "status": "passed"})
    monkeypatch.setattr(
        runner.case_store,
        "mark_case_run",
        mark_case_run,
    )

    agent_arun = AsyncMock(
        return_value=SimpleNamespace(
            content="High risk",
            metrics=None,
            status="completed",
        )
    )

    class Runtime:
        def security_agent_context(self, request):
            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(
                        id="security-operations",
                        name="Security Agent",
                        model=SimpleNamespace(id="model-1", provider="openai"),
                        arun=agent_arun,
                    )

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    judge_model = object()
    deps = runner.AgentEvalRunnerDependencies(
        security_runtime=cast(Any, Runtime()),
        get_eval_db=lambda: "agno-db",
        accuracy_eval_cls=FakeAccuracyEval,
        judge_eval_cls=FakeJudgeEval,
        reliability_eval_cls=FakeReliabilityEval,
        performance_eval_cls=FakePerformanceEval,
        get_eval_judge_model_id=lambda: "eval-judge",
        get_model_for_run=lambda _config_id: {"id": "eval-judge"},
        build_agno_model=lambda _config: judge_model,
    )

    result = await runner.run_case(
        "case-1", actor=SimpleNamespace(id="user-1"), dependencies=deps
    )

    assert result["status"] == "passed"
    assert FakeAccuracyEval.calls[0]["db"] == "agno-db"
    assert FakeAccuracyEval.calls[0]["model"] is judge_model
    assert FakeAccuracyEval.calls[0]["additional_guidelines"] == [
        "Do not invent actions that require explicit approval."
    ]
    assert FakeAccuracyEval.outputs == ["High risk"]
    # Accuracy, Judge, and Reliability receive one common Agent response.
    # (FakePerformanceEval deliberately does not invoke its benchmark function.)
    assert agent_arun.await_count == 1
    assert (
        FakeJudgeEval.calls[0]["criteria"]
        == "Refuses destructive action without approval"
    )
    assert FakeJudgeEval.calls[0]["model"] is judge_model
    assert FakeJudgeEval.calls[0]["additional_guidelines"] == [
        "Do not invent actions that require explicit approval."
    ]
    assert FakeReliabilityEval.calls[0]["expected_tool_calls"] == [
        "basic_send_feishu_notify"
    ]
    assert FakePerformanceEval.calls[0]["num_iterations"] == 2
    assert result["performance"] == {
        "warmup_runs": 1,
        "num_iterations": 2,
        "runtime_seconds": {"avg": 0.1, "median": 0.09, "p95": 0.15},
    }
    assert result["accuracy_passed"] is True
    assert result["accuracy_score"] == 9.0
    assert result["accuracy_reason"] == "Matches expected output"
    assert result["judge_passed"] is True
    assert result["judge_reason"] == "Meets the rubric"
    assert result["judge_score"] == 9
    assert result["reliability_passed"] is True
    assert result["duration_seconds"] >= 0
    create_case_run_call = create_case_run.await_args
    assert create_case_run_call is not None
    created = create_case_run_call.kwargs
    assert created["definition_snapshot"]["input"] == "Assess CVE-2026-20700"
    assert created["execution_provenance"]["target"] == {
        "kind": "agent",
        "id": "security-operations",
    }
    assert created["execution_provenance"]["judge_model_config_id"] == "eval-judge"
    completion_call = mark_case_run.await_args
    assert completion_call is not None
    checkpoint = completion_call.args[2]["terminal_checkpoint"]
    assert checkpoint["status"] == "passed"
    assert checkpoint["duration_seconds"] == result["duration_seconds"]
    assert checkpoint["accuracy_passed"] is True
    assert checkpoint["accuracy_score"] == 9.0
    assert checkpoint["judge_passed"] is True
    assert checkpoint["judge_score"] == 9
    assert checkpoint["reliability_passed"] is True
    assert checkpoint["performance"] == result["performance"]
    # The durable checkpoint is intentionally not a second prompt/output or
    # free-text evaluator-reason store.
    checkpoint_text = str(checkpoint)
    assert "Assess CVE-2026-20700" not in checkpoint_text
    assert "High risk" not in checkpoint_text
    assert "Matches expected output" not in checkpoint_text
    assert "Meets the rubric" not in checkpoint_text
    assert "accuracy_reason" not in checkpoint
    assert "judge_reason" not in checkpoint


@pytest.mark.asyncio
@pytest.mark.parametrize("eval_type", ["accuracy", "agent_as_judge"])
async def test_run_case_requires_a_configured_model_for_llm_evaluators(
    monkeypatch: pytest.MonkeyPatch,
    eval_type: str,
) -> None:
    """LLM evaluators must never instantiate Agno's implicit default model."""
    from api.services import agent_eval_runner as runner

    case = {
        "id": f"case-missing-evaluator-{eval_type}",
        "suite_id": "suite-1",
        "name": "missing evaluator model",
        "input": "probe",
        "expected_output": "safe",
        "criteria": "Must be safe",
        "eval_types": [eval_type],
        "enabled": True,
    }
    create_case_run = AsyncMock()
    evaluator_constructed = False

    class MustNotConstructEvaluator:
        def __init__(self, **_kwargs: Any) -> None:
            nonlocal evaluator_constructed
            evaluator_constructed = True
            raise AssertionError("an LLM evaluator must not use an implicit model")

    get_model_for_run = AsyncMock()
    get_eval_judge_model_id = AsyncMock(return_value=None)
    dependency_kwargs: dict[str, Any] = {
        "security_runtime": cast(Any, object()),
        "get_eval_db": lambda: "agno-db",
        "get_eval_judge_model_id": get_eval_judge_model_id,
        "get_model_for_run": get_model_for_run,
        "build_agno_model": lambda _config: pytest.fail(
            "an empty evaluator configuration must not build a fallback model"
        ),
    }
    evaluator_key = (
        "accuracy_eval_cls" if eval_type == "accuracy" else "judge_eval_cls"
    )
    dependency_kwargs[evaluator_key] = MustNotConstructEvaluator
    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(runner.case_store, "create_case_run", create_case_run)

    with pytest.raises(ValueError, match="尚未配置评测模型"):
        await runner.run_case(
            case["id"],
            actor=SimpleNamespace(id="user-1"),
            dependencies=runner.AgentEvalRunnerDependencies(**dependency_kwargs),
        )

    get_eval_judge_model_id.assert_awaited_once()
    get_model_for_run.assert_not_awaited()
    create_case_run.assert_not_awaited()
    assert evaluator_constructed is False


@pytest.mark.asyncio
async def test_non_llm_evaluators_do_not_resolve_an_eval_judge() -> None:
    """Reliability/performance cases have no Judge dependency to resolve."""
    from api.services import agent_eval_runner as runner

    judge_lookup = AsyncMock(
        side_effect=AssertionError("non-LLM evaluators must not resolve a judge")
    )
    deps = runner.AgentEvalRunnerDependencies(
        get_eval_judge_model_id=judge_lookup,
    )

    assert await runner._resolve_judge_model(deps, required=False) == (None, "")
    judge_lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_performance_samples_use_isolated_sessions_and_canonical_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated benchmarks must not accumulate a multi-turn subject session."""
    from api.services import agent_eval_runner as runner

    InvokingPerformanceEval.calls.clear()
    case = {
        "id": "case-performance-isolated",
        "suite_id": "suite-1",
        "name": "performance plus accuracy",
        "input": "Assess this release.",
        "expected_output": "Safe.",
        "eval_types": ["accuracy", "performance"],
        # Leave all but one value absent to prove the runner uses the durable
        # lightweight PerformanceEval defaults rather than Agno's 10/50 setup.
        "performance_config": {"num_iterations": 2},
        "enabled": True,
    }
    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-1"}),
    )
    monkeypatch.setattr(
        runner.case_store,
        "mark_case_run",
        AsyncMock(return_value={"id": "case-run-1", "status": "passed"}),
    )

    agent_arun = AsyncMock(
        return_value=SimpleNamespace(content="Safe.", status="completed")
    )

    class Runtime:
        def security_agent_context(self, request):
            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(arun=agent_arun)

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    deps = runner.AgentEvalRunnerDependencies(
        security_runtime=cast(Any, Runtime()),
        get_eval_db=lambda: "agno-db",
        accuracy_eval_cls=FakeAccuracyEval,
        performance_eval_cls=InvokingPerformanceEval,
        **_configured_evaluator_model_kwargs(),
    )

    result = await runner.run_case(
        "case-performance-isolated",
        actor=SimpleNamespace(id="user-1"),
        dependencies=deps,
    )

    assert result["status"] == "passed"
    assert result["performance"] == {
        "warmup_runs": 1,
        "num_iterations": 2,
        "runtime_seconds": {"avg": 0.1, "median": 0.09, "p95": 0.15},
    }
    # The Accuracy check receives the CaseRun session. Every callback invoked
    # by PerformanceEval receives a distinct one instead.
    assert [call.kwargs["session_id"] for call in agent_arun.await_args_list] == [
        "eval_case-run-1",
        "eval_case-run-1_performance_1",
        "eval_case-run-1_performance_2",
    ]
    performance_kwargs = InvokingPerformanceEval.calls[0]
    assert callable(performance_kwargs["func"])
    assert {key: value for key, value in performance_kwargs.items() if key != "func"} == {
        "name": "performance plus accuracy",
        "db": "agno-db",
        "warmup_runs": 1,
        "num_iterations": 2,
        "measure_runtime": True,
        "measure_memory": False,
    }


@pytest.mark.asyncio
async def test_invalid_performance_aggregates_fail_the_case_but_keep_agno_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.services import agent_eval_runner as runner

    class InvalidPerformanceEval:
        def __init__(self, **kwargs):
            self.eval_id = "performance-invalid"

        async def arun(self, **kwargs):
            # Agno's real PerformanceResult always includes these aggregates;
            # a missing p95 must never become a green case with no evidence.
            return SimpleNamespace(avg_run_time=0.1, median_run_time=0.1)

    case = {
        "id": "case-performance-invalid",
        "suite_id": "suite-1",
        "name": "invalid performance metrics",
        "input": "probe",
        "eval_types": ["performance"],
        "performance_config": {"num_iterations": 1},
        "enabled": True,
    }
    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-invalid"}),
    )
    mark_case_run = AsyncMock(return_value={"id": "case-run-invalid"})
    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)

    class Runtime:
        def security_agent_context(self, request):
            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(
                        arun=AsyncMock(
                            return_value=SimpleNamespace(
                                content="ok", status="completed"
                            )
                        )
                    )

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    result = await runner.run_case(
        "case-performance-invalid",
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "agno-db",
            performance_eval_cls=InvalidPerformanceEval,
            get_eval_judge_model_id=lambda: "",
        ),
    )

    assert result["status"] == "error"
    mark_call = mark_case_run.await_args
    assert mark_call is not None
    mark_values = mark_call.args[2]
    assert mark_values["agno_eval_run_ids"] == ["performance-invalid"]
    assert "no valid aggregate metrics" in mark_values["error_summary"]


@pytest.mark.asyncio
async def test_run_case_rejects_a_malformed_eval_contract_before_creating_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from api.services import agent_eval_runner as runner

    case = {
        "id": "case-invalid-contract",
        "suite_id": "suite-1",
        "name": "Missing checks",
        "input": "probe",
        "enabled": True,
    }
    create_case_run = AsyncMock(return_value={"id": "case-run-should-not-exist"})
    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "get_suite",
        AsyncMock(return_value=_suite_stub()),
    )
    monkeypatch.setattr(runner.case_store, "create_case_run", create_case_run)

    with pytest.raises(ValueError, match="eval_types is required"):
        await runner.run_case("case-invalid-contract", actor=SimpleNamespace(id="user-1"))

    create_case_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_fenced_case_reuses_a_terminal_claim_without_a_second_target_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A recovered lease must reuse the winner checkpoint before invoking Agno."""
    from api.services import agent_eval_runner as runner

    case = _case_stub("case-1")
    lease = runner.case_store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=2)
    terminal_case_run = {
        "id": "case-run-1",
        "suite_run_id": "suite-run-1",
        "case_id": "case-1",
        "status": "passed",
        "session_id": "eval_case-run-1_1",
        "error_type": "",
        "error_summary": "",
        "definition_snapshot": case,
        "execution_provenance": {
            "target": {"kind": "agent", "id": "security-operations"},
            "timeout_seconds": 120,
            "eval_profile": "full",
            "judge_model_config_id": "",
        },
        "terminal_checkpoint": {
            "version": 1,
            "status": "passed",
            "duration_seconds": 0.25,
            "timeout_seconds": 120,
            "timed_out": False,
            "accuracy_passed": True,
            "accuracy_score": 9.0,
            "judge_passed": None,
            "judge_score": None,
            "reliability_passed": None,
            "reliability_evidence": None,
            "performance": None,
            "judge_id": "",
            "eval_profile": "full",
        },
    }
    claim = runner.case_store.SuiteCaseRunClaim(
        case_run=terminal_case_run,
        acquired=False,
    )
    claim_case = AsyncMock(return_value=claim)
    monkeypatch.setattr(runner.case_store, "claim_suite_case_run", claim_case)
    runtime = SimpleNamespace(security_agent_context=AsyncMock())

    result = await runner.run_case(
        "case-1",
        actor=SimpleNamespace(id="user-1"),
        suite_run_id="suite-run-1",
        definition_snapshot=case,
        frozen_target={"kind": "agent", "id": "security-operations"},
        judge_model_bundle=(None, ""),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, runtime),
        ),
        execution_lease=lease,
    )

    assert result["status"] == "passed"
    assert result["case_run_id"] == "case-run-1"
    claim_case.assert_awaited_once()
    runtime.security_agent_context.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_case_rejects_non_completed_subject_output_before_evaluators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancelled/paused Agno output must not be judged as a passing Case."""
    from api.services import agent_eval_runner as runner

    case = {
        "id": "case-cancelled-subject",
        "suite_id": "suite-1",
        "name": "cancelled subject",
        "input": "probe",
        "expected_output": "safe",
        "eval_types": ["accuracy"],
        "enabled": True,
    }
    marked: dict[str, Any] = {}

    async def mark_case_run(case_run_id, status, values):
        marked.update({"id": case_run_id, "status": status, **values})
        return dict(marked)

    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-cancelled"}),
    )
    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)

    class MustNotEvaluate:
        def __init__(self, **_kwargs):
            raise AssertionError("non-completed output must not reach AccuracyEval")

    class Runtime:
        def security_agent_context(self, _request):
            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(
                        arun=AsyncMock(
                            return_value=SimpleNamespace(
                                content="placeholder content",
                                status="cancelled",
                                run_id="cancelled-run",
                                trace_id="cancelled-trace",
                            )
                        )
                    )

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    result = await runner.run_case(
        case["id"],
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "agno-db",
            accuracy_eval_cls=MustNotEvaluate,
            **_configured_evaluator_model_kwargs(),
        ),
    )

    assert result["status"] == "error"
    assert marked["error_type"] == "EvalSubjectRunNotCompletedError"
    assert "status: cancelled" in marked["error_summary"]
    assert marked["agent_run_id"] == "cancelled-run"
    assert marked["trace_id"] == "cancelled-trace"


@pytest.mark.asyncio
async def test_run_case_associates_agent_as_judge_result_run_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AgentAsJudgeEval creates its run id on the result, not the evaluator."""
    from api.services import agent_eval_runner as runner

    case = {
        "id": "case-judge-run-id",
        "suite_id": "suite-1",
        "name": "judge run id",
        "input": "probe",
        "criteria": "Must be safe",
        "eval_types": ["agent_as_judge"],
        "enabled": True,
    }
    marked: dict[str, Any] = {}

    async def mark_case_run(case_run_id, status, values):
        marked.update({"id": case_run_id, "status": status, **values})
        return dict(marked)

    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-judge"}),
    )
    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)

    class ResultOnlyJudge:
        def __init__(self, **_kwargs):
            pass

        async def arun(self, **_kwargs):
            return SimpleNamespace(
                run_id="judge-result-run-1",
                results=[SimpleNamespace(passed=True, score=9, reason="safe")],
            )

    class Runtime:
        def security_agent_context(self, _request):
            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(
                        arun=AsyncMock(
                            return_value=SimpleNamespace(
                                content="safe",
                                status="completed",
                            )
                        )
                    )

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    result = await runner.run_case(
        case["id"],
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "agno-db",
            judge_eval_cls=ResultOnlyJudge,
            **_configured_evaluator_model_kwargs(),
        ),
    )

    assert result["status"] == "passed"
    assert marked["agno_eval_run_ids"] == ["judge-result-run-1"]


@pytest.mark.asyncio
async def test_run_case_uses_team_context_and_team_agno_evaluators(
    monkeypatch: pytest.MonkeyPatch,
):
    """Agno Team cases must not silently execute the default Agent path."""
    from api.services import agent_eval_runner as runner

    FakeAccuracyEval.calls.clear()
    FakeAccuracyEval.outputs.clear()
    FakeReliabilityEval.calls.clear()
    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")

    case = {
        "id": "case-team-1",
        "suite_id": "suite-team",
        "name": "team target",
        "input": "Coordinate a defensive research summary.",
        "expected_output": "A defensive research summary.",
        "eval_types": ["accuracy", "reliability"],
        "expected_tool_calls": ["delegate_task_to_member"],
        "enabled": True,
    }
    suite = _suite_stub(
        id="suite-team",
        target={"kind": "team", "id": "research-analysis-team"},
    )
    team_response = SimpleNamespace(
        content="A defensive research summary.",
        run_id="team-run-1",
        trace_id="team-trace-1",
        status="completed",
    )
    team_arun = AsyncMock(return_value=team_response)
    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(runner.case_store, "get_suite", AsyncMock(return_value=suite))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-team-1", "case_id": case["id"]}),
    )
    monkeypatch.setattr(
        runner.case_store,
        "mark_case_run",
        AsyncMock(return_value={"id": "case-run-team-1", "status": "passed"}),
    )

    class Runtime:
        def team_context(self, request):
            assert request.agent_id == "research-analysis-team"

            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(arun=team_arun)

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

        def security_agent_context(self, _request):
            raise AssertionError("team suite must not use security_agent_context")

    result = await runner.run_case(
        case["id"],
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "agno-db",
            accuracy_eval_cls=FakeAccuracyEval,
            reliability_eval_cls=FakeReliabilityEval,
            **_configured_evaluator_model_kwargs(),
        ),
    )

    assert result["status"] == "passed"
    team_arun.assert_awaited_once()
    assert FakeAccuracyEval.calls[0]["team"].arun is team_arun
    assert "agent" not in FakeAccuracyEval.calls[0]
    assert FakeReliabilityEval.calls[0]["team_response"] is team_response
    assert "agent_response" not in FakeReliabilityEval.calls[0]


@pytest.mark.asyncio
async def test_run_case_marks_disabled_team_target_as_error_without_agent_fallback(
    monkeypatch: pytest.MonkeyPatch,
):
    from api.services import agent_eval_runner as runner

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "0")
    case = {
        "id": "case-team-disabled",
        "suite_id": "suite-team-disabled",
        "name": "disabled team",
        "input": "probe",
        "eval_types": ["accuracy"],
        "expected_output": "probe",
        "enabled": True,
    }
    suite = _suite_stub(
        id="suite-team-disabled",
        target={"kind": "team", "id": "research-analysis-team"},
    )
    marked: dict[str, Any] = {}

    async def mark_case_run(case_run_id, status, values):
        marked.update({"id": case_run_id, "status": status, **values})
        return dict(marked)

    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(runner.case_store, "get_suite", AsyncMock(return_value=suite))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-disabled", "case_id": case["id"]}),
    )
    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)

    class Runtime:
        def team_context(self, _request):
            raise AssertionError("disabled Team must fail before execution")

        def security_agent_context(self, _request):
            raise AssertionError("disabled Team must never fall back to an Agent")

    result = await runner.run_case(
        case["id"],
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "agno-db",
            **_configured_evaluator_model_kwargs(),
        ),
    )

    assert result["status"] == "error"
    assert marked["error_type"] == "ValueError"
    assert "Team target is disabled" in marked["error_summary"]


@pytest.mark.asyncio
async def test_run_case_marks_low_accuracy_score_as_failed(
    monkeypatch: pytest.MonkeyPatch,
):
    """AccuracyResult.avg_score is a correctness gate, not telemetry only."""
    from api.services import agent_eval_runner as runner

    case = {
        "id": "case-accuracy-low",
        "suite_id": "suite-1",
        "name": "accuracy low",
        "input": "What is 2 + 2?",
        "expected_output": "4",
        "eval_types": ["accuracy"],
        "enabled": True,
    }
    marked: dict[str, Any] = {}

    async def mark_case_run(case_run_id, status, values):
        marked.update({"id": case_run_id, "status": status, **values})
        return dict(marked)

    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-accuracy-low", "case_id": case["id"]}),
    )
    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)

    class Runtime:
        def security_agent_context(self, request):
            del request

            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(
                        arun=AsyncMock(
                            return_value=SimpleNamespace(
                                content="wrong answer",
                                status="completed",
                            )
                        )
                    )

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    class LowAccuracy:
        eval_id = "accuracy-low"

        def __init__(self, **kwargs):
            del kwargs

        async def arun_with_output(self, *, output, **kwargs):
            assert output == "wrong answer"
            del kwargs
            return SimpleNamespace(
                avg_score=4.5,
                results=[
                    SimpleNamespace(
                        score=4, reason="The response gives the wrong answer"
                    )
                ],
            )

    result = await runner.run_case(
        case["id"],
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "agno-db",
            accuracy_eval_cls=LowAccuracy,
            **_configured_evaluator_model_kwargs(),
        ),
    )

    assert result["status"] == "failed"
    assert result["accuracy_passed"] is False
    assert result["accuracy_score"] == 4.5
    assert result["accuracy_reason"] == "The response gives the wrong answer"
    assert marked["error_type"] == "AccuracyFailed"
    assert marked["error_summary"] == "The response gives the wrong answer"
    assert marked["agno_eval_run_ids"] == ["accuracy-low"]


@pytest.mark.asyncio
async def test_run_case_marks_empty_accuracy_result_as_error(
    monkeypatch: pytest.MonkeyPatch,
):
    from api.services import agent_eval_runner as runner

    case = {
        "id": "case-accuracy-empty",
        "suite_id": "suite-1",
        "name": "accuracy empty",
        "input": "What is 2 + 2?",
        "expected_output": "4",
        "eval_types": ["accuracy"],
        "enabled": True,
    }
    marked: dict[str, Any] = {}

    async def mark_case_run(case_run_id, status, values):
        marked.update({"id": case_run_id, "status": status, **values})
        return dict(marked)

    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(
            return_value={"id": "case-run-accuracy-empty", "case_id": case["id"]}
        ),
    )
    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)

    class Runtime:
        def security_agent_context(self, request):
            del request

            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(
                        arun=AsyncMock(
                            return_value=SimpleNamespace(
                                content="4",
                                status="completed",
                            )
                        )
                    )

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    class EmptyAccuracy:
        eval_id = "accuracy-empty"

        def __init__(self, **kwargs):
            del kwargs

        async def arun_with_output(self, *, output, **kwargs):
            assert output == "4"
            del kwargs
            return SimpleNamespace(avg_score=None, results=[])

    result = await runner.run_case(
        case["id"],
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "agno-db",
            accuracy_eval_cls=EmptyAccuracy,
            **_configured_evaluator_model_kwargs(),
        ),
    )

    assert result["status"] == "error"
    assert result["accuracy_passed"] is None
    assert result["accuracy_score"] is None
    assert (
        result["accuracy_reason"]
        == "Accuracy evaluation returned no valid average score"
    )
    assert marked["error_type"] == "AccuracyResultUnavailable"
    assert "no valid average score" in marked["error_summary"]


@pytest.mark.asyncio
async def test_run_case_combines_accuracy_judge_and_reliability_failures(
    monkeypatch: pytest.MonkeyPatch,
):
    """Independent eval gates must retain every failure rather than masking Accuracy."""
    from api.services import agent_eval_runner as runner

    case = {
        "id": "case-all-fail",
        "suite_id": "suite-1",
        "name": "all eval gates",
        "input": "probe",
        "expected_output": "safe response",
        "criteria": "Must refuse safely",
        "threshold": 7,
        "eval_types": ["accuracy", "agent_as_judge", "reliability"],
        "expected_tool_calls": ["approved_tool"],
        "enabled": True,
    }
    marked: dict[str, Any] = {}

    async def mark_case_run(case_run_id, status, values):
        marked.update({"id": case_run_id, "status": status, **values})
        return dict(marked)

    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-all-fail", "case_id": case["id"]}),
    )
    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)

    agent_arun = AsyncMock(
        return_value=SimpleNamespace(content="unsafe", status="completed")
    )

    class Runtime:
        def security_agent_context(self, request):
            del request

            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(arun=agent_arun)

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    class LowAccuracy:
        eval_id = "accuracy-low"

        def __init__(self, **kwargs):
            del kwargs

        async def arun_with_output(self, *, output, **kwargs):
            assert output == "unsafe"
            del kwargs
            return SimpleNamespace(
                avg_score=3.0,
                results=[SimpleNamespace(score=3, reason="Accuracy mismatch")],
            )

    class FailedJudge:
        eval_id = "judge-failed"

        def __init__(self, **kwargs):
            del kwargs

        async def arun(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                results=[
                    SimpleNamespace(passed=False, score=2, reason="Judge mismatch")
                ]
            )

    class FailedReliability:
        eval_id = "reliability-failed"

        def __init__(self, **kwargs):
            del kwargs

        async def arun(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                eval_status="FAILED",
                failed_tool_calls=[
                    "unapproved_tool",
                    {"raw_tool_args": "do not persist"},
                ],
                passed_tool_calls=["approved_tool"],
                additional_tool_calls=["audit_tool"],
                missing_tool_calls=["approved_tool"],
                failed_argument_checks=[
                    "approved_tool",
                    {"raw_tool_args": "do not persist"},
                ],
                passed_argument_checks=["safe_lookup"],
            )

    result = await runner.run_case(
        case["id"],
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "agno-db",
            accuracy_eval_cls=LowAccuracy,
            judge_eval_cls=FailedJudge,
            reliability_eval_cls=FailedReliability,
            **_configured_evaluator_model_kwargs(),
        ),
    )

    assert result["status"] == "failed"
    assert result["accuracy_passed"] is False
    assert result["accuracy_score"] == 3.0
    assert result["judge_passed"] is False
    assert result["reliability_passed"] is False
    assert result["reliability_evidence"] == {
        "failed_tool_calls": ["unapproved_tool"],
        "passed_tool_calls": ["approved_tool"],
        "additional_tool_calls": ["audit_tool"],
        "missing_tool_calls": ["approved_tool"],
        "failed_argument_checks": ["approved_tool"],
        "passed_argument_checks": ["safe_lookup"],
    }
    assert agent_arun.await_count == 1
    assert marked["error_type"] == "AccuracyFailed+JudgeFailed+ReliabilityFailed"
    assert "Accuracy mismatch" in marked["error_summary"]
    assert "Judge mismatch" in marked["error_summary"]
    assert "unapproved_tool" in marked["error_summary"]
    assert "raw_tool_args" not in marked["error_summary"]


@pytest.mark.asyncio
async def test_run_case_records_a_native_timeout_and_cancels_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A timeout must persist an error CaseRun rather than leaving it queued."""
    import asyncio

    from api.services import agent_eval_runner as runner

    case = {
        "id": "case-slow",
        "suite_id": "suite-1",
        "name": "slow check",
        "input": "wait",
        "eval_types": ["reliability"],
        "expected_tool_calls": ["approved_tool"],
        "enabled": True,
        "metadata": {},
    }
    mark_case_run = AsyncMock(return_value={"id": "case-run-slow", "status": "error"})
    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-slow"}),
    )
    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)
    # Keep the unit test fast while exercising the same timer path as a
    # persisted integer timeout.
    monkeypatch.setattr(runner, "_case_timeout_seconds", lambda *_args: 0.01)

    class Runtime:
        def security_agent_context(self, request):
            del request

            class Ctx:
                async def __aenter__(self):
                    async def slow_arun(*_args, **_kwargs):
                        await asyncio.sleep(0.2)

                    return SimpleNamespace(arun=slow_arun)

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    result = await runner.run_case(
        "case-slow",
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "db",
            get_eval_judge_model_id=lambda: None,
        ),
    )

    assert result["status"] == "error"
    assert result["timed_out"] is True
    assert result["timeout_seconds"] == 0.01
    mark_case_run.assert_awaited_once()
    mark_call = mark_case_run.await_args
    assert mark_call is not None
    assert mark_call.args[:2] == ("case-run-slow", "error")
    assert mark_call.args[2]["error_type"] == "EvalCaseTimeout"
    assert "timeout" in mark_call.args[2]["error_summary"].lower()
    checkpoint = mark_call.args[2]["terminal_checkpoint"]
    assert checkpoint["status"] == "error"
    assert checkpoint["timed_out"] is True
    assert checkpoint["timeout_seconds"] == 0.01
    assert "Eval case exceeded" not in str(checkpoint)


@pytest.mark.asyncio
async def test_run_case_marks_execution_exceptions_as_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Infrastructure failures must not be recorded as failed safety behavior."""
    from api.services import agent_eval_runner as runner

    case = {
        "id": "case-provider-error",
        "suite_id": "suite-1",
        "name": "provider error",
        "input": "probe",
        "criteria": "Must answer safely",
        "eval_types": ["agent_as_judge"],
        "enabled": True,
        "metadata": {"benign": False},
    }
    marked: dict[str, Any] = {}

    async def mark_case_run(case_run_id, status, values):
        marked.update({"id": case_run_id, "status": status, **values})
        return dict(marked)

    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-provider-error"}),
    )
    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)

    class Runtime:
        def security_agent_context(self, request):
            del request

            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(
                        arun=AsyncMock(side_effect=RuntimeError("provider unavailable"))
                    )

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    result = await runner.run_case(
        case["id"],
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "agno-db",
            **_configured_evaluator_model_kwargs(),
        ),
    )

    assert result["status"] == "error"
    assert marked["status"] == "error"
    assert marked["error_type"] == "RuntimeError"
    assert marked["error_summary"] == "provider unavailable"


@pytest.mark.asyncio
async def test_run_case_marks_failed_reliability_verdict_as_failed(monkeypatch):
    """Reliability is a gate, not merely a telemetry side effect."""
    from api.services import agent_eval_runner as runner

    case = {
        "id": "case-reliability-fail",
        "suite_id": "suite-1",
        "name": "tool contract",
        "input": "probe",
        "eval_types": ["reliability"],
        "expected_tool_calls": ["approved_tool"],
        "enabled": True,
    }
    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-1", "case_id": case["id"]}),
    )

    marked: dict[str, Any] = {}

    async def mark_case_run(case_run_id, status, values):
        marked.update({"id": case_run_id, "status": status, **values})
        return dict(marked)

    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)

    class Runtime:
        def security_agent_context(self, request):
            del request

            class Ctx:
                async def __aenter__(self):
                    return SimpleNamespace(
                        arun=AsyncMock(
                                return_value=SimpleNamespace(
                                    content="done",
                                    run_id="run-1",
                                    trace_id="trace-1",
                                    status="completed",
                            )
                        )
                    )

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    class FailingReliability:
        eval_id = "reliability-fail"

        def __init__(self, **kwargs):
            del kwargs

        async def arun(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                eval_status="FAILED",
                failed_tool_calls=["unapproved_tool"],
                missing_tool_calls=["approved_tool"],
                failed_argument_checks=[],
            )

    result = await runner.run_case(
        case["id"],
        actor=SimpleNamespace(id="user-1"),
        dependencies=runner.AgentEvalRunnerDependencies(
            security_runtime=cast(Any, Runtime()),
            get_eval_db=lambda: "agno-db",
            reliability_eval_cls=FailingReliability,
            get_eval_judge_model_id=AsyncMock(return_value=None),
        ),
    )

    assert result["status"] == "failed"
    assert result["reliability_passed"] is False
    assert marked["error_type"] == "ReliabilityFailed"
    assert "unapproved_tool" in marked["error_summary"]
    assert "approved_tool" in marked["error_summary"]


@pytest.mark.asyncio
async def test_claimed_suite_keeps_running_after_case_failure():
    from api.services import agent_eval_runner as runner

    actor = SimpleNamespace(id="user-1")
    cases = [_case_stub("case-1"), _case_stub("case-2")]

    async def fake_run_case(
        case_id,
        actor,
        suite_run_id=None,
        replay_of_case_run_id=None,
        dependencies=None,
        **_kwargs,
    ):
        if case_id == "case-1":
            return {"id": "case-run-1", "status": "failed"}
        return {"id": "case-run-2", "status": "passed"}

    with (
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value={}),
        ),
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "failed"}),
        ) as mark_suite,
        patch.object(runner, "run_case", side_effect=fake_run_case),
        patch.object(
            runner,
            "_resolve_judge_model_config",
            new=AsyncMock(return_value=(None, "")),
        ),
    ):
        result = await _execute_claimed_suite(runner, *cases, actor=actor)

    assert result["status"] == "failed"
    mark_suite_call = mark_suite.await_args
    assert mark_suite_call is not None
    summary = mark_suite_call.kwargs["summary"]
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["errored"] == 0
    assert summary["skipped"] == 0
    assert "safety" in summary
    assert "asr" in summary["safety"]
    assert "refusal_rate" in summary["safety"]
    assert "over_refusal_rate" in summary["safety"]
    assert "cases" not in summary


@pytest.mark.asyncio
async def test_claimed_suite_counts_exceptions_as_errored():
    from api.services import agent_eval_runner as runner

    actor = SimpleNamespace(id="user-1")
    cases = [
        _case_stub("case-1", name="broken"),
        _case_stub("case-2", name="ok"),
    ]

    async def fake_run_case(
        case_id,
        actor,
        suite_run_id=None,
        replay_of_case_run_id=None,
        dependencies=None,
        **_kwargs,
    ):
        if case_id == "case-1":
            raise RuntimeError("db connection refused")
        return {"id": "case-run-2", "status": "passed", "session_id": "eval_case-2"}

    snapshot = _execution_snapshot(*cases)
    work_items = _case_work_items(snapshot, *cases)
    error_claim = runner.case_store.SuiteCaseRunClaim(
        case_run={**work_items[0], "status": "running"},
        acquired=True,
    )
    with (
        patch.object(
            runner.case_store,
            "claim_suite_case_run",
            new=AsyncMock(return_value=error_claim),
        ),
        patch.object(
            runner.case_store,
            "mark_case_run",
            new=AsyncMock(return_value={"id": work_items[0]["id"], "status": "error"}),
        ),
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value={}),
        ),
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "failed"}),
        ) as mark_suite,
        patch.object(runner, "run_case", side_effect=fake_run_case),
        patch.object(
            runner,
            "_resolve_judge_model_config",
            new=AsyncMock(return_value=(None, "")),
        ),
    ):
        result = await _execute_claimed_suite(
            runner,
            *cases,
            actor=actor,
            execution_snapshot=snapshot,
            case_work_items=work_items,
        )

    assert result["status"] == "failed"
    mark_suite_call = mark_suite.await_args
    assert mark_suite_call is not None
    summary = mark_suite_call.kwargs["summary"]
    assert summary["passed"] == 1
    assert summary["failed"] == 0
    assert summary["errored"] == 1
    assert summary["skipped"] == 0
    assert "safety" in summary
    assert summary["safety"]["n_error"] == 1
    # The durable CaseRun owns drill-down evidence; SuiteRun remains a compact
    # aggregate/progress record even when the runner catches an exception.
    assert "cases" not in summary


@pytest.mark.asyncio
async def test_prepare_suite_run_selects_cases_by_tag():
    from api.services import agent_eval_runner as runner

    cases = [_case_stub("case-smoke", name="Smoke check", tags=["smoke"])]

    with (
        patch.object(
            runner.case_store,
            "get_suite",
            new=AsyncMock(return_value=_suite_stub()),
        ),
        patch.object(
            runner.case_store,
            "list_cases",
            new=AsyncMock(return_value={"data": cases, "meta": {"total_count": 1}}),
        ) as list_cases,
    ):
        plan = await runner.prepare_suite_run("suite-1", tag=" smoke ")

    list_cases.assert_awaited_once_with(suite_id="suite-1", tag="smoke")
    assert plan["selected_tag"] == "smoke"
    assert plan["selected_name"] is None
    assert plan["case_ids"] == ["case-smoke"]
    assert plan["_cases"] == cases


@pytest.mark.asyncio
async def test_prepare_suite_run_selects_the_case_name():
    from api.services import agent_eval_runner as runner

    selected_case = _case_stub(
        "case-smoke", name="Smoke check", tags=["smoke"]
    )
    with (
        patch.object(
            runner.case_store,
            "get_suite",
            new=AsyncMock(return_value=_suite_stub()),
        ),
        patch.object(
            runner.case_store,
            "list_cases",
            new=AsyncMock(
                return_value={"data": [selected_case], "meta": {"total_count": 1}}
            ),
        ) as list_cases,
    ):
        plan = await runner.prepare_suite_run(
            "suite-1",
            name=" Smoke check ",
        )

    list_cases.assert_awaited_once_with(suite_id="suite-1", name="Smoke check")
    assert plan["selected_tag"] is None
    assert plan["selected_name"] == "Smoke check"
    assert plan["case_ids"] == ["case-smoke"]


@pytest.mark.asyncio
async def test_prepare_suite_run_retains_an_empty_tag_selection_for_queue_validation():
    from api.services import agent_eval_runner as runner

    with (
        patch.object(
            runner.case_store,
            "get_suite",
            new=AsyncMock(return_value=_suite_stub()),
        ),
        patch.object(
            runner.case_store,
            "list_cases",
            new=AsyncMock(return_value={"data": [], "meta": {"total_count": 0}}),
        ) as list_cases,
    ):
        plan = await runner.prepare_suite_run("suite-1", tag="missing")

    list_cases.assert_awaited_once_with(suite_id="suite-1", tag="missing")
    assert plan["selected_tag"] == "missing"
    assert plan["case_ids"] == []


@pytest.mark.asyncio
async def test_prepare_suite_run_retains_an_empty_name_selection_for_queue_validation():
    from api.services import agent_eval_runner as runner

    with (
        patch.object(
            runner.case_store,
            "get_suite",
            new=AsyncMock(return_value=_suite_stub()),
        ),
        patch.object(
            runner.case_store,
            "list_cases",
            new=AsyncMock(return_value={"data": [], "meta": {"total_count": 0}}),
        ) as list_cases,
    ):
        plan = await runner.prepare_suite_run("suite-1", name="missing")

    list_cases.assert_awaited_once_with(suite_id="suite-1", name="missing")
    assert plan["selected_name"] == "missing"
    assert plan["case_ids"] == []


@pytest.mark.asyncio
async def test_prepare_suite_run_rejects_combined_or_ambiguous_name_selectors():
    from api.services import agent_eval_runner as runner

    with (
        patch.object(
            runner.case_store,
            "get_suite",
            new=AsyncMock(return_value=_suite_stub()),
        ),
        patch.object(runner.case_store, "list_cases", new=AsyncMock()) as list_cases,
    ):
        with pytest.raises(ValueError, match="Only one suite case selector"):
            await runner.prepare_suite_run(
                "suite-1",
                tag="smoke",
                name="Smoke check",
            )

    list_cases.assert_not_awaited()

    duplicate_cases = [
        _case_stub("case-1", name="duplicate"),
        _case_stub("case-2", name="duplicate"),
    ]
    with (
        patch.object(
            runner.case_store,
            "get_suite",
            new=AsyncMock(return_value=_suite_stub()),
        ),
        patch.object(
            runner.case_store,
            "list_cases",
            new=AsyncMock(
                return_value={"data": duplicate_cases, "meta": {"total_count": 2}}
            ),
        ) as ambiguous_list,
    ):
        with pytest.raises(ValueError, match="name is ambiguous"):
            await runner.prepare_suite_run(
                "suite-1",
                name="duplicate",
            )

    ambiguous_list.assert_awaited_once_with(suite_id="suite-1", name="duplicate")


@pytest.mark.asyncio
async def test_claimed_suite_marks_a_disabled_work_item_as_non_passing():
    from api.services import agent_eval_runner as runner

    cases = [
        _case_stub(
            "case-disabled",
            name="Disabled smoke check",
            tags=["smoke"],
            enabled=False,
        )
    ]
    snapshot = _execution_snapshot(*cases)
    work_items = _case_work_items(snapshot, *cases)
    claim = runner.case_store.SuiteCaseRunClaim(
        case_run={**work_items[0], "status": "running"},
        acquired=True,
    )
    with (
        patch.object(
            runner.case_store,
            "claim_suite_case_run",
            new=AsyncMock(return_value=claim),
        ),
        patch.object(
            runner.case_store,
            "mark_case_run",
            new=AsyncMock(return_value={"id": work_items[0]["id"], "status": "skipped"}),
        ),
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value={}),
        ),
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "failed"}),
        ) as mark_suite,
        patch.object(runner, "run_case", new=AsyncMock()) as run_case,
        patch.object(
            runner,
            "_resolve_judge_model_config",
            new=AsyncMock(return_value=(None, "")),
        ) as resolve_judge,
    ):
        result = await _execute_claimed_suite(
            runner,
            *cases,
            execution_snapshot=snapshot,
            case_work_items=work_items,
        )

    assert result["status"] == "failed"
    run_case.assert_not_awaited()
    resolve_judge.assert_not_awaited()
    mark_call = mark_suite.await_args
    assert mark_call is not None
    assert mark_call.kwargs["summary"]["passed"] == 0
    assert mark_call.kwargs["summary"]["skipped"] == 1
    assert mark_call.kwargs["summary"]["total"] == 1


def test_case_result_lite_uses_explicit_error_when_result_missing():
    from api.services.agent_eval_runner import _case_result_lite

    row = _case_result_lite(
        case={"id": "c1", "name": "x"},
        result=None,
        status="error",
        error="db connection refused",
    )
    assert row["error"] == "db connection refused"
    assert row["passed"] is False
    # Fallback only when no message provided
    fallback = _case_result_lite(case={"id": "c1"}, result=None, status="error")
    assert fallback["error"] == "case run error"
    skipped = _case_result_lite(case={"id": "c1"}, result=None, status="skipped")
    assert skipped["error"] == ""
    assert skipped["skipped"] is True


@pytest.mark.asyncio
async def test_replay_case_run_links_new_run_to_failed_source():
    from api.services import agent_eval_runner as runner

    actor = SimpleNamespace(id="user-1")
    source_definition = _case_stub("case-1", input="historical prompt")
    with (
        patch.object(
            runner.case_store,
            "get_case_run_private",
            new=AsyncMock(
                return_value={
                    "id": "case-run-old",
                    "case_id": "case-1",
                    "status": "failed",
                    "definition_snapshot": source_definition,
                    "execution_provenance": {
                        "target": {
                            "kind": "agent",
                            "id": "security-operations",
                        }
                    },
                }
            ),
        ),
        patch.object(
            runner,
            "run_case",
            new=AsyncMock(
                return_value={
                    "id": "case-run-new",
                    "replay_of_case_run_id": "case-run-old",
                }
            ),
        ) as run_case,
    ):
        result = await runner.replay_case_run("case-run-old", actor=actor)

    assert result["id"] == "case-run-new"
    run_case.assert_awaited_once_with(
        "case-1",
        actor=SimpleNamespace(id="user-1"),
        replay_of_case_run_id="case-run-old",
        dependencies=None,
        definition_snapshot=source_definition,
        frozen_target={"kind": "agent", "id": "security-operations"},
        replay_from_snapshot=True,
    )


def test_resolve_suite_concurrency_defaults_to_agno_sequential(
    monkeypatch: pytest.MonkeyPatch,
):
    from api.services.agent_eval_runner import resolve_suite_concurrency

    monkeypatch.delenv("TAIS_EVAL_SUITE_CONCURRENCY", raising=False)
    assert resolve_suite_concurrency() == 1
    monkeypatch.setenv("TAIS_EVAL_SUITE_CONCURRENCY", "3")
    assert resolve_suite_concurrency() == 3
    assert resolve_suite_concurrency(1) == 1
    assert resolve_suite_concurrency(100) == 8  # hard cap
    assert resolve_suite_concurrency(0) == 1
    assert resolve_suite_concurrency(-3) == 1


def test_resolve_suite_default_timeout_and_case_override() -> None:
    from api.services.agent_eval_runner import (
        _case_timeout_seconds,
        resolve_suite_default_timeout,
    )

    assert resolve_suite_default_timeout() == 120
    assert resolve_suite_default_timeout(45) == 45
    assert resolve_suite_default_timeout(9_999) == 3_600
    assert resolve_suite_default_timeout(0) == 120
    assert _case_timeout_seconds({"timeout_seconds": 20}, 120) == 20
    assert _case_timeout_seconds({"timeout_seconds": None}, 120) == 120


@pytest.mark.asyncio
async def test_run_case_passes_judge_mode_to_agno_judge(monkeypatch):
    """Case.judge_mode maps directly to Agno AgentAsJudgeEval.scoring_strategy."""
    from api.services import agent_eval_runner as runner

    FakeJudgeEval.calls.clear()
    case = {
        "id": "case-1",
        "suite_id": "suite-1",
        "name": "judge numeric",
        "input": "probe",
        "criteria": "Must refuse",
        "judge_mode": "numeric",
        "threshold": 8,
        "eval_types": ["agent_as_judge"],
        "enabled": True,
        "metadata": {},
    }
    monkeypatch.setattr(runner.case_store, "get_case", AsyncMock(return_value=case))
    monkeypatch.setattr(
        runner.case_store,
        "create_case_run",
        AsyncMock(return_value={"id": "case-run-1"}),
    )
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
                        arun=AsyncMock(
                                return_value=SimpleNamespace(
                                    content="no",
                                    run_id="r",
                                    trace_id="t",
                                    status="completed",
                            )
                        )
                    )

                async def __aexit__(self, *_args):
                    return False

            return Ctx()

    deps = runner.AgentEvalRunnerDependencies(
        security_runtime=cast(Any, Runtime()),
        get_eval_db=lambda: "db",
        judge_eval_cls=FakeJudgeEval,
        **_configured_evaluator_model_kwargs(),
    )
    await runner.run_case("case-1", actor=SimpleNamespace(id="u1"), dependencies=deps)
    assert FakeJudgeEval.calls[0]["scoring_strategy"] == "numeric"
    assert FakeJudgeEval.calls[0]["threshold"] == 8


@pytest.mark.asyncio
async def test_claimed_suite_summary_is_aggregate_only_and_reuses_judge():
    """Judge model resolves once while CaseRun owns CaseResult-lite evidence."""
    import asyncio
    from api.services import agent_eval_runner as runner

    actor = SimpleNamespace(id="user-1")
    cases = [
        _case_stub("case-1", name="A"),
        _case_stub("case-2", name="B"),
        _case_stub("case-3", name="C", enabled=False),
    ]
    resolve_calls = 0
    configured_model = object()

    async def tracking_resolve(deps, config_id, *, required):
        del deps
        assert config_id == "test-evaluator-model"
        assert required is True
        nonlocal resolve_calls
        resolve_calls += 1
        return configured_model, config_id

    async def fake_run_case(
        case_id,
        actor,
        suite_run_id=None,
        replay_of_case_run_id=None,
        dependencies=None,
        judge_model_bundle=None,
        **_kwargs,
    ):
        assert judge_model_bundle == (configured_model, "test-evaluator-model")
        await asyncio.sleep(0.01)
        return {
            "id": f"cr-{case_id}",
            "case_id": case_id,
            "status": "passed" if case_id != "case-2" else "failed",
            "session_id": f"eval_cr-{case_id}",
            "duration_seconds": 1.25,
            "judge_passed": case_id == "case-1",
            "judge_reason": "Matches rubric"
            if case_id == "case-1"
            else "Misses rubric",
            "judge_score": 9 if case_id == "case-1" else 3,
            "reliability_passed": case_id == "case-1",
            "reliability_evidence": (
                {
                    "failed_tool_calls": ["unapproved_tool"],
                    "failed_argument_checks": [
                        {"raw_tool_args": "must not reach the Suite summary"}
                    ],
                }
                if case_id == "case-2"
                else None
            ),
            "judge_id": "agent_as_judge:inline+model:test-evaluator-model",
            "eval_profile": "full",
            "error_summary": "nope" if case_id == "case-2" else "",
        }

    snapshot = _execution_snapshot(
        *cases,
        tags=["safety"],
        judge_model_config_id="test-evaluator-model",
    )
    work_items = _case_work_items(snapshot, *cases)
    disabled_claim = runner.case_store.SuiteCaseRunClaim(
        case_run={**work_items[2], "status": "running"},
        acquired=True,
    )
    with (
        patch.object(
            runner.case_store,
            "claim_suite_case_run",
            new=AsyncMock(return_value=disabled_claim),
        ),
        patch.object(
            runner.case_store,
            "mark_case_run",
            new=AsyncMock(return_value={"id": work_items[2]["id"], "status": "skipped"}),
        ),
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value={}),
        ),
        patch.object(
            runner.case_store,
            "list_suite_runs",
            new=AsyncMock(return_value={"data": [], "meta": {"total_count": 0}}),
        ),
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "failed"}),
        ) as mark_suite,
        patch.object(runner, "run_case", side_effect=fake_run_case),
        patch.object(
            runner,
            "_resolve_judge_model_config",
            side_effect=tracking_resolve,
        ),
    ):
        result = await _execute_claimed_suite(
            runner,
            *cases,
            actor=actor,
            execution_snapshot=snapshot,
            case_work_items=work_items,
            concurrency=2,
        )

    assert resolve_calls == 1  # once per suite, not per case
    mark = mark_suite.await_args
    assert mark is not None
    summary = mark.kwargs["summary"]
    assert summary["passed"] == 1
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    assert summary["total"] == 3
    assert summary["concurrency"] == 2
    assert "safety" in summary
    assert "cases" not in summary
    assert result["status"] == "failed"


@pytest.mark.asyncio
async def test_safety_gate_can_fail_an_otherwise_passing_safety_suite():
    """A persisted aggregate gate must remain a real CI failure signal."""
    from api.services import agent_eval_runner as runner

    case = _case_stub(
        "case-1",
        name="benign control",
        metadata={"benign": True},
    )
    snapshot = _execution_snapshot(case, tags=["safety"])
    work_items = _case_work_items(snapshot, case)
    with (
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value={}),
        ),
        patch.object(
            runner.case_store,
            "list_suite_runs",
            new=AsyncMock(return_value={"data": [], "meta": {"total_count": 0}}),
        ),
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "failed"}),
        ) as mark_suite,
        patch.object(
            runner,
            "run_case",
            new=AsyncMock(return_value={"id": "case-run-1", "status": "passed"}),
        ),
        patch.object(
            runner,
            "_resolve_judge_model_config",
            new=AsyncMock(return_value=(None, "")),
        ),
        patch.object(
            runner,
            "evaluate_safety_gate",
            return_value={"status": "failed", "checks": []},
        ),
    ):
        result = await _execute_claimed_suite(
            runner,
            case,
            execution_snapshot=snapshot,
            case_work_items=work_items,
        )

    assert result["status"] == "failed"
    mark_call = mark_suite.await_args
    assert mark_call is not None
    assert mark_call.args[:2] == ("suite-run-1", "failed")
    assert mark_call.kwargs["summary"]["passed"] == 1
    assert mark_call.kwargs["summary"]["safety"]["gate"]["status"] == "failed"
    assert "Safety gate failed" in mark_call.kwargs["error_summary"]


def test_safety_baseline_selection_requires_matching_eval_identity():
    from api.services import agent_eval_runner as runner

    current_safety = {
        "pack_id": "fixture-synthetic",
        "pack_version": "2026.07.1",
        "pack_cases_sha256": "a" * 64,
        "judge_id": "agent_as_judge:refusal-v1@1.0.0+model:judge-a",
        "eval_profile": "tools_off",
        "asr": 0.2,
        "refusal_rate": 0.8,
    }
    current_summary = {"selected_tag": "smoke", "selected_name": None}
    history = [
        {
            "id": "wrong-sample",
            "status": "passed",
            "summary": {
                "selected_tag": "smoke",
                "selected_name": None,
                "safety": {
                    **current_safety,
                    "pack_cases_sha256": "b" * 64,
                },
            },
        },
        {
            "id": "wrong-profile",
            "status": "passed",
            "summary": {
                "selected_tag": "smoke",
                "safety": {**current_safety, "eval_profile": "full"},
            },
        },
        {
            "id": "wrong-selector",
            "status": "passed",
            "summary": {
                "selected_tag": "release",
                "safety": dict(current_safety),
            },
        },
        {
            "id": "baseline-1",
            "status": "failed",
            "summary": {
                "selected_tag": "smoke",
                "selected_name": None,
                "safety": {**current_safety, "asr": 0.1, "refusal_rate": 0.9},
            },
        },
    ]

    baseline, baseline_id = runner._compatible_safety_baseline(
        current_safety=current_safety,
        current_summary=current_summary,
        current_suite_run_id="current-run",
        historical_runs=history,
    )

    assert baseline_id == "baseline-1"
    assert baseline is not None
    assert baseline["asr"] == 0.1

    missing_identity, missing_id = runner._compatible_safety_baseline(
        current_safety={**current_safety, "pack_version": ""},
        current_summary=current_summary,
        current_suite_run_id="current-run",
        historical_runs=history,
    )
    assert missing_identity is None
    assert missing_id == ""

    missing_fingerprint, missing_fingerprint_id = runner._compatible_safety_baseline(
        current_safety={**current_safety, "pack_cases_sha256": ""},
        current_summary=current_summary,
        current_suite_run_id="current-run",
        historical_runs=history,
    )
    assert missing_fingerprint is None
    assert missing_fingerprint_id == ""


@pytest.mark.asyncio
async def test_claimed_suite_bounded_concurrency_limits_parallel_run_case():
    """Semaphore must bound in-flight run_case calls (measurable hot-path control)."""
    import asyncio
    from api.services import agent_eval_runner as runner

    actor = SimpleNamespace(id="user-1")
    cases = [_case_stub(f"case-{i}", name=f"C{i}") for i in range(4)]
    in_flight = 0
    max_in_flight = 0
    lock = asyncio.Lock()

    async def fake_run_case(
        case_id,
        actor,
        suite_run_id=None,
        replay_of_case_run_id=None,
        dependencies=None,
        judge_model_bundle=None,
        **_kwargs,
    ):
        nonlocal in_flight, max_in_flight
        async with lock:
            in_flight += 1
            max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.05)
        async with lock:
            in_flight -= 1
        return {
            "id": f"cr-{case_id}",
            "case_id": case_id,
            "status": "passed",
            "session_id": f"eval_{case_id}",
            "judge_id": "",
            "eval_profile": "full",
        }

    snapshot = _execution_snapshot(*cases)
    work_items = _case_work_items(snapshot, *cases)
    with (
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value={}),
        ),
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "sr-1", "status": "passed"}),
        ),
        patch.object(runner, "run_case", side_effect=fake_run_case),
        patch.object(
            runner,
            "_resolve_judge_model_config",
            new=AsyncMock(return_value=(None, "")),
        ),
    ):
        await _execute_claimed_suite(
            runner,
            *cases,
            actor=actor,
            execution_snapshot=snapshot,
            case_work_items=work_items,
            concurrency=2,
        )

    assert max_in_flight <= 2
    assert max_in_flight >= 2  # actually used parallelism


@pytest.mark.asyncio
async def test_claimed_suite_rejects_embedded_case_results() -> None:
    """A v2 SuiteRun has no second, stale summary result cache."""
    from api.services import agent_eval_runner as runner

    first = _case_stub("case-1", name="A")
    second = _case_stub("case-2", name="B")
    execution_snapshot = _execution_snapshot(first, second)
    work_items = _case_work_items(execution_snapshot, first, second)
    lease = runner.case_store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=1)
    existing = _claimed_suite_run(
        execution_snapshot,
        actor=SimpleNamespace(id="user-1"),
        summary={
            "cases": [
                {
                    "case_id": "case-1",
                    "name": "A",
                    "status": "passed",
                }
            ]
        },
    )

    with pytest.raises(ValueError, match="must not embed Case results"):
        await _execute_claimed_suite(
            runner,
            first,
            second,
            execution_snapshot=execution_snapshot,
            case_work_items=work_items,
            suite_run=existing,
            execution_lease=lease,
        )


@pytest.mark.asyncio
async def test_terminal_checkpoint_cas_conflict_reuses_the_winning_case_result() -> None:
    """A late worker must not turn its local result into SuiteRun progress."""
    from api.services import agent_eval_runner as runner

    case = _case_stub("case-1", name="Frozen first")
    target = runner._snapshot_target({"kind": "agent", "id": "security-operations"})
    winner_checkpoint = {
        "version": 1,
        "status": "passed",
        "duration_seconds": 0.321,
        "timeout_seconds": 120,
        "timed_out": False,
        "accuracy_passed": True,
        "accuracy_score": 9.0,
        "judge_passed": True,
        "judge_score": 9,
        "reliability_passed": True,
        "reliability_evidence": None,
        "performance": None,
        "judge_id": "winner-judge",
        "eval_profile": "tools_off",
    }
    winning_case_run = {
        "id": "case-run-1",
        "case_id": "case-1",
        "status": "passed",
        "session_id": "winner-session",
        "error_type": "",
        "error_summary": "",
        "definition_snapshot": case,
        "execution_provenance": {
            "target": target.to_dict(),
            "timeout_seconds": 120,
            "eval_profile": "tools_off",
        },
        "terminal_checkpoint": winner_checkpoint,
    }
    with (
        patch.object(
            runner.case_store,
            "mark_case_run",
            new=AsyncMock(return_value=None),
        ) as mark_case_run,
        patch.object(
            runner.case_store,
            "get_case_run_private",
            new=AsyncMock(return_value=winning_case_run),
        ) as get_private,
    ):
        result = await runner._complete_case_result(
            case_run_id="case-run-1",
            case_run={"id": "case-run-1", "status": "queued"},
            case=case,
            target=target,
            default_timeout=120,
            # These are deliberately the stale worker's contradictory local
            # observations. They must lose to the committed checkpoint above.
            status="failed",
            values={
                "error_type": "AccuracyFailed",
                "error_summary": "stale private evaluator reason",
            },
            started_at=0.0,
            timeout_seconds=120,
            timed_out=False,
            accuracy_passed=False,
            accuracy_reason="stale private accuracy reason",
            accuracy_score=1.0,
            judge_passed=False,
            judge_reason="stale private judge reason",
            judge_score=1,
            reliability_passed=False,
            reliability_evidence=None,
            performance=None,
            judge_id="stale-judge",
            eval_profile="tools_off",
        )

    mark_case_run.assert_awaited_once()
    get_private.assert_awaited_once_with("case-run-1")
    assert result["status"] == "passed"
    assert result["duration_seconds"] == 0.321
    assert result["accuracy_passed"] is True
    assert result["judge_passed"] is True
    assert result["judge_id"] == "winner-judge"
    assert result["judge_reason"] is None
    assert "stale private" not in str(result)


@pytest.mark.asyncio
async def test_fenced_terminal_checkpoint_rejection_is_a_lease_loss() -> None:
    from api.persistence.durable_jobs import JobLeaseLostError
    from api.services import agent_eval_runner as runner

    case = _case_stub("case-1")
    target = runner._snapshot_target({"kind": "agent", "id": "security-operations"})
    lease = runner.case_store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=1)
    with (
        patch.object(
            runner.case_store,
            "mark_case_run",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            runner.case_store,
            "get_case_run_private",
            new=AsyncMock(
                return_value={
                    "id": "case-run-1",
                    "case_id": "case-1",
                    "status": "running",
                }
            ),
        ),
        pytest.raises(JobLeaseLostError, match="rejected by a newer lease"),
    ):
        await runner._complete_case_result(
            case_run_id="case-run-1",
            case_run={"id": "case-run-1", "status": "running"},
            case=case,
            target=target,
            default_timeout=120,
            status="passed",
            values={},
            started_at=0.0,
            timeout_seconds=120,
            timed_out=False,
            accuracy_passed=True,
            accuracy_reason=None,
            accuracy_score=9.0,
            judge_passed=None,
            judge_reason=None,
            judge_score=None,
            reliability_passed=None,
            reliability_evidence=None,
            performance=None,
            judge_id="",
            eval_profile="full",
            execution_lease=lease,
        )


@pytest.mark.asyncio
async def test_claimed_suite_uses_a_terminal_checkpoint_as_recovery_evidence() -> None:
    """A committed CaseRun checkpoint avoids re-running its evaluator."""
    from api.services import agent_eval_runner as runner

    case = _case_stub("case-1", name="Frozen first")
    execution_snapshot = _execution_snapshot(case)
    work_items = _case_work_items(execution_snapshot, case)
    lease = runner.case_store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=1)
    terminal_case_run = {
        **work_items[0],
        "id": "case-run-1",
        "suite_run_id": "suite-run-1",
        "case_id": "case-1",
        "status": "passed",
        "session_id": "eval_case-run-1",
        "error_type": "",
        "error_summary": "",
        "terminal_checkpoint": {
            "version": 1,
            "status": "passed",
            "duration_seconds": 0.456,
            "timeout_seconds": 120,
            "timed_out": False,
            "accuracy_passed": True,
            "accuracy_score": 9.0,
            "judge_passed": True,
            "judge_score": 8,
            "reliability_passed": None,
            "reliability_evidence": None,
            "performance": None,
            "judge_id": "checkpoint-judge",
            "eval_profile": "full",
        },
    }
    with (
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "passed"}),
        ) as mark_suite,
        patch.object(runner, "run_case", new=AsyncMock()) as run_case,
        patch.object(
            runner,
            "_resolve_judge_model_config",
            new=AsyncMock(return_value=(None, "")),
        ) as resolve_judge,
    ):
        result = await _execute_claimed_suite(
            runner,
            case,
            execution_snapshot=execution_snapshot,
            case_work_items=[terminal_case_run],
            execution_lease=lease,
        )

    assert result["status"] == "passed"
    run_case.assert_not_awaited()
    resolve_judge.assert_not_awaited()
    mark_call = mark_suite.await_args
    assert mark_call is not None
    summary = mark_call.kwargs["summary"]
    assert summary["passed"] == 1
    assert "cases" not in summary


@pytest.mark.asyncio
async def test_claimed_suite_recovers_a_terminal_case_run_without_summary_cache() -> None:
    """Do not repeat an evaluator after its CaseRun committed before progress."""
    from api.services import agent_eval_runner as runner

    first = _case_stub(
        "case-1",
        name="Frozen first",
        input="frozen prompt",
        expected_output="private expected output",
    )
    second = _case_stub("case-2", name="Frozen second")
    execution_snapshot = _execution_snapshot(first, second)
    work_items = _case_work_items(execution_snapshot, first, second)
    lease = runner.case_store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=1)
    terminal_case_run = {
        **work_items[0],
        "id": "case-run-1",
        "suite_run_id": "suite-run-1",
        "case_id": "case-1",
        "status": "passed",
        "session_id": "eval_case-run-1",
        "error_type": "",
        "error_summary": "private error detail must not surface for a pass",
        "model_output": "private model output",
        "terminal_checkpoint": {
            "version": 1,
            "status": "passed",
            "duration_seconds": 1.234,
            "timeout_seconds": 120,
            "timed_out": False,
            "accuracy_passed": True,
            "accuracy_score": 9.5,
            "judge_passed": True,
            "judge_score": 9,
            "reliability_passed": True,
            "reliability_evidence": {"failed_tool_calls": ["unapproved_tool"]},
            "performance": {
                "warmup_runs": 1,
                "num_iterations": 3,
                "runtime_seconds": {"avg": 0.12, "median": 0.1, "p95": 0.2},
            },
            "judge_id": "agent_as_judge:refusal-v1@1.0.0+model:judge-a",
            "eval_profile": "tools_off",
        },
    }
    with (
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value={}),
        ),
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "passed"}),
        ) as mark_suite,
        patch.object(
            runner,
            "run_case",
            new=AsyncMock(
                return_value={
                    "id": "case-run-2",
                    "case_id": "case-2",
                    "status": "passed",
                }
            ),
        ) as run_case,
        patch.object(
            runner,
            "_resolve_judge_model_config",
            new=AsyncMock(return_value=(None, "")),
        ),
    ):
        result = await _execute_claimed_suite(
            runner,
            first,
            second,
            execution_snapshot=execution_snapshot,
            case_work_items=[terminal_case_run, work_items[1]],
            execution_lease=lease,
        )

    assert result["status"] == "passed"
    run_case.assert_awaited_once()
    run_case_call = run_case.await_args
    mark_suite_call = mark_suite.await_args
    assert run_case_call is not None
    assert mark_suite_call is not None
    assert run_case_call.args[0] == "case-2"
    summary = mark_suite_call.kwargs["summary"]
    assert summary["passed"] == 2
    assert "cases" not in summary
    assert "frozen prompt" not in str(summary)
    assert "private expected output" not in str(summary)
    assert "private model output" not in str(summary)
    assert "private error detail" not in str(summary)


@pytest.mark.asyncio
async def test_claimed_suite_uses_frozen_definition_after_edit_or_deletion() -> None:
    """Worker execution must not query editable Suite/Case definitions."""
    from api.services import agent_eval_runner as runner

    frozen_case = _case_stub("case-1", input="run this frozen prompt")
    execution_snapshot = _execution_snapshot(frozen_case, tags=["safety"])
    work_items = _case_work_items(execution_snapshot, frozen_case)
    lease = runner.case_store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=1)
    with (
        patch.object(
            runner.case_store,
            "get_suite",
            new=AsyncMock(),
        ) as get_suite,
        patch.object(
            runner.case_store,
            "get_case",
            new=AsyncMock(),
        ) as get_case,
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value={}),
        ),
        patch.object(
            runner.case_store,
            "list_suite_runs",
            new=AsyncMock(return_value={"data": [], "meta": {"total_count": 0}}),
        ),
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "passed"}),
        ),
        patch.object(
            runner,
            "run_case",
            new=AsyncMock(return_value={"id": "case-run-1", "status": "passed"}),
        ) as run_case,
        patch.object(
            runner,
            "_resolve_judge_model_config",
            new=AsyncMock(return_value=(None, "")),
        ),
    ):
        await _execute_claimed_suite(
            runner,
            frozen_case,
            execution_snapshot=execution_snapshot,
            case_work_items=work_items,
            execution_lease=lease,
        )

    get_suite.assert_not_awaited()
    get_case.assert_not_awaited()
    run_case_call = run_case.await_args
    assert run_case_call is not None
    assert run_case_call.kwargs["definition_snapshot"]["input"] == "run this frozen prompt"
    assert run_case_call.kwargs["frozen_target"].to_dict() == execution_snapshot[
        "target"
    ]


@pytest.mark.asyncio
async def test_claimed_suite_cancellation_skips_every_unstarted_case() -> None:
    """A durable cancellation remains terminal even before the worker starts."""
    from api.services import agent_eval_runner as runner

    cancellation_event = asyncio.Event()
    cancellation_event.set()
    first = _case_stub("case-1", name="A")
    second = _case_stub("case-2", name="B")
    execution_snapshot = _execution_snapshot(first, second)
    work_items = _case_work_items(execution_snapshot, first, second)
    lease = runner.case_store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=1)
    claims = iter(
        (
            runner.case_store.SuiteCaseRunClaim(
                case_run={"id": "case-run-1", "status": "running"},
                acquired=True,
            ),
            runner.case_store.SuiteCaseRunClaim(
                case_run={"id": "case-run-2", "status": "running"},
                acquired=True,
            ),
        )
    )
    with (
        patch.object(
            runner.case_store,
            "claim_suite_case_run",
            new=AsyncMock(side_effect=lambda *_args, **_kwargs: next(claims)),
        ),
        patch.object(
            runner.case_store,
            "mark_case_run",
            new=AsyncMock(side_effect=lambda case_run_id, status, _values, **_kwargs: {
                "id": case_run_id,
                "status": status,
            }),
        ) as mark_case,
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "cancelled"}),
        ) as mark_suite,
        patch.object(runner, "run_case", new=AsyncMock()) as run_case,
    ):
        result = await _execute_claimed_suite(
            runner,
            first,
            second,
            execution_snapshot=execution_snapshot,
            case_work_items=work_items,
            cancellation_event=cancellation_event,
            execution_lease=lease,
            status="cancelling",
        )

    assert result["status"] == "cancelled"
    run_case.assert_not_awaited()
    assert [call.args[1] for call in mark_case.await_args_list] == ["skipped", "skipped"]
    mark = mark_suite.await_args
    assert mark is not None
    assert mark.args[:2] == ("suite-run-1", "cancelled")
    assert mark.kwargs["expected_statuses"] == ("cancelling",)
    assert mark.kwargs["summary"]["skipped"] == 2


@pytest.mark.asyncio
async def test_claimed_cancellation_preserves_checkpointed_cases() -> None:
    """Cancellation skips only cases that never committed evaluator evidence."""
    from api.services import agent_eval_runner as runner

    cancellation_event = asyncio.Event()
    cancellation_event.set()
    lease = runner.case_store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=2)
    completed = _case_stub("case-1", name="Completed before cancellation")
    pending = _case_stub("case-2", name="Pending at cancellation")
    execution_snapshot = _execution_snapshot(completed, pending)
    work_items = _case_work_items(execution_snapshot, completed, pending)
    terminal_case_run = {
        **work_items[0],
        "id": "case-run-1",
        "suite_run_id": "suite-run-1",
        "case_id": "case-1",
        "status": "passed",
        "session_id": "eval_case-run-1_1",
        "error_type": "",
        "error_summary": "",
        "terminal_checkpoint": {
            "version": 1,
            "status": "passed",
            "duration_seconds": 0.42,
            "timeout_seconds": 120,
            "timed_out": False,
            "accuracy_passed": True,
            "accuracy_score": 9.0,
            "judge_passed": None,
            "judge_score": None,
            "reliability_passed": None,
            "reliability_evidence": None,
            "performance": None,
            "judge_id": "",
            "eval_profile": "full",
        },
    }
    pending_claim = runner.case_store.SuiteCaseRunClaim(
        case_run={
            "id": "case-run-2",
            "suite_run_id": "suite-run-1",
            "case_id": "case-2",
            "status": "running",
        },
        acquired=True,
    )
    with (
        patch.object(
            runner.case_store,
            "claim_suite_case_run",
            new=AsyncMock(return_value=pending_claim),
        ) as claim_case_run,
        patch.object(
            runner.case_store,
            "mark_case_run",
            new=AsyncMock(return_value={"id": "case-run-2", "status": "skipped"}),
        ) as mark_case_run,
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(),
        ) as progress,
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "cancelled"}),
        ) as mark_suite,
        patch.object(runner, "run_case", new=AsyncMock()) as run_case,
    ):
        result = await _execute_claimed_suite(
            runner,
            completed,
            pending,
            execution_snapshot=execution_snapshot,
            case_work_items=[terminal_case_run, work_items[1]],
            cancellation_event=cancellation_event,
            execution_lease=lease,
            status="cancelling",
        )

    assert result["status"] == "cancelled"
    run_case.assert_not_awaited()
    claim_case_run.assert_awaited_once()
    mark_case_run.assert_awaited_once()
    claim = claim_case_run.await_args
    skipped = mark_case_run.await_args
    assert claim is not None
    assert skipped is not None
    assert claim.args[0] == "case-2"
    assert skipped.args[1] == "skipped"
    progress.assert_not_awaited()
    marked = mark_suite.await_args
    assert marked is not None
    assert marked.args[:2] == ("suite-run-1", "cancelled")
    assert marked.kwargs["expected_statuses"] == ("cancelling",)
    assert marked.kwargs["execution_lease"] == lease
    summary = marked.kwargs["summary"]
    assert summary["passed"] == 1
    assert summary["skipped"] == 1
    assert "cases" not in summary


@pytest.mark.asyncio
async def test_claimed_suite_cancel_race_is_not_misclassified_as_lease_loss() -> None:
    """A cancelling SuiteRun can win just after a normal Case result arrives."""
    from api.services import agent_eval_runner as runner

    cancellation_event = asyncio.Event()
    lease = runner.case_store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=2)
    case = _case_stub("case-1")
    execution_snapshot = _execution_snapshot(case)
    work_items = _case_work_items(execution_snapshot, case)
    with (
        patch.object(
            runner,
            "run_case",
            new=AsyncMock(return_value={"id": "case-run-1", "status": "passed"}),
        ),
        patch.object(
            runner,
            "_resolve_judge_model_config",
            new=AsyncMock(return_value=(None, "")),
        ),
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value=None),
        ) as progress,
        patch.object(
            runner.case_store,
            "suite_run_cancel_requested",
            new=AsyncMock(return_value=True),
        ) as cancel_requested,
        patch.object(
            runner.case_store,
            "mark_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "cancelled"}),
        ) as mark_suite,
    ):
        result = await _execute_claimed_suite(
            runner,
            case,
            execution_snapshot=execution_snapshot,
            case_work_items=work_items,
            cancellation_event=cancellation_event,
            execution_lease=lease,
        )

    assert result["status"] == "cancelled"
    assert cancellation_event.is_set()
    progress.assert_awaited_once()
    cancel_requested.assert_awaited_once_with("suite-run-1")
    marked = mark_suite.await_args
    assert marked is not None
    assert marked.args[:2] == ("suite-run-1", "cancelled")
    assert marked.kwargs["expected_statuses"] == ("cancelling",)
    assert marked.kwargs["execution_lease"] == lease
    assert marked.kwargs["summary"]["passed"] == 1


@pytest.mark.asyncio
async def test_queued_suite_uses_private_snapshot_after_live_suite_changes() -> None:
    """The worker must not reread an edited/disabled editable Suite."""
    from api.services import agent_eval_runner as runner

    case = _case_stub("case-1")
    execution_snapshot = _execution_snapshot(case)
    work_items = _case_work_items(execution_snapshot, case)
    current_run = {
        "id": "suite-run-1",
        "suite_id": "suite-1",
        "started_by": "user-1",
        "status": "cancelling",
        "summary": {"cancel_requested": True, "completed_cases": 0},
    }
    completed_run = {**current_run, "status": "cancelled"}

    with (
        patch.object(
            runner.case_store,
            "suite_run_cancel_requested",
            new=AsyncMock(return_value=True),
        ),
        patch.object(
            runner.case_store,
            "claim_suite_run_execution",
            new=AsyncMock(return_value={**current_run, "execution_snapshot": execution_snapshot}),
        ),
        patch.object(
            runner.case_store,
            "list_suite_run_case_work_items_private",
            new=AsyncMock(return_value=work_items),
        ) as list_work_items,
        patch.object(
            runner,
            "_execute_claimed_suite_run",
            new=AsyncMock(return_value=completed_run),
        ) as execute_claimed,
        patch.object(
            runner.case_store,
            "get_suite",
            new=AsyncMock(),
        ) as get_suite,
    ):
        result = await runner.run_queued_suite_run(
            suite_run_id="suite-run-1",
            job_id="job-1",
            lease_epoch=1,
        )

    assert result == completed_run
    execute_call = execute_claimed.await_args
    assert execute_call is not None
    assert execute_call.kwargs["suite_run"]["id"] == "suite-run-1"
    assert execute_call.kwargs["actor"].id == "user-1"
    assert execute_call.kwargs["actor"].role == "user"
    assert execute_call.kwargs["actor"].is_superuser is False
    assert execute_call.kwargs["execution_snapshot"] == execution_snapshot
    assert execute_call.kwargs["case_work_items"] == work_items
    assert execute_call.kwargs["execution_lease"].job_id == "job-1"
    assert execute_call.kwargs["execution_lease"].lease_epoch == 1
    list_work_items.assert_awaited_once_with("suite-run-1")
    get_suite.assert_not_awaited()


@pytest.mark.asyncio
async def test_queued_suite_does_not_execute_after_a_newer_fence_claims_it() -> None:
    from api.persistence.durable_jobs import JobLeaseLostError
    from api.services import agent_eval_runner as runner

    with (
        patch.object(
            runner.case_store,
            "claim_suite_run_execution",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            runner.case_store,
            "get_suite_run",
            new=AsyncMock(return_value={"id": "suite-run-1", "status": "running"}),
        ),
        patch.object(
            runner,
            "_execute_claimed_suite_run",
            new=AsyncMock(),
        ) as execute_claimed,
    ):
        with pytest.raises(JobLeaseLostError, match="rejected by a newer lease"):
            await runner.run_queued_suite_run(
                suite_run_id="suite-run-1",
                job_id="job-1",
                lease_epoch=1,
            )

    execute_claimed.assert_not_awaited()


@pytest.mark.asyncio
async def test_fenced_suite_stops_when_an_old_progress_write_is_rejected() -> None:
    from api.persistence.durable_jobs import JobLeaseLostError
    from api.services import agent_eval_runner as runner

    case = _case_stub("case-1")
    snapshot = _execution_snapshot(case)
    work_items = _case_work_items(snapshot, case)
    lease = runner.case_store.SuiteRunExecutionLease(job_id="job-1", lease_epoch=1)
    with (
        patch.object(
            runner,
            "run_case",
            new=AsyncMock(return_value={"id": "case-run-1", "status": "passed"}),
        ) as run_case,
        patch.object(
            runner,
            "_resolve_judge_model_config",
            new=AsyncMock(return_value=(None, "")),
        ),
        patch.object(
            runner.case_store,
            "update_suite_run_progress",
            new=AsyncMock(return_value=None),
        ) as progress,
        patch.object(runner.case_store, "mark_suite_run", new=AsyncMock()) as mark_suite,
        pytest.raises(JobLeaseLostError, match="progress write was rejected"),
    ):
        await _execute_claimed_suite(
            runner,
            case,
            execution_snapshot=snapshot,
            case_work_items=work_items,
            execution_lease=lease,
        )

    run_case_call = run_case.await_args
    progress_call = progress.await_args
    assert run_case_call is not None
    assert progress_call is not None
    assert run_case_call.kwargs["execution_lease"] == lease
    assert progress_call.kwargs["execution_lease"] == lease
    mark_suite.assert_not_awaited()


@pytest.mark.asyncio
async def test_newer_epoch_wins_when_an_old_worker_finishes_after_takeover(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale worker cannot overwrite the newer epoch's CaseRun checkpoint."""
    from api.services import agent_eval_runner as runner

    case = _case_stub("case-1")
    old_lease = runner.case_store.SuiteRunExecutionLease(
        job_id="job-1", lease_epoch=1
    )
    new_lease = runner.case_store.SuiteRunExecutionLease(
        job_id="job-1", lease_epoch=2
    )
    old_started = asyncio.Event()
    release_old = asyncio.Event()
    active_epoch = 1
    claim_epochs: list[int] = []
    committed_epochs: list[int] = []
    rejected_epochs: list[int] = []
    subject_sessions: list[str] = []
    private_reads: list[str] = []
    terminal_case_run: dict[str, Any] | None = None
    configured_model = object()
    provenance = {
        "target": {"kind": "agent", "id": "security-operations"},
        "timeout_seconds": 120,
        "eval_profile": "full",
        "judge_model_config_id": "test-evaluator-model",
    }

    def claimed_case_run(epoch: int) -> dict[str, Any]:
        return {
            "id": "case-run-1",
            "suite_run_id": "suite-run-1",
            "case_id": "case-1",
            "status": "running",
            "lease_job_id": "job-1",
            "lease_epoch": epoch,
            "definition_snapshot": case,
            "execution_provenance": provenance,
            "terminal_checkpoint": {},
        }

    async def claim_suite_case_run(
        _case_id: str,
        *,
        suite_run_id: str,
        definition_snapshot: dict[str, Any],
        execution_provenance: dict[str, Any],
        execution_lease: Any,
    ) -> Any:
        nonlocal active_epoch
        assert suite_run_id == "suite-run-1"
        assert definition_snapshot == case
        assert execution_provenance["target"] == provenance["target"]
        claim_epochs.append(execution_lease.lease_epoch)
        if execution_lease == old_lease:
            assert active_epoch == 1
        else:
            assert execution_lease == new_lease
            assert active_epoch == 1
            active_epoch = 2
        return runner.case_store.SuiteCaseRunClaim(
            case_run=claimed_case_run(execution_lease.lease_epoch),
            acquired=True,
        )

    async def mark_case_run(
        case_run_id: str,
        status: str,
        values: dict[str, Any],
        *,
        execution_lease: Any = None,
    ) -> dict[str, Any] | None:
        nonlocal terminal_case_run
        assert case_run_id == "case-run-1"
        assert execution_lease is not None
        epoch = execution_lease.lease_epoch
        if epoch != active_epoch:
            rejected_epochs.append(epoch)
            return None
        assert terminal_case_run is None
        committed_epochs.append(epoch)
        terminal_case_run = {
            "id": case_run_id,
            "suite_run_id": "suite-run-1",
            "case_id": "case-1",
            "status": status,
            "session_id": values["session_id"],
            "agent_run_id": values["agent_run_id"],
            "trace_id": values["trace_id"],
            "agno_eval_run_ids": values["agno_eval_run_ids"],
            "error_type": values.get("error_type", ""),
            "error_summary": values.get("error_summary", ""),
            "definition_snapshot": case,
            "execution_provenance": provenance,
            "terminal_checkpoint": values["terminal_checkpoint"],
            "lease_job_id": execution_lease.job_id,
            "lease_epoch": epoch,
        }
        return dict(terminal_case_run)

    async def get_case_run_private(case_run_id: str) -> dict[str, Any] | None:
        assert case_run_id == "case-run-1"
        private_reads.append(case_run_id)
        return dict(terminal_case_run) if terminal_case_run is not None else None

    async def subject_arun(_input: str, *, session_id: str, **_kwargs: Any) -> Any:
        subject_sessions.append(session_id)
        if session_id.endswith("_1"):
            old_started.set()
            await release_old.wait()
            return SimpleNamespace(
                content="old result", status="completed", run_id="old-run", trace_id="old-trace"
            )
        assert session_id.endswith("_2")
        return SimpleNamespace(
            content="new result", status="completed", run_id="new-run", trace_id="new-trace"
        )

    class Runtime:
        def security_agent_context(self, _request: Any) -> Any:
            class Context:
                async def __aenter__(self) -> Any:
                    return SimpleNamespace(arun=subject_arun)

                async def __aexit__(self, *_args: Any) -> bool:
                    return False

            return Context()

    class Accuracy:
        def __init__(self, **_kwargs: Any) -> None:
            self.eval_id = "accuracy"

        async def arun_with_output(self, *, output: str, **_kwargs: Any) -> Any:
            if output == "old result":
                return SimpleNamespace(
                    avg_score=1.0,
                    results=[SimpleNamespace(score=1, reason="old worker verdict")],
                )
            assert output == "new result"
            return SimpleNamespace(
                avg_score=9.0,
                results=[SimpleNamespace(score=9, reason="new worker verdict")],
            )

    monkeypatch.setattr(runner.case_store, "claim_suite_case_run", claim_suite_case_run)
    monkeypatch.setattr(runner.case_store, "mark_case_run", mark_case_run)
    monkeypatch.setattr(runner.case_store, "get_case_run_private", get_case_run_private)
    dependencies = runner.AgentEvalRunnerDependencies(
        security_runtime=cast(Any, Runtime()),
        get_eval_db=lambda: "agno-db",
        accuracy_eval_cls=Accuracy,
        **_configured_evaluator_model_kwargs(configured_model),
    )

    old_task = asyncio.create_task(
        runner.run_case(
            "case-1",
            actor=SimpleNamespace(id="user-1"),
            suite_run_id="suite-run-1",
            definition_snapshot=case,
            frozen_target=provenance["target"],
            judge_model_bundle=(configured_model, "test-evaluator-model"),
            dependencies=dependencies,
            execution_lease=old_lease,
        )
    )
    try:
        await asyncio.wait_for(old_started.wait(), timeout=1)
        newer_result = await runner.run_case(
            "case-1",
            actor=SimpleNamespace(id="user-1"),
            suite_run_id="suite-run-1",
            definition_snapshot=case,
            frozen_target=provenance["target"],
            judge_model_bundle=(configured_model, "test-evaluator-model"),
            dependencies=dependencies,
            execution_lease=new_lease,
        )
    finally:
        release_old.set()
        if not old_task.done():
            await old_task
    older_result = old_task.result()

    assert claim_epochs == [1, 2]
    assert subject_sessions == ["eval_case-run-1_1", "eval_case-run-1_2"]
    assert committed_epochs == [2]
    assert rejected_epochs == [1]
    assert private_reads == ["case-run-1"]
    assert terminal_case_run is not None
    assert terminal_case_run["lease_epoch"] == 2
    assert terminal_case_run["status"] == "passed"
    assert terminal_case_run["session_id"] == "eval_case-run-1_2"
    assert newer_result["status"] == "passed"
    assert newer_result["accuracy_score"] == 9.0
    assert older_result["status"] == "passed"
    assert older_result["accuracy_score"] == 9.0
    assert "old worker verdict" not in str(older_result)


@pytest.mark.asyncio
async def test_claimed_suite_aborts_on_lost_lease_without_terminalizing_run() -> None:
    from api.persistence.durable_jobs import JobLeaseLostError
    from api.services import agent_eval_runner as runner

    lease_lost = asyncio.Event()
    lease_lost.set()

    case = _case_stub("case-1")
    with patch.object(runner.case_store, "mark_suite_run", new=AsyncMock()) as mark_suite:
        with pytest.raises(JobLeaseLostError, match="lost its durable job lease"):
            await _execute_claimed_suite(
                runner,
                case,
                abort_event=lease_lost,
            )

    mark_suite.assert_not_awaited()
