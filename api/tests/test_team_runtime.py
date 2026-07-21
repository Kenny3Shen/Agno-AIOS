"""Critical Team runtime behaviors: feature gate, tools-off, cancel, disconnect."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from api.services.team_runtime import build_team, team_feature_enabled


@pytest.mark.asyncio
async def test_stream_team_disabled_fails(monkeypatch):
    """Feature flag off must fail closed with TEAM_DISABLED (not silent fallback)."""
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    req = srr.SecurityRunRequest.from_chat_args(
        "x", agent_id="research-analysis-team", enable_tools=True
    )
    assert req.agent_id == "research-analysis-team"
    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "0")
    assert team_feature_enabled() is False

    async def fake_settings():
        from api.services.chat_settings_service import ChatSettings

        return ChatSettings(
            show_raw_reasoning=False,
            show_raw_tool_io=False,
            show_thought_chain=True,
        )

    monkeypatch.setattr(srr, "get_chat_settings_async", fake_settings)
    # stream() also imports the name through chat_settings_service in some paths.
    monkeypatch.setattr(
        "api.services.chat_settings_service.get_chat_settings_async",
        fake_settings,
    )
    events = [
        event
        async for event in srr.DEFAULT_SECURITY_RUN_RUNTIME.stream(req)
    ]
    assert any(
        e.event == "run.failed" and e.data.get("code") == "TEAM_DISABLED" for e in events
    )


@pytest.mark.asyncio
async def test_stream_team_enable_tools_false_skips_member_tools(monkeypatch):
    """enable_tools=False must not mount member tools from profiles."""
    from api.services import team_runtime as tr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    created_tools: list[list] = []

    def fake_agent(**kwargs):
        created_tools.append(list(kwargs.get("tools") or []))
        return SimpleNamespace(**kwargs)

    class FakeTeam:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.members = kwargs.get("members") or []

    async def fake_get_model(_model_id=None):
        return {"provider": "openai-compatible", "model_id": "fake"}

    async def fake_chat_settings():
        from api.services.chat_settings_service import ChatSettings

        return ChatSettings()

    monkeypatch.setattr(tr, "Agent", fake_agent)
    monkeypatch.setattr(tr, "Team", FakeTeam)
    monkeypatch.setattr(tr, "get_model_for_run", fake_get_model)
    monkeypatch.setattr(tr, "build_agno_model", lambda *_a, **_k: object())
    monkeypatch.setattr(tr, "get_async_agno_postgres_db", lambda: None)
    monkeypatch.setattr(tr, "build_tools_for_profile", lambda _p: ["tool"])
    monkeypatch.setattr(tr, "get_chat_settings_async", fake_chat_settings)

    await build_team("research-analysis-team", enable_tools=False)
    assert created_tools
    assert all(tools == [] for tools in created_tools)

    created_tools.clear()
    await build_team("research-analysis-team", enable_tools=True)
    assert any(tools == ["tool"] for tools in created_tools)


@pytest.mark.asyncio
async def test_stream_cancel_during_team_emits_single_cancelled(monkeypatch):
    """Cancel mid-stream must invoke runner cancel and emit one run.cancelled."""
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    runtime = srr.SecurityRunRuntime()

    class SlowTeam:
        def __init__(self):
            self.cancelled: list[str] = []
            self.gate = asyncio.Event()

        def cancel_run(self, run_id: str) -> bool:
            self.cancelled.append(run_id)
            self.gate.set()
            return True

        async def arun(self, *_args, **_kwargs):
            yield SimpleNamespace(
                event="TeamRunStarted",
                run_id="team-run-cancel",
                session_id="s1",
                team_id="research-analysis-team",
                model="m",
                model_provider="p",
            )
            await self.gate.wait()
            await asyncio.sleep(0.05)
            yield SimpleNamespace(
                event="TeamRunContent",
                run_id="team-run-cancel",
                team_id="research-analysis-team",
                content="should not appear",
            )

    team = SlowTeam()
    request = srr.SecurityRunRequest.from_chat_args(
        "x",
        session_id="s1",
        user_id="u-cancel",
        agent_id="research-analysis-team",
    )
    settings = SimpleNamespace(
        show_raw_reasoning=False,
        show_raw_tool_io=False,
        show_thought_chain=True,
    )
    events: list = []

    async def _consume():
        async for event in runtime._stream_agent_events(team, request, settings):
            events.append(event)
            if event.event == "run.started":
                assert runtime.cancel_run(user_id="u-cancel", run_id="team-run-cancel")

    await asyncio.wait_for(_consume(), timeout=3)
    cancelled = [e for e in events if e.event == "run.cancelled"]
    assert len(cancelled) == 1
    assert cancelled[0].data["run_id"] == "team-run-cancel"
    assert "team-run-cancel" in team.cancelled
    assert not any(e.event == "content.delta" for e in events)
    # Ownership: wrong user cannot cancel a registered team run.
    assert not runtime.cancel_run(user_id="other", run_id="team-run-cancel")


@pytest.mark.asyncio
async def test_early_stop_after_completed_does_not_cancel_runner(monkeypatch):
    """Client disconnect after run.completed must not cancel the Agno runner."""
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    cancelled: list[str] = []

    class _Runner:
        model = None

        def cancel_run(self, run_id: str) -> bool:
            cancelled.append(run_id)
            return True

        async def arun(self, *_a, **_k):
            yield SimpleNamespace(
                event="TeamRunStarted",
                run_id="team-run-ok",
                session_id="s1",
                team_id="research-analysis-team",
                model="m",
                model_provider="p",
                agent_id="",
                parent_run_id=None,
            )
            yield SimpleNamespace(
                event="TeamRunContent",
                run_id="team-run-ok",
                team_id="research-analysis-team",
                agent_id="",
                parent_run_id=None,
                content="ok",
            )
            yield SimpleNamespace(
                event="TeamRunCompleted",
                run_id="team-run-ok",
                team_id="research-analysis-team",
                session_id="s1",
                content="ok",
                metrics={},
                citations=[],
                followups=[],
            )
            await asyncio.sleep(0.05)

    runtime = srr.SecurityRunRuntime()
    request = srr.SecurityRunRequest.from_chat_args(
        "x",
        agent_id="research-analysis-team",
        session_id="s1",
        user_id="u1",
    )
    settings = SimpleNamespace(
        show_raw_reasoning=False,
        show_raw_tool_io=False,
        show_thought_chain=True,
    )
    events = []
    async for event in runtime._stream_agent_events(_Runner(), request, settings):
        events.append(event)
        if event.event == "run.completed":
            break
    assert any(e.event == "run.completed" for e in events)
    assert cancelled == []
