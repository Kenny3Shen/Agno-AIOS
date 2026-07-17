from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

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
