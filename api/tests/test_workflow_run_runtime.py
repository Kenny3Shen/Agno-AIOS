from types import SimpleNamespace
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from api.persistence.durable_jobs import JobKind
from api.services import workflow_run_runtime


class FakeWorkflow:
    def __init__(self):
        self.name = "demo"

    def arun(self, **_kwargs):
        async def _gen():
            yield SimpleNamespace(
                event="WorkflowStarted",
                run_id="run-1",
                session_id="sess-1",
                workflow_name="demo",
            )
            yield SimpleNamespace(
                event="ParallelExecutionStarted",
                run_id="run-1",
                session_id="sess-1",
                step_name="Fan-out",
                step_id="fanout",
                step_index=0,
                parallel_step_count=2,
            )
            yield SimpleNamespace(
                event="StepStarted",
                run_id="run-1",
                session_id="sess-1",
                step_name="Triage",
                step_id="triage",
                step_index=0,
            )
            yield SimpleNamespace(
                event="StepCompleted",
                run_id="run-1",
                session_id="sess-1",
                step_name="Triage",
                step_id="triage",
                step_index=0,
                content="triaged",
            )
            yield SimpleNamespace(
                event="ParallelExecutionCompleted",
                run_id="run-1",
                session_id="sess-1",
                step_name="Fan-out",
                step_id="fanout",
                parallel_step_count=2,
            )
            yield SimpleNamespace(
                event="ConditionExecutionStarted",
                run_id="run-1",
                session_id="sess-1",
                step_name="Branch",
                condition_result=True,
            )
            yield SimpleNamespace(
                event="ConditionExecutionCompleted",
                run_id="run-1",
                session_id="sess-1",
                step_name="Branch",
                condition_result=True,
                branch="then",
            )
            yield SimpleNamespace(
                event="LoopExecutionStarted",
                run_id="run-1",
                session_id="sess-1",
                step_name="Retry",
                max_iterations=2,
            )
            yield SimpleNamespace(
                event="LoopIterationStarted",
                run_id="run-1",
                session_id="sess-1",
                step_name="Retry",
                iteration=1,
                max_iterations=2,
            )
            yield SimpleNamespace(
                event="LoopIterationCompleted",
                run_id="run-1",
                session_id="sess-1",
                step_name="Retry",
                iteration=1,
                max_iterations=2,
                should_continue=False,
            )
            yield SimpleNamespace(
                event="LoopExecutionCompleted",
                run_id="run-1",
                session_id="sess-1",
                step_name="Retry",
                total_iterations=1,
                max_iterations=2,
            )
            yield SimpleNamespace(
                event="WorkflowCompleted",
                run_id="run-1",
                session_id="sess-1",
                content="done",
            )

        return _gen()


@pytest.mark.asyncio
async def test_stream_workflow_run_projects_lifecycle_events():
    with patch.object(
        workflow_run_runtime,
        "compile_workflow",
        new=AsyncMock(return_value=FakeWorkflow()),
    ):
        events = [
            event
            async for event in workflow_run_runtime.stream_workflow_run(
                workflow_id="wf-1",
                definition={"name": "demo", "steps": []},
                input_text="hello",
                user_id="u1",
                session_id="sess-1",
                run_id="run-1",
            )
        ]
    names = [event.event for event in events]
    assert names[0] == "workflow.started"
    assert names.count("workflow.started") == 1
    assert events[0].data.get("skills") == []
    assert "parallel.started" in names
    assert "step.started" in names
    assert "step.completed" in names
    assert "parallel.completed" in names
    assert "condition.started" in names
    assert "condition.completed" in names
    assert "loop.started" in names
    assert "loop.iteration.started" in names
    assert "loop.iteration.completed" in names
    assert "loop.completed" in names
    assert names[-1] == "workflow.completed"
    completed = next(event for event in events if event.event == "step.completed")
    assert completed.data["content"] == "triaged"
    condition = next(event for event in events if event.event == "condition.completed")
    assert condition.data["branch"] == "then"


@pytest.mark.asyncio
async def test_workflow_run_binds_tools_to_one_workspace_and_cleans():
    """Workflow compilation and execution see the same ephemeral directory."""
    from api.services.agent_catalog import get_agent_profile
    from api.services.agent_tools import (
        build_tools_for_profile,
        current_analysis_workspace,
    )

    captured: dict[str, object] = {}

    class ScopedWorkflow:
        name = "scoped"

        def arun(self, **_kwargs):
            async def _events():
                workspace = current_analysis_workspace()
                assert workspace is not None
                captured["executed_workspace"] = workspace.path
                assert workspace.path.exists()
                yield SimpleNamespace(
                    event="WorkflowCompleted",
                    run_id="workflow-scope-run",
                    session_id="workflow-scope-session",
                    content="done",
                )

            return _events()

    async def compile_scoped(*_args, **_kwargs):
        workspace = current_analysis_workspace()
        assert workspace is not None
        captured["compiled_workspace"] = workspace.path
        tools = build_tools_for_profile(get_agent_profile("data-analysis"))
        file_tool = next(tool for tool in tools if type(tool).__name__ == "FileTools")
        assert file_tool.base_dir == workspace.path
        return ScopedWorkflow()

    with patch.object(workflow_run_runtime, "compile_workflow", new=compile_scoped):
        events = [
            event
            async for event in workflow_run_runtime.stream_workflow_run(
                workflow_id="wf-scope",
                definition={"name": "scope", "steps": []},
                input_text="hello",
                user_id="u1",
                session_id="workflow-scope-session",
                run_id="workflow-scope-run",
            )
        ]

    assert events[-1].event == "workflow.completed"
    compiled = captured["compiled_workspace"]
    executed = captured["executed_workspace"]
    assert isinstance(compiled, Path)
    assert compiled == executed
    assert not compiled.exists()



class FakePausedWorkflow:
    def __init__(self):
        self.name = "paused-demo"

    def arun(self, **_kwargs):
        async def _gen():
            yield SimpleNamespace(
                event="WorkflowStarted",
                run_id="run-p",
                session_id="sess-p",
                workflow_name="paused-demo",
            )
            yield SimpleNamespace(
                event="WorkflowPaused",
                run_id="run-p",
                session_id="sess-p",
                paused_step_name="Gate",
                step_id="gate",
                content="Confirm gate",
            )

        return _gen()


@pytest.mark.asyncio
async def test_stream_workflow_paused_creates_approval():
    with (
        patch.object(
            workflow_run_runtime,
            "compile_workflow",
            new=AsyncMock(return_value=FakePausedWorkflow()),
        ),
        patch.object(
            workflow_run_runtime,
            "_create_workflow_step_approval",
            new=AsyncMock(return_value="appr-1"),
        ) as create_appr,
    ):
        events = [
            event
            async for event in workflow_run_runtime.stream_workflow_run(
                workflow_id="wf-p",
                definition={"name": "p", "steps": []},
                input_text="x",
                user_id="u1",
                session_id="sess-p",
                run_id="run-p",
            )
        ]
    names = [event.event for event in events]
    assert names[-1] == "workflow.paused"
    paused = events[-1]
    assert paused.data["approval_id"] == "appr-1"
    create_appr.assert_awaited_once()


def test_cancel_workflow_run_requires_registered_owner():
    class FakeCancellable:
        def __init__(self) -> None:
            self.cancelled: list[str] = []

        def cancel_run(self, run_id: str) -> bool:
            self.cancelled.append(run_id)
            return True

    workflow = FakeCancellable()
    workflow_run_runtime.register_workflow_run(
        user_id="u1", run_id="run-x", workflow=workflow
    )
    try:
        assert not workflow_run_runtime.cancel_workflow_run(user_id="u2", run_id="run-x")
        assert workflow.cancelled == []
        assert workflow_run_runtime.cancel_workflow_run(user_id="u1", run_id="run-x")
        assert workflow.cancelled == ["run-x"]
        assert not workflow_run_runtime.cancel_workflow_run(user_id="u1", run_id="missing")
    finally:
        workflow_run_runtime.unregister_workflow_run(user_id="u1", run_id="run-x")


@pytest.mark.asyncio
async def test_schedule_workflow_resume_enqueues_one_idempotent_job() -> None:
    job = object()
    with patch.object(
        workflow_run_runtime,
        "enqueue_durable_job",
        new=AsyncMock(return_value=job),
    ) as enqueue:
        scheduled = await workflow_run_runtime.schedule_workflow_resume(" approval-1 ")

    assert scheduled is job
    enqueue.assert_awaited_once_with(
        kind=JobKind.WORKFLOW_RESUME,
        payload={"approval_id": "approval-1"},
        idempotency_key="workflow-resume:approval-1",
    )


@pytest.mark.asyncio
async def test_schedule_workflow_resume_requires_approval_id() -> None:
    with pytest.raises(ValueError, match="approval_id is required"):
        await workflow_run_runtime.schedule_workflow_resume(" ")


@pytest.mark.asyncio
async def test_resume_canonicalizes_legacy_persisted_skill_before_compiling() -> None:
    class ApprovalDb:
        async def get_approval(self, approval_id: str):
            assert approval_id == "approval-1"
            return {
                "source_type": "workflow",
                "workflow_id": "wf-1",
                "run_id": "run-1",
                "session_id": "session-1",
                "status": "approved",
                "context": {},
            }

    workflow = SimpleNamespace(aget_run_output=AsyncMock(return_value=None))
    compile = AsyncMock(return_value=workflow)
    legacy_definition = {
        "name": "Historic workflow",
        "steps": [
            {
                "id": "triage",
                "type": "step",
                "executor": {"kind": "agent", "ref": "security-operations"},
                "skills": ["playbook-skill", "cve-intel-skill"],
            }
        ],
    }
    with (
        patch.object(
            workflow_run_runtime,
            "get_async_agno_postgres_db",
            return_value=ApprovalDb(),
        ),
        patch.object(
            workflow_run_runtime.workflow_store,
            "get_workflow",
            new=AsyncMock(return_value={"definition": legacy_definition}),
        ),
        patch.object(workflow_run_runtime, "compile_workflow", new=compile),
    ):
        with pytest.raises(ValueError, match="Paused run run-1 not found"):
            await workflow_run_runtime.resume_workflow_run("approval-1")

    compile_call = compile.await_args
    assert compile_call is not None
    definition = compile_call.args[0]
    assert definition["steps"][0]["skills"] == ["cve-intel-skill"]


@pytest.mark.asyncio
async def test_workflow_resume_uses_fresh_workspace_and_cleans() -> None:
    from api.services.agent_catalog import get_agent_profile
    from api.services.agent_tools import (
        build_tools_for_profile,
        current_analysis_workspace,
    )

    class ApprovalDb:
        async def get_approval(self, _approval_id: str):
            return {
                "source_type": "workflow",
                "workflow_id": "wf-resume-scope",
                "run_id": "workflow-resume-run",
                "session_id": "workflow-resume-session",
                "status": "approved",
                "context": {},
            }

    captured: dict[str, Path] = {}

    async def compile_scoped(*_args, **_kwargs):
        workspace = current_analysis_workspace()
        assert workspace is not None
        captured["workspace"] = workspace.path
        tools = build_tools_for_profile(get_agent_profile("data-analysis"))
        assert any(type(tool).__name__ == "FileTools" for tool in tools)
        return SimpleNamespace(aget_run_output=AsyncMock(return_value=None))

    with (
        patch.object(
            workflow_run_runtime,
            "get_async_agno_postgres_db",
            return_value=ApprovalDb(),
        ),
        patch.object(
            workflow_run_runtime.workflow_store,
            "get_workflow",
            new=AsyncMock(return_value={"definition": {"name": "x", "steps": []}}),
        ),
        patch.object(workflow_run_runtime, "compile_workflow", new=compile_scoped),
    ):
        with pytest.raises(ValueError, match="Paused run workflow-resume-run not found"):
            await workflow_run_runtime.resume_workflow_run("approval-scope")

    assert not captured["workspace"].exists()


@pytest.mark.asyncio
async def test_stream_registers_and_unregisters_workflow():
    class FakeWorkflow:
        def __init__(self) -> None:
            self.name = "reg"
            self.cancelled: list[str] = []

        def cancel_run(self, run_id: str) -> bool:
            self.cancelled.append(run_id)
            return True

        def arun(self, **_kwargs):
            async def _gen():
                yield SimpleNamespace(
                    event="WorkflowStarted",
                    run_id="run-reg",
                    session_id="sess-reg",
                    workflow_name="reg",
                )
                yield SimpleNamespace(
                    event="WorkflowCompleted",
                    run_id="run-reg",
                    session_id="sess-reg",
                    content="ok",
                )

            return _gen()

    fake = FakeWorkflow()
    with patch.object(
        workflow_run_runtime,
        "compile_workflow",
        new=AsyncMock(return_value=fake),
    ):
        events = [
            event
            async for event in workflow_run_runtime.stream_workflow_run(
                workflow_id="wf-reg",
                definition={"name": "reg", "steps": []},
                input_text="x",
                user_id="u1",
                session_id="sess-reg",
                run_id="run-reg",
            )
        ]
    assert [e.event for e in events][0] == "workflow.started"
    assert events[-1].event == "workflow.completed"
    # After stream completes, cancel should miss (unregistered).
    assert not workflow_run_runtime.cancel_workflow_run(user_id="u1", run_id="run-reg")


@pytest.mark.asyncio
async def test_workflow_preflight_includes_nested_workflow_skill_bindings():
    root = {
        "name": "root",
        "steps": [
            {"type": "step", "skills": ["root-skill"]},
            {"type": "workflow_ref", "workflow_id": "nested-1"},
        ],
    }
    nested = {
        "name": "nested",
        "steps": [{"type": "step", "skills": ["nested-skill"]}],
    }
    preflight = AsyncMock(return_value=[])
    with (
        patch.object(
            workflow_run_runtime.workflow_store,
            "get_workflow",
            AsyncMock(return_value={"definition": nested}),
        ),
        patch.object(
            workflow_run_runtime,
            "canonicalize_workflow_definition",
            return_value=nested,
        ),
        patch.object(
            workflow_run_runtime,
            "required_skill_issues_for_actor",
            preflight,
        ),
    ):
        issues = await workflow_run_runtime.workflow_capability_issues(
            actor=SimpleNamespace(id="u1", role="user", is_superuser=False),
            definition=root,
        )

    assert issues == []
    assert preflight.await_args is not None
    assert preflight.await_args.args[1] == ["root-skill", "nested-skill"]
