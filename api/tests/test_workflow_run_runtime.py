"""Critical workflow run runtime: stream lifecycle, cancel ownership, resume, cleanup."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from api.persistence.durable_jobs import JobKind
from api.services import workflow_run_runtime
from api.services.agent_tools import current_analysis_workspace


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
    assert "step.started" in names
    assert "step.completed" in names
    assert names[-1] == "workflow.completed"
    completed = next(event for event in events if event.event == "step.completed")
    assert completed.data["content"] == "triaged"


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
        # Cancel-before-start succeeds (AgentOS always stores intent).
        assert workflow_run_runtime.cancel_workflow_run(
            user_id="u1", run_id="missing-pre"
        )
        workflow_run_runtime._workflow_cancel_intent.discard(("u1", "missing-pre"))
    finally:
        workflow_run_runtime.unregister_workflow_run(user_id="u1", run_id="run-x")


def test_cancel_before_start_applied_on_register():
    class FakeCancellable:
        def __init__(self) -> None:
            self.cancelled: list[str] = []

        def cancel_run(self, run_id: str) -> bool:
            self.cancelled.append(run_id)
            return True

    assert workflow_run_runtime.cancel_workflow_run(user_id="u1", run_id="run-pre")
    workflow = FakeCancellable()
    workflow_run_runtime.register_workflow_run(
        user_id="u1", run_id="run-pre", workflow=workflow
    )
    try:
        assert workflow.cancelled == ["run-pre"]
    finally:
        workflow_run_runtime.unregister_workflow_run(user_id="u1", run_id="run-pre")


@pytest.mark.asyncio
async def test_stream_registers_and_unregisters_workflow():
    class TrackingWorkflow:
        def __init__(self) -> None:
            self.name = "reg"

        def cancel_run(self, run_id: str) -> bool:
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

    fake = TrackingWorkflow()
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
    assert events[0].event == "workflow.started"
    assert events[-1].event == "workflow.completed"
    # After stream completes, live registration is cleared.
    assert ("u1", "run-reg") not in workflow_run_runtime._active_workflows


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
async def test_workflow_run_binds_tools_to_one_workspace_and_cleans():
    """Compile + execute share one ephemeral workspace; path is removed after stream."""
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
