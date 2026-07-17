from unittest.mock import AsyncMock
import asyncio
from types import SimpleNamespace

import pytest

from api.services.team_runtime import (
    build_team_by_id,
    is_team_id,
    list_chat_teams,
    normalize_team_id,
    team_feature_enabled,
)


def test_team_feature_flag_default_off(monkeypatch):
    monkeypatch.delenv("TAIS_ENABLE_AGNO_TEAM", raising=False)
    assert team_feature_enabled() is False
    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    assert team_feature_enabled() is True


def test_team_catalog_gated(monkeypatch):
    monkeypatch.delenv("TAIS_ENABLE_AGNO_TEAM", raising=False)
    assert list_chat_teams() == []
    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    ids = {row["id"] for row in list_chat_teams()}
    assert "research-analysis-team" in ids
    assert "research-analysis-route" in ids


def test_normalize_team_ids():
    assert normalize_team_id("research-analysis") == "research-analysis-team"
    assert normalize_team_id("research-analysis-route") == "research-analysis-route"
    assert is_team_id("research-analysis-team") is True
    assert is_team_id("data-analysis") is False


@pytest.mark.asyncio
async def test_build_research_team_members(monkeypatch):
    created: list[dict] = []

    class FakeTeam:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)
            self.members = kwargs.get("members") or []

    def fake_agent(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(**kwargs)

    async def fake_get_model(_model_id=None):
        return {"provider": "openai-compatible", "model_id": "fake"}

    monkeypatch.setattr("api.services.team_runtime.Agent", fake_agent)
    monkeypatch.setattr("api.services.team_runtime.Team", FakeTeam)
    monkeypatch.setattr("api.services.team_runtime.get_model_for_run", fake_get_model)
    monkeypatch.setattr("api.services.team_runtime.build_agno_model", lambda *_a, **_k: object())
    monkeypatch.setattr("api.services.team_runtime.get_async_agno_postgres_db", lambda: None)
    monkeypatch.setattr(
        "api.services.team_runtime.build_tools_for_profile",
        lambda _p: [],
    )

    team = await build_team_by_id("research-analysis")
    assert team.id == "research-analysis-team"
    member_ids = [getattr(m, "id", None) for m in team.members]
    assert "deep-research" in member_ids
    assert "data-analysis" in member_ids
    assert {row["id"] for row in created} >= {"deep-research", "data-analysis"}
    # Each member gets its own model instance (broadcast-safe).
    models = [row.get("model") for row in created if row.get("id") in {"deep-research", "data-analysis"}]
    assert len(models) == 2
    assert models[0] is not models[1]
    assert getattr(team, "session_summary_manager", None) is not None
    assert getattr(team, "add_session_summary_to_context", False) is True


@pytest.mark.asyncio
async def test_stream_team_disabled_fails(monkeypatch):
    from api.services import security_run_runtime as srr

    monkeypatch.delenv("TAIS_ENABLE_AGNO_TEAM", raising=False)
    req = srr.SecurityRunRequest.from_chat_args(
        "research topic",
        agent_id="research-analysis-team",
        enable_tools=True,
    )
    # when flag off, resolve_chat_run_target falls back to security-operations
    assert req.agent_id == "security-operations"

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    req2 = srr.SecurityRunRequest.from_chat_args(
        "research topic",
        agent_id="research-analysis-team",
        enable_tools=True,
    )
    assert req2.agent_id == "research-analysis-team"
    assert req2.skill_names == []

    events = []
    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    req3 = srr.SecurityRunRequest.from_chat_args(
        "x", agent_id="research-analysis-team", enable_tools=True
    )
    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "0")

    async def fake_settings():
        return SimpleNamespace(
            show_raw_reasoning=False,
            show_raw_tool_io=False,
            show_thought_chain=True,
        )

    monkeypatch.setattr(srr, "get_chat_settings_async", fake_settings)
    async for ev in srr.DEFAULT_SECURITY_RUN_RUNTIME.stream(req3):
        events.append(ev)
    assert any(e.event == "run.failed" and e.data.get("code") == "TEAM_DISABLED" for e in events)


def test_event_matches_agent_and_team():
    from agno.run.agent import RunEvent
    from agno.run.team import TeamRunEvent
    from api.services.security_run_runtime import _event_matches

    assert _event_matches(RunEvent.run_started.value, "run_started")
    assert _event_matches(TeamRunEvent.run_started.value, "run_started")
    assert not _event_matches("Nope", "run_started")


def test_is_member_agent_event():
    from api.services.security_run_runtime import _is_member_agent_event

    leader = SimpleNamespace(team_id="research-analysis-team", agent_id="", parent_run_id=None)
    assert _is_member_agent_event(leader) is False
    # Leader intermediate often only has content (empty team_id, no parent).
    leader_intermediate = SimpleNamespace(
        team_id="",
        agent_id="",
        parent_run_id=None,
        content="draft",
    )
    assert _is_member_agent_event(leader_intermediate) is False
    member = SimpleNamespace(
        team_id="",
        agent_id="deep-research",
        agent_name="深度研究助手",
        parent_run_id="parent-run",
    )
    assert _is_member_agent_event(member) is True
    # Agno may forward member Intermediate with parent_run_id but no agent_id.
    member_intermediate = SimpleNamespace(
        team_id="",
        agent_id="",
        parent_run_id="parent-run",
        content="partial",
    )
    assert _is_member_agent_event(member_intermediate) is True


def test_project_tool_update_prefixes_member():
    from api.services.security_run_runtime import _project_tool_update

    member_event = SimpleNamespace(
        team_id="",
        agent_id="deep-research",
        agent_name="深度研究助手",
        parent_run_id="parent",
        tool=SimpleNamespace(tool_call_id="c1", tool_name="read_url"),
    )
    projected = _project_tool_update(member_event, "running")
    assert projected["id"].startswith("member:deep-research:")
    assert projected["name"].startswith("[深度研究助手]")
    assert projected["member_id"] == "deep-research"

    leader_event = SimpleNamespace(
        team_id="research-analysis-team",
        agent_id="",
        parent_run_id=None,
        tool=SimpleNamespace(tool_call_id="c2", tool_name="delegate"),
    )
    leader = _project_tool_update(leader_event, "completed")
    assert not str(leader["id"]).startswith("member:")
    assert "member_id" not in leader


class TeamStreamRunner:
    """Minimal Team-like runner yielding Team + member Agent events."""

    def __init__(self):
        self.cancelled: list[str] = []

    def cancel_run(self, run_id: str) -> bool:
        self.cancelled.append(run_id)
        return True

    async def arun(self, *_args, **_kwargs):
        yield SimpleNamespace(
            event="TeamRunStarted",
            run_id="team-run-1",
            session_id="s1",
            team_id="research-analysis-team",
            team_name="研究分析团队",
            model="m",
            model_provider="p",
            agent_id="",
            parent_run_id=None,
        )
        yield SimpleNamespace(
            event="RunStarted",
            run_id="member-run-1",
            session_id="s1",
            team_id="",
            agent_id="deep-research",
            agent_name="深度研究助手",
            parent_run_id="team-run-1",
            model="m",
            model_provider="p",
        )
        yield SimpleNamespace(
            event="RunContent",
            run_id="member-run-1",
            team_id="",
            agent_id="deep-research",
            agent_name="深度研究助手",
            parent_run_id="team-run-1",
            content="成员调研草稿",
        )
        yield SimpleNamespace(
            event="ToolCallStarted",
            run_id="member-run-1",
            team_id="",
            agent_id="deep-research",
            agent_name="深度研究助手",
            parent_run_id="team-run-1",
            tool=SimpleNamespace(tool_call_id="t1", tool_name="read_url"),
        )
        yield SimpleNamespace(
            event="ToolCallCompleted",
            run_id="member-run-1",
            team_id="",
            agent_id="deep-research",
            agent_name="深度研究助手",
            parent_run_id="team-run-1",
            tool=SimpleNamespace(tool_call_id="t1", tool_name="read_url", result="ok"),
        )
        yield SimpleNamespace(
            event="RunCompleted",
            run_id="member-run-1",
            team_id="",
            agent_id="deep-research",
            agent_name="深度研究助手",
            parent_run_id="team-run-1",
            content="成员完成摘要",
        )
        yield SimpleNamespace(
            event="TeamRunContent",
            run_id="team-run-1",
            team_id="research-analysis-team",
            team_name="研究分析团队",
            agent_id="",
            parent_run_id=None,
            content="队长综合报告",
        )
        yield SimpleNamespace(
            event="TeamRunCompleted",
            run_id="team-run-1",
            session_id="s1",
            team_id="research-analysis-team",
            content="队长综合报告",
            metrics={"total_tokens": 9, "total_time": 0.5},
            citations=[],
            followups=[],
        )


@pytest.mark.asyncio
async def test_stream_projects_team_member_thoughts_and_leader_content(monkeypatch):
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    runtime = srr.SecurityRunRuntime()
    request = srr.SecurityRunRequest.from_chat_args(
        "调研并核算",
        session_id="s1",
        user_id="u1",
        agent_id="research-analysis-team",
        enable_tools=True,
    )
    assert request.agent_id == "research-analysis-team"

    settings = SimpleNamespace(
        show_raw_reasoning=False,
        show_raw_tool_io=False,
        show_thought_chain=True,
    )
    events = [
        event
        async for event in runtime._stream_agent_events(
            TeamStreamRunner(), request, settings
        )
    ]
    kinds = [e.event for e in events]
    assert "run.started" in kinds
    assert "thought.update" in kinds
    assert "tool.update" in kinds
    assert "content.delta" in kinds
    assert "run.completed" in kinds

    content_deltas = [e.data.get("delta") for e in events if e.event == "content.delta"]
    assert content_deltas == ["队长综合报告"]
    assert "成员调研草稿" not in content_deltas

    thoughts = [e for e in events if e.event == "thought.update"]
    titles = [e.data["thought"]["title"] for e in thoughts]
    assert any("深度研究助手" in t for t in titles)

    tools = [e for e in events if e.event == "tool.update"]
    assert tools
    assert tools[0].data["tool"]["id"].startswith("member:deep-research:")
    assert tools[0].data["tool"]["name"].startswith("[深度研究助手]")
    assert tools[0].data["run_id"] == "team-run-1"

    started = next(e for e in events if e.event == "run.started")
    assert started.data["agent_id"] == "research-analysis-team"
    assert started.data["run_id"] == "team-run-1"


@pytest.mark.asyncio
async def test_stream_team_enable_tools_false_skips_member_tools(monkeypatch):
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

    monkeypatch.setattr(tr, "Agent", fake_agent)
    monkeypatch.setattr(tr, "Team", FakeTeam)
    monkeypatch.setattr(tr, "get_model_for_run", fake_get_model)
    monkeypatch.setattr(tr, "build_agno_model", lambda *_a, **_k: object())
    monkeypatch.setattr(tr, "get_async_agno_postgres_db", lambda: None)
    monkeypatch.setattr(tr, "build_tools_for_profile", lambda _p: ["tool"])

    await tr.build_team("research-analysis-team", enable_tools=False)
    assert created_tools
    assert all(tools == [] for tools in created_tools)

    created_tools.clear()
    await tr.build_team("research-analysis-team", enable_tools=True)
    assert any(tools == ["tool"] for tools in created_tools)


@pytest.mark.asyncio
async def test_stream_cancel_during_team_emits_single_cancelled(monkeypatch):
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



@pytest.mark.asyncio
async def test_member_run_error_is_thought_not_failed(monkeypatch):
    """Member Agent run_error must not fail the whole Team stream."""
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")

    class _Runner:
        model = None

        async def arun(self, *_a, **_k):
            yield SimpleNamespace(
                event="TeamRunStarted",
                run_id="team-run-err",
                session_id="s1",
                team_id="research-analysis-team",
                model="m",
                model_provider="p",
                agent_id="",
                parent_run_id=None,
            )
            yield SimpleNamespace(
                event="RunError",
                run_id="member-run-err",
                parent_run_id="team-run-err",
                agent_id="deep-research",
                agent_name="深度研究助手",
                team_id="",
                content="member boom",
            )
            yield SimpleNamespace(
                event="TeamRunContent",
                run_id="team-run-err",
                team_id="research-analysis-team",
                agent_id="",
                parent_run_id=None,
                content="leader recovered",
            )
            yield SimpleNamespace(
                event="TeamRunCompleted",
                run_id="team-run-err",
                team_id="research-analysis-team",
                session_id="s1",
                content="done",
                metrics={},
                citations=[],
                followups=[],
            )

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
    events = [
        event
        async for event in runtime._stream_agent_events(_Runner(), request, settings)
    ]
    kinds = [e.event for e in events]
    assert "run.failed" not in kinds
    assert "run.completed" in kinds
    thoughts = [e for e in events if e.event == "thought.update"]
    assert any(
        e.data.get("thought", {}).get("status") == "error"
        and e.data.get("thought", {}).get("id") == "member:deep-research"
        for e in thoughts
    )
    contents = [e.data.get("delta") for e in events if e.event == "content.delta"]
    assert "leader recovered" in contents


@pytest.mark.asyncio
async def test_team_live_search_defaults_to_profile(monkeypatch):
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    captured: dict = {}

    class _FakeTeam:
        model = None
        search_knowledge = False

        async def arun(self, *_a, **_k):
            if False:  # pragma: no cover - empty async generator
                yield None

    async def _build_team(team_id, **kwargs):
        captured["team_id"] = team_id
        captured["live_search"] = kwargs.get("live_search")
        return _FakeTeam()

    monkeypatch.setattr(srr, "build_team", _build_team)
    monkeypatch.setattr(
        srr,
        "get_chat_settings_async",
        AsyncMock(
            return_value=SimpleNamespace(
                show_raw_reasoning=False,
                show_raw_tool_io=False,
                show_thought_chain=True,
            )
        ),
    )
    runtime = srr.SecurityRunRuntime()
    request = srr.SecurityRunRequest.from_chat_args(
        "x",
        agent_id="research-analysis-team",
        enable_tools=True,
        live_search=None,
        search_knowledge=False,
    )
    async for _ in runtime.stream(request):
        pass
    assert captured.get("live_search") is True


@pytest.mark.asyncio
async def test_intermediate_content_leader_is_content_delta(monkeypatch):
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")

    class _Runner:
        model = None

        async def arun(self, *_a, **_k):
            yield SimpleNamespace(
                event="TeamRunStarted",
                run_id="team-run-i",
                session_id="s1",
                team_id="research-analysis-team",
                model="m",
                model_provider="p",
                agent_id="",
                parent_run_id=None,
            )
            yield SimpleNamespace(
                event="TeamRunIntermediateContent",
                run_id="team-run-i",
                team_id="research-analysis-team",
                agent_id="",
                parent_run_id=None,
                content="draft",
            )
            yield SimpleNamespace(
                event="TeamRunCompleted",
                run_id="team-run-i",
                team_id="research-analysis-team",
                session_id="s1",
                content="draft",
                metrics={},
                citations=[],
                followups=[],
            )

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
    events = [
        event
        async for event in runtime._stream_agent_events(_Runner(), request, settings)
    ]
    kinds = [e.event for e in events]
    assert "content.delta" in kinds
    assert any(e.data.get("delta") == "draft" for e in events if e.event == "content.delta")



@pytest.mark.asyncio
async def test_member_intermediate_without_agent_id_stays_in_thought(monkeypatch):
    """Agno IntermediateRunContent often drops agent_id; must not leak to answer."""
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")

    class Runner:
        async def arun(self, *_a, **_k):
            yield SimpleNamespace(
                event="TeamRunStarted",
                run_id="team-run-m",
                session_id="s1",
                team_id="research-analysis-team",
                model="m",
                model_provider="p",
                agent_id="",
                parent_run_id=None,
            )
            # Fully identified member start
            yield SimpleNamespace(
                event="RunStarted",
                run_id="member-run-1",
                team_id="",
                agent_id="deep-research",
                agent_name="深度研究助手",
                parent_run_id="team-run-m",
                model="m",
                model_provider="p",
            )
            # Identity-stripped intermediate (content only + parent_run_id)
            yield SimpleNamespace(
                event="RunIntermediateContent",
                run_id="member-run-1",
                team_id="",
                agent_id="",
                agent_name="",
                parent_run_id="team-run-m",
                content="成员中间草稿A",
            )
            yield SimpleNamespace(
                event="RunIntermediateContent",
                run_id="member-run-1",
                team_id="",
                agent_id="",
                parent_run_id="team-run-m",
                content="成员中间草稿B",
            )
            yield SimpleNamespace(
                event="RunCompleted",
                run_id="member-run-1",
                team_id="",
                agent_id="deep-research",
                agent_name="深度研究助手",
                parent_run_id="team-run-m",
                content="成员完整输出",
            )
            # Leader intermediate still reaches content.delta
            yield SimpleNamespace(
                event="TeamRunIntermediateContent",
                run_id="team-run-m",
                team_id="",  # Agno often omits team_id on intermediate
                agent_id="",
                parent_run_id=None,
                content="队长草稿",
            )
            yield SimpleNamespace(
                event="TeamRunContent",
                run_id="team-run-m",
                team_id="research-analysis-team",
                agent_id="",
                parent_run_id=None,
                content="队长终稿",
            )
            yield SimpleNamespace(
                event="TeamRunCompleted",
                run_id="team-run-m",
                session_id="s1",
                team_id="research-analysis-team",
                content="队长终稿",
                metrics={},
                citations=[],
                followups=[],
            )

        def cancel_run(self, *_a, **_k):
            return True

    runtime = srr.SecurityRunRuntime()
    request = srr.SecurityRunRequest.from_chat_args(
        "x",
        session_id="s1",
        user_id="u1",
        agent_id="research-analysis-team",
    )
    settings = SimpleNamespace(
        show_raw_reasoning=False,
        show_raw_tool_io=False,
        show_thought_chain=True,
    )
    events = [
        event
        async for event in runtime._stream_agent_events(Runner(), request, settings)
    ]
    content_deltas = [e.data.get("delta") for e in events if e.event == "content.delta"]
    assert "成员中间草稿A" not in content_deltas
    assert "成员中间草稿B" not in content_deltas
    assert "成员完整输出" not in content_deltas
    assert content_deltas == ["队长草稿", "队长终稿"]

    thoughts = [e for e in events if e.event == "thought.update"]
    member_thoughts = [
        e for e in thoughts if e.data["thought"].get("id") == "member:deep-research"
    ]
    assert member_thoughts, thoughts
    summaries = " ".join(str(e.data["thought"].get("summary") or "") for e in member_thoughts)
    assert "成员中间草稿" in summaries or "成员完整输出" in summaries


def test_resolve_member_identity_tracks_run_and_last():
    from api.services.security_run_runtime import _resolve_member_identity

    by_run: dict[str, tuple[str, str]] = {}
    last: list[tuple[str, str] | None] = [None]
    identified = SimpleNamespace(
        run_id="m1",
        agent_id="deep-research",
        agent_name="深度研究助手",
    )
    assert _resolve_member_identity(identified, by_run=by_run, last=last) == (
        "deep-research",
        "深度研究助手",
    )
    stripped = SimpleNamespace(run_id="m1", agent_id="", agent_name="")
    assert _resolve_member_identity(stripped, by_run=by_run, last=last) == (
        "deep-research",
        "深度研究助手",
    )
    # New run_id without agent_id must not inherit previous member label.
    other = SimpleNamespace(run_id="m2", agent_id="", agent_name="")
    assert _resolve_member_identity(other, by_run=by_run, last=last) == (
        "member",
        "member",
    )
    # Missing run_id may use last known member (identity-stripped intermediate).
    no_run = SimpleNamespace(run_id="", agent_id="", agent_name="")
    assert _resolve_member_identity(no_run, by_run=by_run, last=last) == (
        "deep-research",
        "深度研究助手",
    )



@pytest.mark.asyncio
async def test_early_stop_after_completed_does_not_cancel_runner(monkeypatch):
    """Consumer break after run.completed must not cancel Agno (Team history)."""
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
            # Simulate slow post-complete teardown
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
            break  # client stops reading after terminal event
    assert any(e.event == "run.completed" for e in events)
    assert cancelled == []


def test_task_event_matches_team_run_event():
    from api.services.security_run_runtime import _event_matches
    from agno.run.team import TeamRunEvent

    assert _event_matches(TeamRunEvent.task_created.value, "task_created")
    assert _event_matches(TeamRunEvent.task_updated.value, "task_updated")
    assert _event_matches(TeamRunEvent.task_iteration_started.value, "task_iteration_started")


def test_broadcast_team_in_catalog(monkeypatch):
    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")
    from api.services.team_runtime import list_chat_teams, normalize_team_id, get_team_profile
    from agno.team.mode import TeamMode

    assert normalize_team_id("research-broadcast") == "research-analysis-broadcast"
    profile = get_team_profile("research-analysis-broadcast")
    assert profile is not None
    assert profile.get("mode") == TeamMode.broadcast
    ids = {row["id"] for row in list_chat_teams()}
    assert "research-analysis-broadcast" in ids


def test_member_thought_throttle_skips_tiny_deltas(monkeypatch):
    from api.services.security_run_runtime import _should_emit_member_thought

    clock = {"t": 0.0}

    def fake_mono():
        return clock["t"]

    monkeypatch.setattr("api.services.security_run_runtime.time.monotonic", fake_mono)
    state: dict[str, tuple[str, float]] = {}
    assert _should_emit_member_thought(state, member_id="m1", summary="a")
    # same text ignored
    assert not _should_emit_member_thought(state, member_id="m1", summary="a")
    # tiny growth before interval ignored
    clock["t"] = 0.1
    assert not _should_emit_member_thought(state, member_id="m1", summary="ab")
    # growth threshold
    assert _should_emit_member_thought(
        state, member_id="m1", summary="a" + ("x" * 15)
    )
    # force always
    assert _should_emit_member_thought(
        state, member_id="m1", summary="final", force=True
    )


def test_append_member_content_delta_merges_chunks():
    from api.services.security_run_runtime import _append_member_content_delta

    acc: dict[str, str] = {}
    s1 = _append_member_content_delta(acc, member_id="m1", delta="Hel")
    s2 = _append_member_content_delta(acc, member_id="m1", delta="lo")
    assert s1 == "Hel"
    assert s2 == "Hello"
    # cumulative snapshot path
    s3 = _append_member_content_delta(acc, member_id="m1", delta="Hello!")
    assert s3 == "Hello!"


@pytest.mark.asyncio
async def test_member_stream_thought_summary_accumulates_deltas(monkeypatch):
    """Member RunContent chunks are deltas; ThoughtChain summary must grow."""
    from types import SimpleNamespace
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")

    class Runner:
        async def arun(self, *a, **k):
            # Long enough chunk train to cross min_growth between emits.
            chunks = ["Alpha-", "Bravo-", "Charlie-", "Delta-end"]
            for ch in chunks:
                yield SimpleNamespace(
                    event="RunContent",
                    run_id="m1",
                    team_id="",
                    agent_id="deep-research",
                    agent_name="深度研究助手",
                    parent_run_id="t1",
                    content=ch,
                )
            yield SimpleNamespace(
                event="RunCompleted",
                run_id="m1",
                team_id="",
                agent_id="deep-research",
                agent_name="深度研究助手",
                parent_run_id="t1",
                content="Alpha-Bravo-Charlie-Delta-end",
            )
            yield SimpleNamespace(
                event="TeamRunContent",
                run_id="t1",
                team_id="research-analysis-team",
                agent_id="",
                parent_run_id=None,
                content="综合",
            )
            yield SimpleNamespace(
                event="TeamRunCompleted",
                run_id="t1",
                session_id="s",
                team_id="research-analysis-team",
                content="综合",
                metrics={},
                citations=[],
                followups=[],
            )

        def cancel_run(self, *a, **k):
            return True

    runtime = srr.SecurityRunRuntime()
    request = srr.SecurityRunRequest.from_chat_args(
        "x", session_id="s", user_id="u1", agent_id="research-analysis-team"
    )
    settings = SimpleNamespace(
        show_raw_reasoning=False, show_raw_tool_io=False, show_thought_chain=True
    )
    thoughts = []
    async for ev in runtime._stream_agent_events(Runner(), request, settings):
        if ev.event == "thought.update":
            th = ev.data["thought"]
            if th.get("id") == "member:deep-research":
                thoughts.append(th)
    running = [t["summary"] for t in thoughts if t.get("status") == "running"]
    completed = [t["summary"] for t in thoughts if t.get("status") == "completed"]
    assert running, thoughts
    # Accumulators must grow (not single-token only)
    assert max(len(s) for s in running) >= len("Alpha-Bravo-")
    assert completed and completed[-1] == "Alpha-Bravo-Charlie-Delta-end"

@pytest.mark.asyncio
async def test_broadcast_shares_member_interactions(monkeypatch):
    from agno.team.mode import TeamMode
    from api.services import team_runtime as tr

    captured: dict = {}

    class FakeTeam:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.__dict__.update(kwargs)
            self.members = kwargs.get("members") or []

    monkeypatch.setattr(tr, "Agent", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(tr, "Team", FakeTeam)
    async def fake_get_model(_m=None):
        return {"provider": "x", "model_id": "m"}

    monkeypatch.setattr(tr, "get_model_for_run", fake_get_model)
    monkeypatch.setattr(tr, "build_agno_model", lambda *_a, **_k: object())
    monkeypatch.setattr(tr, "get_async_agno_postgres_db", lambda: None)
    monkeypatch.setattr(tr, "build_tools_for_profile", lambda _p: [])

    await tr.build_team("research-analysis-broadcast", enable_tools=False)
    assert captured.get("mode") == TeamMode.broadcast
    assert captured.get("share_member_interactions") is True
    assert captured.get("respond_directly") is False

    captured.clear()
    await tr.build_team("research-analysis-route", enable_tools=False)
    assert captured.get("mode") == TeamMode.route
    assert captured.get("respond_directly") is True
    assert captured.get("share_member_interactions") is False


@pytest.mark.asyncio
async def test_leader_completed_flushes_open_member_thoughts(monkeypatch):
    """If member RunCompleted is missing, leader completion still closes thoughts."""
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")

    class Runner:
        async def arun(self, *_a, **_k):
            yield SimpleNamespace(
                event="TeamRunStarted",
                run_id="team-run-f",
                session_id="s1",
                team_id="research-analysis-team",
                model="m",
                model_provider="p",
                agent_id="",
                parent_run_id=None,
            )
            yield SimpleNamespace(
                event="RunStarted",
                run_id="member-run-f",
                team_id="",
                agent_id="deep-research",
                agent_name="深度研究助手",
                parent_run_id="team-run-f",
                model="m",
                model_provider="p",
            )
            yield SimpleNamespace(
                event="RunContent",
                run_id="member-run-f",
                team_id="",
                agent_id="deep-research",
                agent_name="深度研究助手",
                parent_run_id="team-run-f",
                content="成员草稿未完成",
            )
            # No member RunCompleted — only leader completes.
            yield SimpleNamespace(
                event="TeamRunContent",
                run_id="team-run-f",
                team_id="research-analysis-team",
                content="队长结论",
            )
            yield SimpleNamespace(
                event="TeamRunCompleted",
                run_id="team-run-f",
                session_id="s1",
                team_id="research-analysis-team",
                content="队长结论",
                metrics={},
                citations=[],
                followups=[],
            )

        def cancel_run(self, *_a, **_k):
            return True

    runtime = srr.SecurityRunRuntime()
    request = srr.SecurityRunRequest.from_chat_args(
        "x", session_id="s1", user_id="u1", agent_id="research-analysis-team"
    )
    settings = SimpleNamespace(
        show_raw_reasoning=False, show_raw_tool_io=False, show_thought_chain=True
    )
    events = [
        event
        async for event in runtime._stream_agent_events(Runner(), request, settings)
    ]
    thoughts = [e for e in events if e.event == "thought.update"]
    completed_member = [
        e
        for e in thoughts
        if e.data["thought"].get("id") == "member:deep-research"
        and e.data["thought"].get("status") == "completed"
    ]
    assert completed_member, thoughts
    assert "成员草稿" in str(completed_member[-1].data["thought"].get("summary") or "")
    completed = next(e for e in events if e.event == "run.completed")
    assert completed.data.get("content") == "队长结论"


def test_completed_payload_includes_content():
    from types import SimpleNamespace
    from api.services.chat_run_events import completed_payload

    payload = completed_payload(
        SimpleNamespace(
            run_id="r1",
            session_id="s1",
            content="final answer",
            metrics={},
            followups=["next"],
        )
    )
    assert payload["content"] == "final answer"
    assert payload["followups"] == ["next"]


@pytest.mark.asyncio
async def test_member_reasoning_delta_stays_in_thought(monkeypatch):
    """Member ReasoningContentDelta must not feed the main reasoning panel."""
    from api.services import security_run_runtime as srr

    monkeypatch.setenv("TAIS_ENABLE_AGNO_TEAM", "1")

    class Runner:
        async def arun(self, *_a, **_k):
            yield SimpleNamespace(
                event="TeamRunStarted",
                run_id="team-run-r",
                session_id="s1",
                team_id="research-analysis-team",
                model="m",
                model_provider="p",
                agent_id="",
                parent_run_id=None,
            )
            yield SimpleNamespace(
                event="RunStarted",
                run_id="member-run-r",
                team_id="",
                agent_id="deep-research",
                agent_name="深度研究助手",
                parent_run_id="team-run-r",
                model="m",
                model_provider="p",
            )
            yield SimpleNamespace(
                event="ReasoningContentDelta",
                run_id="member-run-r",
                team_id="",
                agent_id="deep-research",
                agent_name="深度研究助手",
                parent_run_id="team-run-r",
                content="成员内部推理片段",
            )
            yield SimpleNamespace(
                event="RunCompleted",
                run_id="member-run-r",
                team_id="",
                agent_id="deep-research",
                agent_name="深度研究助手",
                parent_run_id="team-run-r",
                content="成员结论",
                citations=[{"title": "Example", "url": "https://example.com"}],
            )
            yield SimpleNamespace(
                event="TeamRunContent",
                run_id="team-run-r",
                team_id="research-analysis-team",
                content="队长回答",
            )
            yield SimpleNamespace(
                event="TeamRunCompleted",
                run_id="team-run-r",
                session_id="s1",
                team_id="research-analysis-team",
                content="队长回答",
                metrics={},
                citations=[],
                followups=[],
            )

        def cancel_run(self, *_a, **_k):
            return True

    runtime = srr.SecurityRunRuntime()
    request = srr.SecurityRunRequest.from_chat_args(
        "x", session_id="s1", user_id="u1", agent_id="research-analysis-team"
    )
    settings = SimpleNamespace(
        show_raw_reasoning=True,
        show_raw_tool_io=False,
        show_thought_chain=True,
    )
    events = [
        event
        async for event in runtime._stream_agent_events(Runner(), request, settings)
    ]
    assert not any(e.event == "reasoning.delta" for e in events), events
    thoughts = [e for e in events if e.event == "thought.update"]
    assert any(
        e.data["thought"].get("id") == "member:deep-research:reasoning" for e in thoughts
    ), thoughts
    sources = [e for e in events if e.event == "sources"]
    assert sources, events
    titles = [item.get("title") for item in sources[0].data.get("items") or []]
    assert any(isinstance(t, str) and "深度研究助手" in t for t in titles), titles


def test_csv_builder_dedupes_stem(tmp_path, monkeypatch):
    from pathlib import Path
    from api.services import agent_tools as at

    root = Path(tmp_path)
    (root / "a.csv").write_text("x\n1\n", encoding="utf-8")
    nested = root / "sub"
    nested.mkdir()
    (nested / "a.csv").write_text("y\n2\n", encoding="utf-8")
    (root / "b.csv").write_text("z\n3\n", encoding="utf-8")

    monkeypatch.setattr(at, "analysis_work_dir", lambda: root)
    tools = at._build_csv()
    stems = [p.stem for p in tools.csvs]
    assert stems.count("a") == 1
    assert "b" in stems
    a_path = next(p for p in tools.csvs if p.stem == "a")
    assert a_path.parent == root

