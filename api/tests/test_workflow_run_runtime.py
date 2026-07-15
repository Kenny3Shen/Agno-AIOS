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
