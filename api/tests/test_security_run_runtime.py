from pathlib import Path
import threading
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agno.models.deepseek import DeepSeek
import pytest
from pydantic import SecretStr

from api.services import runtime_env, security_run_runtime
from api.services.chat_run_events import ChatRunEvent


class FakeAgent:
    async def arun(self, *_args, **_kwargs):
        yield {"event": "RunContent", "content": "dict chunk"}
        yield {"event": "Other", "content": "ignored"}
        yield SimpleNamespace(event="RunContent", content="object chunk")
        yield SimpleNamespace(event="RunContent", content="")


class EventAgent:
    def __init__(self):
        self.cancelled_run_ids: list[str] = []

    def cancel_run(self, run_id: str) -> bool:
        self.cancelled_run_ids.append(run_id)
        return True

    async def arun(self, *_args, **_kwargs):
        yield {"event": "RunStarted", "run_id": "run-1", "session_id": "session-1", "model": "test-model", "model_provider": "test"}
        yield {"event": "ToolCallStarted", "run_id": "run-1", "tool": {"tool_call_id": "tool-1", "tool_name": "cve_lookup", "arguments": {"token": "secret"}}}
        yield {"event": "ToolCallCompleted", "run_id": "run-1", "tool": {"tool_call_id": "tool-1", "tool_name": "cve_lookup", "result": "sensitive output"}}
        yield {"event": "RunCompleted", "run_id": "run-1", "session_id": "session-1", "metrics": {"total_tokens": 42, "total_time": 1.25}, "citations": [{"id": "cve", "title": "CVE advisory", "url": "https://example.test/cve", "content": "safe excerpt"}], "followups": ["Assess impact"]}


class DetailedEventAgent:
    async def arun(self, *_args, **_kwargs):
        yield {"event": "ReasoningContentDelta", "run_id": "run-1", "content": "private chain"}
        yield {"event": "ReasoningStep", "run_id": "run-1", "content": "safe summary"}
        yield {"event": "ToolCallCompleted", "run_id": "run-1", "tool": {"tool_call_id": "tool-1", "tool_name": "lookup", "arguments": {"token": "secret"}, "result": "sensitive output"}}


class PausedEventAgent:
    async def arun(self, *_args, **_kwargs):
        yield {"event": "RunStarted", "run_id": "run-paused", "session_id": "session-1"}
        yield {
            "event": "RunPaused",
            "run_id": "run-paused",
            "session_id": "session-1",
            "tools": [{"tool_name": "simulate_containment", "approval_id": "approval-1"}],
        }


class BlockingAgent:
    async def arun(self, *_args, **_kwargs):
        raise RuntimeError("Your request was blocked.")
        yield


class FallbackAgent:
    async def arun(self, *_args, **_kwargs):
        yield {"event": "RunContent", "content": "fallback chunk"}


class FakeMcpTools:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


class BlockingRuntime(security_run_runtime.SecurityRunRuntime):
    def _build_security_agent(self, mcp_tools, request):
        return BlockingAgent()

    def build_fallback_agent(self, model_id=None, reasoning_effort=None, memory_enabled=True):
        return FallbackAgent()


@pytest.mark.asyncio
async def test_runtime_env_loader_runs_dotenv_once() -> None:
    runtime_env._RUNTIME_ENV_LOADED = False
    calls: list[dict] = []

    with patch.object(
        runtime_env, "load_dotenv", side_effect=lambda **kwargs: calls.append(kwargs)
    ):
        await runtime_env.load_runtime_env_async()
        await runtime_env.load_runtime_env_async()

    assert calls == [{"override": True}]


@pytest.mark.asyncio
async def test_load_prompt_reads_static_prompt_file():
    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / "agent.md").write_text("\n外置提示词\n", encoding="utf-8")
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            assert await security_run_runtime._load_prompt_async("agent.md") == "外置提示词"


@pytest.mark.asyncio
async def test_load_prompt_rejects_empty_prompt_file():
    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / "agent.md").write_text("  \n", encoding="utf-8")
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            with pytest.raises(RuntimeError):
                await security_run_runtime._load_prompt_async("agent.md")


@pytest.mark.asyncio
async def test_security_agent_loads_prompt_when_agent_is_built():
    created: dict = {}

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        prompt_file = prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT
        prompt_file.write_text("第一次运行时能力", encoding="utf-8")
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda _model_id: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: [],
                agent_factory=agent_factory,
            )
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            await runtime._build_security_agent(
                FakeMcpTools(),
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "hello",
                    model_id="model-1",
                    user_id="u1",
                    knowledge_owner_user_id="u1",
                ),
            )
            assert created["instructions"] == ["第一次运行时能力"]
            prompt_file.write_text("第二次运行时能力", encoding="utf-8")
            await runtime._build_security_agent(
                FakeMcpTools(),
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "hello",
                    model_id="model-1",
                    user_id="u1",
                    knowledge_owner_user_id="u1",
                ),
            )
    assert created["instructions"] == ["第二次运行时能力"]
    assert created["knowledge_filters"] == {"user_id": "u1"}
    assert created["search_knowledge"]
    assert created["update_memory_on_run"]
    assert created["enable_session_summaries"]
    assert isinstance(
        created["session_summary_manager"],
        security_run_runtime.SessionSummaryManager,
    )


@pytest.mark.asyncio
async def test_fallback_agent_loads_prompt_when_agent_is_built():
    created: dict = {}

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        prompt_file = prompt_dir / security_run_runtime.SAFE_FALLBACK_PROMPT
        prompt_file.write_text("降级提示词", encoding="utf-8")
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda _model_id: object(),
                get_db=lambda: object(),
                agent_factory=agent_factory,
            )
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            await runtime.build_fallback_agent(model_id="model-1")
    assert created["instructions"] == ["降级提示词"]


@pytest.mark.asyncio
async def test_fallback_agent_keeps_memory_and_summary():
    created: dict = {}

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(
            build_model=lambda _model_id: object(),
            get_db=lambda: object(),
            agent_factory=agent_factory,
        )
    )
    await runtime.build_fallback_agent(model_id="model-1")
    assert created["update_memory_on_run"]
    assert created["enable_session_summaries"]
    assert isinstance(
        created["session_summary_manager"],
        security_run_runtime.SessionSummaryManager,
    )
    assert "tools" not in created
    assert "knowledge" not in created


@pytest.mark.asyncio
async def test_security_agent_disables_long_term_memory_when_requested():
    created: dict = {}
    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(
            build_model=lambda _model_id: object(),
            get_db=lambda: object(),
            get_async_knowledge_base=lambda: object(),
            get_enabled_skill_dirs=lambda: [],
            agent_factory=lambda **kwargs: created.update(kwargs) or SimpleNamespace(),
        )
    )
    await runtime._build_security_agent(
        FakeMcpTools(),
        security_run_runtime.SecurityRunRequest.from_chat_args(
            "hello", user_id="u1", memory_enabled=False
        ),
    )
    assert created["update_memory_on_run"] is False
    assert created["add_memories_to_context"] is False


def test_deepseek_session_summary_uses_json_mode_response_format():
    model = DeepSeek(id="deepseek-v4-flash", api_key="secret")
    manager = security_run_runtime.SessionSummaryManager(model=model)

    assert manager.get_response_format(model) == {"type": "json_object"}


@pytest.mark.asyncio
async def test_enabled_skills_loads_sync_agno_skills_off_event_loop():
    event_loop_thread_id = threading.get_ident()
    constructor_thread_id: int | None = None

    class FakeLocalSkills:
        def __init__(self, path: str):
            self.path = path

    class FakeSkills:
        def __init__(self, loaders):
            nonlocal constructor_thread_id
            constructor_thread_id = threading.get_ident()
            self.loaders = loaders

    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(
            get_enabled_skill_dirs=lambda: [Path("/tmp/security-skill")],
        )
    )

    with (
        patch.object(security_run_runtime, "LocalSkills", FakeLocalSkills),
        patch.object(security_run_runtime, "Skills", FakeSkills),
    ):
        skills = await runtime._build_enabled_skills()

    assert isinstance(skills, FakeSkills)
    assert [loader.path for loader in skills.loaders] == ["/tmp/security-skill"]
    assert constructor_thread_id is not None
    assert constructor_thread_id != event_loop_thread_id


@pytest.mark.asyncio
async def test_enabled_skill_dirs_are_read_off_event_loop():
    event_loop_thread_id = threading.get_ident()
    reader_thread_id: int | None = None

    def get_enabled_skill_dirs():
        nonlocal reader_thread_id
        reader_thread_id = threading.get_ident()
        return []

    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(
            get_enabled_skill_dirs=get_enabled_skill_dirs,
        )
    )

    assert await runtime._build_enabled_skills() is None
    assert reader_thread_id is not None
    assert reader_thread_id != event_loop_thread_id


@pytest.mark.asyncio
async def test_build_model_dependency_runs_off_event_loop():
    event_loop_thread_id = threading.get_ident()
    build_model_thread_id: int | None = None
    created: dict = {}

    def build_model(_model_id: str | None):
        nonlocal build_model_thread_id
        build_model_thread_id = threading.get_ident()
        return object()

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SAFE_FALLBACK_PROMPT).write_text(
            "降级提示词",
            encoding="utf-8",
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=build_model,
                get_db=lambda: object(),
                agent_factory=agent_factory,
            )
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            await runtime.build_fallback_agent(model_id="model-1")

    assert "model" in created
    assert build_model_thread_id is not None
    assert build_model_thread_id != event_loop_thread_id


@pytest.mark.asyncio
async def test_runtime_passes_reasoning_effort_override_to_model_builder():
    captured: list[tuple[str | None, str | None]] = []

    def build_model(model_id: str | None, reasoning_effort: str | None):
        captured.append((model_id, reasoning_effort))
        return object()

    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(build_model=build_model)
    )

    await runtime._build_model("model-1", "high")

    assert captured == [("model-1", "high")]


@pytest.mark.asyncio
async def test_fallback_agent_preserves_reasoning_effort_override():
    captured: list[tuple[str | None, str | None]] = []

    def build_model(model_id: str | None, reasoning_effort: str | None):
        captured.append((model_id, reasoning_effort))
        return object()

    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(
            build_model=build_model,
            get_db=lambda: object(),
            agent_factory=lambda **_kwargs: SimpleNamespace(),
        )
    )
    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SAFE_FALLBACK_PROMPT).write_text(
            "降级提示词",
            encoding="utf-8",
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            await runtime.build_fallback_agent("model-1", "max")

    assert captured == [("model-1", "max")]


@pytest.mark.asyncio
async def test_security_agent_context_builds_mcp_url_off_event_loop():
    event_loop_thread_id = threading.get_ident()
    get_mcp_url_thread_id: int | None = None

    def get_mcp_url():
        nonlocal get_mcp_url_thread_id
        get_mcp_url_thread_id = threading.get_ident()
        return "http://127.0.0.1:8000/mcp"

    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(
            get_mcp_url=get_mcp_url,
            get_mcp_token=lambda: "secret",
            mcp_tools_factory=FakeMcpTools,
            agent_factory=lambda **_kwargs: SimpleNamespace(),
        )
    )
    request = security_run_runtime.SecurityRunRequest.from_chat_args("hello")

    with patch.object(
        runtime,
        "_build_security_agent",
        return_value=SimpleNamespace(),
    ):
        async with runtime.security_agent_context(request):
            pass

    assert get_mcp_url_thread_id is not None
    assert get_mcp_url_thread_id != event_loop_thread_id


@pytest.mark.asyncio
async def test_agent_dependencies_are_built_off_event_loop():
    event_loop_thread_id = threading.get_ident()
    dependency_thread_id: int | None = None
    created: dict = {}

    def fake_agent_dependencies():
        nonlocal dependency_thread_id
        dependency_thread_id = threading.get_ident()
        return {"feishu_webhook_url": "https://feishu.example/hook"}

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "安全提示词",
            encoding="utf-8",
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda _model_id: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: [],
                agent_factory=agent_factory,
            )
        )
        request = security_run_runtime.SecurityRunRequest.from_chat_args("hello")
        with (
            patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir),
            patch.object(
                security_run_runtime,
                "_agent_dependencies",
                fake_agent_dependencies,
            ),
        ):
            await runtime._build_security_agent(FakeMcpTools(), request)

    assert created["dependencies"] == {
        "feishu_webhook_url": "https://feishu.example/hook"
    }
    assert dependency_thread_id is not None
    assert dependency_thread_id != event_loop_thread_id


@pytest.mark.asyncio
async def test_stream_agent_events_projects_only_safe_ui_events():
    runtime = security_run_runtime.SecurityRunRuntime()
    events = [
        event
        async for event in runtime._stream_agent_events(
            FakeAgent(),
            security_run_runtime.SecurityRunRequest.from_chat_args(
                "hello",
                session_id="session-1",
                user_id="u1",
            ),
        )
    ]
    assert [event.event for event in events] == ["content.delta", "content.delta"]
    assert [event.data["delta"] for event in events] == ["dict chunk", "object chunk"]


@pytest.mark.asyncio
async def test_stream_agent_events_projects_safe_tools_sources_and_metrics():
    runtime = security_run_runtime.SecurityRunRuntime()
    agent = EventAgent()
    events = [
        event
        async for event in runtime._stream_agent_events(
            agent,
            security_run_runtime.SecurityRunRequest.from_chat_args("hello", user_id="u1"),
        )
    ]

    tool_events = [event for event in events if event.event == "tool.update"]
    assert [event.data["tool"] for event in tool_events] == [
        {"id": "tool-1", "name": "cve_lookup", "status": "running"},
        {"id": "tool-1", "name": "cve_lookup", "status": "completed"},
    ]
    assert all("arguments" not in event.data["tool"] for event in tool_events)
    assert all("result" not in event.data["tool"] for event in tool_events)
    assert next(event.data for event in events if event.event == "sources")["items"][0]["title"] == "CVE advisory"
    completed = next(event.data for event in events if event.event == "run.completed")
    assert completed["metrics"] == {"total_tokens": 42, "duration": 1.25}
    assert completed["followups"] == ["Assess impact"]
    assert not runtime.cancel_run(user_id="u1", run_id="run-1")


@pytest.mark.asyncio
async def test_stream_agent_events_persists_and_projects_required_approval_pause():
    runtime = security_run_runtime.SecurityRunRuntime()
    with (
        patch.object(security_run_runtime, "save_paused_run", new=AsyncMock()) as save,
        patch.object(security_run_runtime, "notify_admins_of_hitl_approval", new=AsyncMock()) as notify,
    ):
        events = [
            event
            async for event in runtime._stream_agent_events(
                PausedEventAgent(),
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "simulate isolation", session_id="session-1", model_id="model-1", user_id="u1"
                ),
            )
        ]

    paused = next(event for event in events if event.event == "run.paused")
    assert paused.data == {
        "run_id": "run-paused",
        "session_id": "session-1",
        "approval_id": "approval-1",
        "tool_name": "simulate_containment",
    }
    assert save.await_args.args[0]["approval_id"] == "approval-1"
    assert save.await_args.args[0]["request_context"]["model_id"] == "model-1"
    notify.assert_awaited_once_with(
        approval_id="approval-1",
        tool_name="simulate_containment",
        submitter_user_id="u1",
        run_id="run-paused",
        session_id="session-1",
    )


@pytest.mark.asyncio
async def test_stream_events_filter_raw_details_at_the_source():
    runtime = security_run_runtime.SecurityRunRuntime()
    request = security_run_runtime.SecurityRunRequest.from_chat_args("hello", user_id="u1")
    hidden = [
        event async for event in runtime._stream_agent_events(
            DetailedEventAgent(), request,
            SimpleNamespace(show_raw_reasoning=False, show_raw_tool_io=False, show_thought_chain=True),
        )
    ]
    assert [event.event for event in hidden] == ["thought.update", "tool.update"]
    assert "input" not in hidden[-1].data["tool"]
    assert "output" not in hidden[-1].data["tool"]

    visible = [
        event async for event in runtime._stream_agent_events(
            DetailedEventAgent(), request,
            SimpleNamespace(show_raw_reasoning=True, show_raw_tool_io=True, show_thought_chain=True),
        )
    ]
    assert visible[0].data["delta"] == "private chain"
    assert visible[-1].data["tool"]["input"] == {"token": "secret"}
    assert visible[-1].data["tool"]["output"] == "sensitive output"


@pytest.mark.asyncio
async def test_stream_events_omit_timeline_when_thought_chain_is_disabled():
    runtime = security_run_runtime.SecurityRunRuntime()
    events = [
        event async for event in runtime._stream_agent_events(
            DetailedEventAgent(),
            security_run_runtime.SecurityRunRequest.from_chat_args("hello", user_id="u1"),
            SimpleNamespace(show_raw_reasoning=False, show_raw_tool_io=True, show_thought_chain=False),
        )
    ]
    assert events == []


def test_runtime_cancellation_requires_the_matching_user_and_live_run():
    runtime = security_run_runtime.SecurityRunRuntime()
    agent = EventAgent()
    runtime.register_run(user_id="u1", run_id="run-1", agent=agent)

    assert not runtime.cancel_run(user_id="u2", run_id="run-1")
    assert runtime.cancel_run(user_id="u1", run_id="run-1")
    assert agent.cancelled_run_ids == ["run-1"]


@pytest.mark.asyncio
async def test_provider_block_detector_matches_openai_status_error_text():
    assert security_run_runtime._is_provider_block_error(
        RuntimeError("Your request was blocked.")
    )
    assert not security_run_runtime._is_provider_block_error(RuntimeError("db down"))


@pytest.mark.asyncio
async def test_mcp_url_and_token_are_kept_separate():
    fake_settings = SimpleNamespace(
        mcp_server_url="http://127.0.0.1:8000/mcp/?transport=stream",
        mcp_token=SecretStr("secret token"),
    )
    with patch.object(security_run_runtime, "get_settings", return_value=fake_settings):
        assert security_run_runtime._build_mcp_url() == "http://127.0.0.1:8000/mcp/?transport=stream"
        assert security_run_runtime._build_mcp_token() == "secret token"


@pytest.mark.asyncio
async def test_security_run_request_drives_provider_block_fallback():
    runtime = BlockingRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(
            get_mcp_url=lambda: "http://127.0.0.1:8000/mcp/",
            get_mcp_token=lambda: "test",
            mcp_tools_factory=FakeMcpTools,
        )
    )
    with patch.object(
        security_run_runtime,
        "get_chat_settings_async",
        new=AsyncMock(return_value=SimpleNamespace()),
    ):
        chunks = [
            chunk
            async for chunk in security_run_runtime.stream_security_run(
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "hello",
                    session_id="session-1",
                    model_id="model-1",
                    user_id="u1",
                    knowledge_owner_user_id="u1",
                ),
                runtime=runtime,
            )
        ]
    assert chunks[0].event == "content.delta"
    assert chunks[1] == ChatRunEvent("content.delta", {"run_id": "", "delta": "fallback chunk"})



def test_rejection_confirmation_note_uses_resolution_data():
    assert (
        security_run_runtime._rejection_confirmation_note(
            {"rejection_reason": "证据不足，暂不封禁"}
        )
        == "Rejected by administrator: 证据不足，暂不封禁"
    )
    assert (
        security_run_runtime._rejection_confirmation_note({"note": "policy"})
        == "Rejected by administrator: policy"
    )
    assert security_run_runtime._rejection_confirmation_note({}) == "Rejected by administrator"


@pytest.mark.asyncio
async def test_apply_native_hitl_resolution_rejects_with_admin_note():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from agno.models.response import ToolExecution
    from agno.run.requirement import RunRequirement

    tool = ToolExecution(
        tool_name="simulate_containment",
        tool_args={"target": "test@test.com", "action": "block"},
        tool_call_id="call-1",
        requires_confirmation=True,
        approval_type="required",
        approval_id="approval-1",
    )
    requirement = RunRequirement(tool_execution=tool)
    run_output = SimpleNamespace(requirements=[requirement], tools=[tool])
    agent = SimpleNamespace(aget_run_output=AsyncMock(return_value=run_output))
    db = SimpleNamespace(
        get_approval=AsyncMock(
            return_value={
                "status": "rejected",
                "resolution_data": {"rejection_reason": "证据不足，暂不封禁", "note": "证据不足，暂不封禁"},
            }
        )
    )

    with patch.object(security_run_runtime, "get_async_agno_postgres_db", return_value=db):
        requirements = await security_run_runtime.apply_native_hitl_resolution(
            agent,
            approval_id="approval-1",
            run_id="run-1",
            session_id="session-1",
            user_id="user-1",
        )

    assert requirements is not None
    assert len(requirements) == 1
    assert requirement.confirmation is False
    assert tool.confirmed is False
    assert tool.confirmation_note == "Rejected by administrator: 证据不足，暂不封禁"
    agent.aget_run_output.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_native_hitl_resolution_confirms_approved_tools():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, patch

    from agno.models.response import ToolExecution
    from agno.run.requirement import RunRequirement

    tool = ToolExecution(
        tool_name="simulate_containment",
        tool_args={"target": "test@test.com", "action": "block"},
        tool_call_id="call-1",
        requires_confirmation=True,
        approval_type="required",
        approval_id="approval-1",
    )
    requirement = RunRequirement(tool_execution=tool)
    run_output = SimpleNamespace(requirements=[requirement], tools=[tool])
    agent = SimpleNamespace(aget_run_output=AsyncMock(return_value=run_output))
    db = SimpleNamespace(
        get_approval=AsyncMock(return_value={"status": "approved", "resolution_data": None})
    )

    with patch.object(security_run_runtime, "get_async_agno_postgres_db", return_value=db):
        requirements = await security_run_runtime.apply_native_hitl_resolution(
            agent,
            approval_id="approval-1",
            run_id="run-1",
            session_id="session-1",
            user_id="user-1",
        )

    assert requirements is not None
    assert requirement.confirmation is True
    assert tool.confirmed is True
