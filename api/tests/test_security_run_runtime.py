"""Business-critical Chat runtime tests: leave-page, reattach, supersede, cancel."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator, cast
from unittest.mock import patch

import anyio
import pytest

from api.services import security_run_runtime
from api.services.chat_run_events import ChatRunEvent


class EventAgent:
    def __init__(self) -> None:
        self.cancelled_run_ids: list[str] = []

    def cancel_run(self, run_id: str) -> bool:
        self.cancelled_run_ids.append(run_id)
        return True

    async def arun(self, *_args, **_kwargs):
        yield {
            "event": "RunStarted",
            "run_id": "run-1",
            "session_id": "session-1",
            "model": "test-model",
            "model_provider": "test",
        }
        yield {
            "event": "RunCompleted",
            "run_id": "run-1",
            "session_id": "session-1",
            "metrics": {},
            "citations": [],
            "followups": [],
        }


@pytest.mark.asyncio
async def test_mid_run_client_disconnect_does_not_cancel_runner():
    """Leaving the page aborts SSE mid-run; Agno must keep going (COMPLETED)."""
    started = asyncio.Event()
    finished = asyncio.Event()
    cancelled: list[str] = []

    class SlowAgent:
        def cancel_run(self, run_id: str) -> bool:
            cancelled.append(run_id)
            return True

        async def arun(self, *_args, **_kwargs):
            yield {
                "event": "RunStarted",
                "run_id": "run-leave",
                "session_id": "s1",
                "model": "m",
                "model_provider": "p",
            }
            started.set()
            await asyncio.sleep(0.2)
            yield {"event": "RunContent", "run_id": "run-leave", "content": "still working"}
            yield {
                "event": "RunCompleted",
                "run_id": "run-leave",
                "session_id": "s1",
                "metrics": {},
                "citations": [],
                "followups": [],
            }
            finished.set()

    runtime = security_run_runtime.SecurityRunRuntime()
    stream = cast(
        AsyncGenerator[ChatRunEvent, None],
        runtime._stream_agent_events(
            SlowAgent(),
            security_run_runtime.SecurityRunRequest.from_chat_args(
                "hello", session_id="s1", user_id="u1"
            ),
        ),
    )
    events = []
    async for event in stream:
        events.append(event)
        if event.event == "run.started":
            break
    await stream.aclose()
    await asyncio.wait_for(finished.wait(), timeout=2.0)
    assert any(event.event == "run.started" for event in events)
    assert cancelled == []


@pytest.mark.asyncio
async def test_request_task_cancel_mid_run_does_not_cancel_runner():
    """Starlette cancels the request task when the SSE client disconnects."""
    started = asyncio.Event()
    finished = asyncio.Event()
    cancelled: list[str] = []
    producer_cancelled = asyncio.Event()

    class SlowAgent:
        def cancel_run(self, run_id: str) -> bool:
            cancelled.append(run_id)
            return True

        async def arun(self, *_args, **_kwargs):
            yield {
                "event": "RunStarted",
                "run_id": "run-task-cancel",
                "session_id": "s1",
                "model": "m",
                "model_provider": "p",
            }
            started.set()
            try:
                await asyncio.sleep(0.35)
            except asyncio.CancelledError:
                producer_cancelled.set()
                raise
            yield {"event": "RunContent", "run_id": "run-task-cancel", "content": "x"}
            yield {
                "event": "RunCompleted",
                "run_id": "run-task-cancel",
                "session_id": "s1",
                "metrics": {},
                "citations": [],
                "followups": [],
            }
            finished.set()

    runtime = security_run_runtime.SecurityRunRuntime()

    async def consume() -> None:
        stream = cast(
            AsyncGenerator[ChatRunEvent, None],
            runtime._stream_agent_events(
                SlowAgent(),
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "hello", session_id="s1", user_id="u1"
                ),
            ),
        )
        async for event in stream:
            if event.event == "run.started":
                async for _ in stream:
                    pass
                return

    task = asyncio.create_task(consume())
    await started.wait()
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(finished.wait(), timeout=2.0)
    assert cancelled == []
    assert not producer_cancelled.is_set()


@pytest.mark.asyncio
async def test_stream_security_run_survives_anyio_cancel_without_cancelling_agno():
    """Leave-page: sse-starlette anyio cancel must not store Operation cancelled by user."""
    started = asyncio.Event()
    finished = asyncio.Event()
    cancelled: list[str] = []
    producer_cancelled = asyncio.Event()
    terminal_events: list[str] = []

    class SlowAgent:
        def cancel_run(self, run_id: str) -> bool:
            cancelled.append(run_id)
            return True

        async def arun(self, *_args, **_kwargs):
            yield {
                "event": "RunStarted",
                "run_id": "run-detached-leave",
                "session_id": "s1",
                "model": "m",
                "model_provider": "p",
            }
            started.set()
            try:
                await asyncio.sleep(0.3)
            except asyncio.CancelledError:
                producer_cancelled.set()
                raise
            yield {
                "event": "RunContent",
                "run_id": "run-detached-leave",
                "content": "still working after leave",
            }
            yield {
                "event": "RunCompleted",
                "run_id": "run-detached-leave",
                "session_id": "s1",
                "metrics": {},
                "citations": [],
                "followups": [],
            }
            finished.set()

    runtime = security_run_runtime.SecurityRunRuntime()

    async def fake_stream(request):  # noqa: ANN001
        async for event in runtime._stream_agent_events(SlowAgent(), request):
            terminal_events.append(event.event)
            yield event

    with patch.object(runtime, "stream", side_effect=fake_stream):

        async def consume() -> None:
            stream = cast(
                AsyncGenerator[ChatRunEvent, None],
                security_run_runtime.stream_security_run(
                    security_run_runtime.SecurityRunRequest.from_chat_args(
                        "hello", session_id="s1", user_id="u1"
                    ),
                    runtime=runtime,
                ),
            )
            async for event in stream:
                if event.event == "run.started":
                    await asyncio.sleep(30)

        with anyio.CancelScope() as scope:
            consumer = asyncio.create_task(consume())
            await started.wait()
            await asyncio.sleep(0.02)
            scope.cancel()
            with pytest.raises((asyncio.CancelledError, anyio.get_cancelled_exc_class())):
                await consumer

        await asyncio.wait_for(finished.wait(), timeout=2.0)

        async def _has_completed() -> bool:
            while "run.completed" not in terminal_events:
                await asyncio.sleep(0.02)
            return True

        await asyncio.wait_for(_has_completed(), timeout=2.0)

    assert cancelled == []
    assert not producer_cancelled.is_set()
    assert "run.completed" in terminal_events
    assert "run.cancelled" not in terminal_events


@pytest.mark.asyncio
async def test_new_stream_on_same_session_supersedes_detached_worker():
    """Regenerate after leave-page must stop the prior detached Agno run."""
    first_started = asyncio.Event()
    second_finished = asyncio.Event()
    cancelled: list[str] = []

    class FirstAgent:
        def cancel_run(self, run_id: str) -> bool:
            cancelled.append(run_id)
            return True

        async def arun(self, *_args, **_kwargs):
            yield {
                "event": "RunStarted",
                "run_id": "run-old",
                "session_id": "s-regen",
                "model": "m",
                "model_provider": "p",
            }
            first_started.set()
            await asyncio.sleep(2.0)
            yield {
                "event": "RunContent",
                "run_id": "run-old",
                "content": "stale answer that must not win",
            }
            yield {
                "event": "RunCompleted",
                "run_id": "run-old",
                "session_id": "s-regen",
                "metrics": {},
                "citations": [],
                "followups": [],
            }

    class SecondAgent:
        def cancel_run(self, run_id: str) -> bool:
            cancelled.append(run_id)
            return True

        async def arun(self, *_args, **_kwargs):
            yield {
                "event": "RunStarted",
                "run_id": "run-new",
                "session_id": "s-regen",
                "model": "m",
                "model_provider": "p",
            }
            await asyncio.sleep(0.05)
            yield {
                "event": "RunContent",
                "run_id": "run-new",
                "content": "fresh regenerate answer",
            }
            yield {
                "event": "RunCompleted",
                "run_id": "run-new",
                "session_id": "s-regen",
                "metrics": {},
                "citations": [],
                "followups": [],
            }
            second_finished.set()

    runtime = security_run_runtime.SecurityRunRuntime()
    request = security_run_runtime.SecurityRunRequest.from_chat_args(
        "hello", session_id="s-regen", user_id="u1"
    )

    async def run_first() -> list[str]:
        return [
            event.event
            async for event in runtime._stream_agent_events(FirstAgent(), request)
        ]

    first_task = asyncio.create_task(run_first())
    await first_started.wait()
    await asyncio.sleep(0.05)

    second_events = [
        event.event
        async for event in runtime._stream_agent_events(SecondAgent(), request)
    ]
    first_events = await asyncio.wait_for(first_task, timeout=2.0)
    await asyncio.wait_for(second_finished.wait(), timeout=2.0)

    assert "run.completed" in second_events
    assert "run.cancelled" in first_events
    assert "run.completed" not in first_events
    assert "run-old" in cancelled
    assert "run.cancelled" not in second_events


@pytest.mark.asyncio
async def test_live_hub_reattach_receives_catchup_and_live_events():
    """Leave-page consumer drops; a second subscriber gets buffer + remaining live."""
    mid = asyncio.Event()
    finished = asyncio.Event()

    class SlowAgent:
        def cancel_run(self, run_id: str) -> bool:
            return True

        async def arun(self, *_args, **_kwargs):
            yield {
                "event": "RunStarted",
                "run_id": "run-live",
                "session_id": "s-live",
                "model": "m",
                "model_provider": "p",
            }
            yield {"event": "RunContent", "run_id": "run-live", "content": "hello "}
            mid.set()
            await asyncio.sleep(0.15)
            yield {"event": "RunContent", "run_id": "run-live", "content": "world"}
            yield {
                "event": "RunCompleted",
                "run_id": "run-live",
                "session_id": "s-live",
                "metrics": {},
                "citations": [],
                "followups": [],
            }
            finished.set()

    runtime = security_run_runtime.SecurityRunRuntime()
    request = security_run_runtime.SecurityRunRequest.from_chat_args(
        "hi", session_id="s-live", user_id="u1"
    )

    async def fake_stream(_request):
        async for event in runtime._stream_agent_events(SlowAgent(), request):
            yield event

    with patch.object(runtime, "stream", side_effect=fake_stream):
        primary = cast(
            AsyncGenerator[ChatRunEvent, None],
            security_run_runtime.stream_security_run(request, runtime=runtime),
        )
        async for event in primary:
            if event.event == "content.delta":
                break
        await primary.aclose()

        await mid.wait()
        assert security_run_runtime.has_live_security_run(
            user_id="u1", session_id="s-live", runtime=runtime
        )

        reattach_events = [
            event.event
            async for event in security_run_runtime.attach_live_security_run(
                user_id="u1", session_id="s-live", runtime=runtime
            )
        ]
        await asyncio.wait_for(finished.wait(), timeout=2.0)

    assert "run.started" in reattach_events
    assert reattach_events.count("content.delta") >= 1
    assert "run.completed" in reattach_events


def test_runtime_cancellation_requires_the_matching_user_and_live_run():
    runtime = security_run_runtime.SecurityRunRuntime()
    agent = EventAgent()
    runtime.register_run(user_id="u1", run_id="run-1", agent=agent)

    assert not runtime.cancel_run(user_id="u2", run_id="run-1")
    assert runtime.cancel_run(user_id="u1", run_id="run-1")
    assert agent.cancelled_run_ids == ["run-1"]
    # Unknown run without stream cancel event → 404 semantics (not AgentOS open cancel).
    assert not runtime.cancel_run(user_id="u1", run_id="ghost-run")


@pytest.mark.asyncio
async def test_live_hub_last_event_index_skips_catchup():
    """AgentOS-style resume: last_event_index skips already-seen frames."""
    hub = security_run_runtime._LiveChatStreamHub()
    await hub.publish(ChatRunEvent("run.started", {"run_id": "r1"}))
    await hub.publish(ChatRunEvent("content.delta", {"run_id": "r1", "delta": "a"}))
    await hub.publish(ChatRunEvent("content.delta", {"run_id": "r1", "delta": "b"}))
    await hub.finish()

    # Full catch-up
    all_events = [e async for e in hub.subscribe()]
    assert len(all_events) == 3
    assert all(isinstance(e.data.get("event_index"), int) for e in all_events)
    assert [e.data["event_index"] for e in all_events] == [0, 1, 2]

    # Skip first two (indices 0,1)
    partial = [e async for e in hub.subscribe(last_event_index=1)]
    assert len(partial) == 1
    assert partial[0].data.get("delta") == "b"
    assert partial[0].data["event_index"] == 2


@pytest.mark.asyncio
async def test_acancel_run_prefers_async_runner_method():
    runtime = security_run_runtime.SecurityRunRuntime()
    calls: list[str] = []

    class AsyncCancelAgent:
        async def acancel_run(self, run_id: str) -> bool:
            calls.append(f"a:{run_id}")
            return True

        def cancel_run(self, run_id: str) -> bool:
            calls.append(f"s:{run_id}")
            return True

    agent = AsyncCancelAgent()
    runtime.register_run(user_id="u1", run_id="run-async", agent=agent)
    assert await runtime.acancel_run(user_id="u1", run_id="run-async")
    assert calls == ["a:run-async"]


def test_supersede_session_stream_cancels_prior_cancel_event():
    runtime = security_run_runtime.SecurityRunRuntime()
    prior = asyncio.Event()
    runtime._session_stream_cancels[("u1", "s1")] = prior
    runtime.register_run(
        user_id="u1",
        run_id="run-prior",
        agent=EventAgent(),
        cancel_event=prior,
        session_id="s1",
    )
    keep = asyncio.Event()
    assert runtime.supersede_session_stream(
        user_id="u1", session_id="s1", keep_cancel=keep
    )
    assert prior.is_set()
    assert not keep.is_set()


@pytest.mark.asyncio
async def test_stream_agent_events_projects_safe_ui_events():
    """UI stream must not leak raw tool I/O by default."""
    runtime = security_run_runtime.SecurityRunRuntime()
    events = [
        event
        async for event in runtime._stream_agent_events(
            EventAgent(),
            security_run_runtime.SecurityRunRequest.from_chat_args(
                "hello", session_id="session-1", user_id="u1"
            ),
        )
    ]
    types = [event.event for event in events]
    assert "run.started" in types
    assert "run.completed" in types
    # Tool updates exist but raw secret payloads stay scrubbed by chat_run_events.
    tool_events = [event for event in events if event.event == "tool.update"]
    for event in tool_events:
        tool = event.data.get("tool") or {}
        assert "secret" not in str(tool.get("input") or "")
        assert "sensitive" not in str(tool.get("output") or "")
