import asyncio
from contextlib import asynccontextmanager
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
    def __init__(self):
        self.run_kwargs = {}

    async def arun(self, *_args, **_kwargs):
        self.run_kwargs = _kwargs
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

    def build_fallback_agent(self, model_id=None, reasoning_effort=None, memory_enabled=True, live_search=None):
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
                build_model=lambda *_args, **_kwargs: object(),
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
                build_model=lambda *_args, **_kwargs: object(),
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
            build_model=lambda *_args, **_kwargs: object(),
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
            build_model=lambda *_args, **_kwargs: object(),
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

    def build_model(_model_id: str | None, reasoning_effort=None, live_search=None):
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

    def build_model(model_id: str | None, reasoning_effort: str | None = None, live_search=None):
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

    def build_model(model_id: str | None, reasoning_effort: str | None = None, live_search=None):
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
    request = security_run_runtime.SecurityRunRequest.from_chat_args("帮我做一次威胁研判")

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
        return {}

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
                build_model=lambda *_args, **_kwargs: object(),
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

    assert created["dependencies"] == {}
    assert created["add_dependencies_to_context"] is False
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
    agent = PausedEventAgent()
    with patch.object(
        security_run_runtime,
        "notify_admins_of_hitl_approval",
        new=AsyncMock(),
    ) as notify:
        events = [
            event
            async for event in runtime._stream_agent_events(
                agent,
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
    assert agent.run_kwargs["metadata"] == {
        "tais_runtime": {
            "version": 1,
            "model_id": "model-1",
            "reasoning_effort": "",
            "knowledge_owner_user_id": "",
            "memory_enabled": True,
            "store_raw_tool_io": False,
            "search_knowledge": True,
            "live_search": None,
            "enable_tools": True,
            "skill_names": ["hitl-containment-skill"],
        }
    }
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
async def test_sleep_interruptible_stops_when_cancel_event_set():
    cancel = asyncio.Event()

    async def _trip():
        await asyncio.sleep(0.05)
        cancel.set()

    trip = asyncio.create_task(_trip())
    with pytest.raises(asyncio.CancelledError):
        await security_run_runtime._sleep_interruptible(2.0, cancel, slice_seconds=0.02)
    await trip
    assert cancel.is_set()


@pytest.mark.asyncio
async def test_cancel_run_sets_stream_cancel_event_even_without_agent_hook():
    runtime = security_run_runtime.SecurityRunRuntime()
    cancel = asyncio.Event()
    runtime.register_run(
        user_id="u1",
        run_id="run-backoff",
        agent=EventAgent(),
        cancel_event=cancel,
    )
    assert runtime.cancel_run(user_id="u1", run_id="run-backoff")
    assert cancel.is_set()


@pytest.mark.asyncio
async def test_stream_retry_backoff_cancel_emits_run_cancelled():
    """POST cancel during model retry sleep should surface run.cancelled, not hang."""
    runtime = security_run_runtime.SecurityRunRuntime()

    class SlowRetryModel:
        def __init__(self):
            self.retries = 2
            self.delay_between_retries = 5
            self.exponential_backoff = False
            self.name = "test"
            self.id = "test-model"
            self.calls = 0

        def classify_error(self, error):
            return error

        def _is_retryable_error(self, _error):
            return True

        def _get_retry_delay(self, _attempt):
            return 5.0

        async def ainvoke_stream(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                from agno.exceptions import ModelProviderError

                raise ModelProviderError("auth_unavailable", status_code=503)
            if False:  # pragma: no cover
                yield None

        async def _ainvoke_stream_with_retry(self, **kwargs):
            if False:  # pragma: no cover
                yield None

    model = SlowRetryModel()

    class RetryThenHangAgent:
        def __init__(self):
            self.model = model

        async def arun(self, *_args, **_kwargs):
            yield {
                "event": "RunStarted",
                "run_id": "run-cancel-retry",
                "session_id": "session-1",
                "model": "test-model",
                "model_provider": "test",
            }
            # Enter patched retry path (will sleep 5s after first failure).
            async for _ in self.model._ainvoke_stream_with_retry():
                pass
            yield {
                "event": "RunCompleted",
                "run_id": "run-cancel-retry",
                "session_id": "session-1",
                "metrics": {"total_tokens": 1},
            }

        def cancel_run(self, run_id: str) -> bool:
            return True

    agent = RetryThenHangAgent()
    request = security_run_runtime.SecurityRunRequest.from_chat_args(
        "hello",
        session_id="session-1",
        user_id="user-1",
    )

    chunks: list = []

    async def _consume():
        async for event in runtime._stream_agent_events(agent, request):
            chunks.append(event)
            if event.event == "run.retrying":
                # Cancel while backoff sleep is in progress.
                assert runtime.cancel_run(user_id="user-1", run_id="run-cancel-retry")

    await asyncio.wait_for(_consume(), timeout=2.0)
    assert any(c.event == "run.retrying" for c in chunks), chunks
    assert any(c.event == "run.cancelled" for c in chunks), chunks


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
    # Legacy resolution_data.rejection_reason is ignored; only note is used.
    assert (
        security_run_runtime._rejection_confirmation_note(
            {"rejection_reason": "证据不足，暂不封禁"}
        )
        == "Rejected by administrator"
    )
    assert (
        security_run_runtime._rejection_confirmation_note({"note": "policy"})
        == "Rejected by administrator: policy"
    )
    assert security_run_runtime._rejection_confirmation_note({}) == "Rejected by administrator"



def test_approved_tool_execution_requires_a_successful_result():
    from agno.models.response import ToolExecution

    tool = ToolExecution(
        tool_name="hitl_simulate_containment",
        approval_id="approval-1",
        confirmed=True,
    )
    run_output = SimpleNamespace(tools=[tool])

    assert not security_run_runtime.approved_tool_executed(run_output, "approval-1")
    tool.result = '{"status": "simulated"}'
    assert security_run_runtime.approved_tool_executed(run_output, "approval-1")
    tool.tool_call_error = True
    assert not security_run_runtime.approved_tool_executed(run_output, "approval-1")


def test_mark_hitl_mcp_tools_only_marks_hitl_namespace():
    from agno.tools.function import Function

    hitl_tool = Function(name="hitl_simulate_containment", entrypoint=lambda: None)
    ordinary_tool = Function(name="basic_lookup", entrypoint=lambda: None)
    mcp_tools = SimpleNamespace(
        functions={hitl_tool.name: hitl_tool, ordinary_tool.name: ordinary_tool},
        async_functions={hitl_tool.name: hitl_tool},
    )

    assert security_run_runtime.mark_hitl_mcp_tools(mcp_tools) == [
        "hitl_simulate_containment"
    ]
    assert hitl_tool.approval_type == "required"
    assert hitl_tool.requires_confirmation is True
    assert ordinary_tool.approval_type is None
    assert ordinary_tool.requires_confirmation is None


def test_mcp_header_provider_injects_current_run_identity():
    provider = security_run_runtime._mcp_header_provider("secret")
    headers = provider(
        SimpleNamespace(user_id="user-1", session_id="session-1", run_id="run-1")
    )
    assert headers == {
        "Authorization": "Bearer secret",
        "X-Agno-User-ID": "user-1",
        "X-Agno-Session-ID": "session-1",
        "X-Agno-Run-ID": "run-1",
    }


def test_security_run_request_round_trips_versioned_run_metadata():
    original = security_run_runtime.SecurityRunRequest.from_chat_args(
        "contain asset",
        session_id="session-1",
        model_id="model-1",
        reasoning_effort="high",
        user_id="user-1",
        knowledge_owner_user_id="owner-1",
        memory_enabled=False,
        store_raw_tool_io=True,
        enable_tools=False,
        search_knowledge=False,
    )
    restored = security_run_runtime.SecurityRunRequest.from_run_metadata(
        {"tais_runtime": original.runtime_metadata()},
        session_id="session-1",
        user_id="user-1",
    )
    assert restored.model_id == "model-1"
    assert restored.reasoning_effort == "high"
    assert restored.knowledge_owner_user_id == "owner-1"
    assert restored.memory_enabled is False
    assert restored.store_raw_tool_io is True
    assert restored.enable_tools is False
    assert restored.search_knowledge is False
    assert original.skill_names == []
    assert restored.skill_names == []

    with pytest.raises(ValueError, match="version is unsupported"):
        security_run_runtime.SecurityRunRequest.from_run_metadata(
            {"tais_runtime": {"version": "1"}},
            session_id="session-1",
            user_id="user-1",
        )


def _security_approval(**overrides):
    return {
        "id": "approval-1",
        "status": "approved",
        "run_status": "PAUSED",
        "run_id": "run-1",
        "session_id": "session-1",
        "user_id": "user-1",
        "source_type": "agent",
        "agent_id": "security-operations",
        "tool_name": "hitl_simulate_containment",
        **overrides,
    }


class ResumeDb:
    def __init__(self, approval=None, run_output=None):
        self.approval = approval or _security_approval()
        self.run_output = run_output
        self.status_updates = []

    async def get_approval(self, _approval_id):
        return self.approval

    async def get_session(self, _session_id, *, user_id):
        assert user_id == "user-1"
        return SimpleNamespace(runs=[self.run_output] if self.run_output is not None else [])

    async def update_approval_run_status(self, run_id, status):
        self.status_updates.append((run_id, status))

    async def get_approvals(self, *, status=None, run_id=None, **_kwargs):
        if run_id == "run-1":
            return ([self.approval], 1)
        return ([], 0)


@pytest.mark.asyncio
async def test_schedule_resume_is_idempotent_for_completed_run():
    db = ResumeDb(approval=_security_approval(run_status="COMPLETED"))
    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(get_db=lambda: db)
    )

    assert await runtime.schedule_resume("approval-1") == "COMPLETED"
    assert db.status_updates == []
    assert runtime._resume_tasks == {}


@pytest.mark.asyncio
async def test_schedule_resume_deduplicates_active_background_task():
    db = ResumeDb()
    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(get_db=lambda: db)
    )
    started = asyncio.Event()

    async def pending_job(approval_id):
        assert approval_id == "approval-1"
        started.set()
        await asyncio.Event().wait()

    with patch.object(runtime, "_resume_job", new=pending_job):
        assert await runtime.schedule_resume("approval-1") == "RUNNING"
        await started.wait()
        assert await runtime.schedule_resume("approval-1") == "RUNNING"
        assert len(db.status_updates) == 1
        await runtime.shutdown()

    assert runtime._resume_tasks == {}


@pytest.mark.asyncio
async def test_failed_run_requires_explicit_retry():
    db = ResumeDb(approval=_security_approval(run_status="ERROR"))
    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(get_db=lambda: db)
    )
    with pytest.raises(ValueError, match="explicit retry"):
        await runtime.schedule_resume("approval-1")


@pytest.mark.asyncio
async def test_recover_resolved_runs_only_schedules_paused_or_running_security_runs():
    db = ResumeDb()

    async def get_approvals(*, status, **_kwargs):
        if status == "approved":
            return (
                [
                    _security_approval(id="approval-paused", run_status="PAUSED"),
                    _security_approval(id="approval-error", run_status="ERROR"),
                ],
                2,
            )
        return ([_security_approval(id="approval-running", status="rejected", run_status="RUNNING")], 1)

    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(get_db=lambda: db)
    )
    with (
        patch.object(db, "get_approvals", new=get_approvals),
        patch.object(runtime, "schedule_resume", new=AsyncMock(return_value="RUNNING")) as schedule,
    ):
        assert await runtime.recover_resolved_runs() == 2

    assert [call.args[0] for call in schedule.await_args_list] == [
        "approval-paused",
        "approval-running",
    ]


@pytest.mark.asyncio
async def test_resume_job_rejects_requirement_and_notifies_submitter_after_continuation():
    from agno.models.response import ToolExecution
    from agno.run.requirement import RunRequirement

    request = security_run_runtime.SecurityRunRequest.from_chat_args(
        "contain asset", session_id="session-1", user_id="user-1"
    )
    tool = ToolExecution(
        tool_name="hitl_simulate_containment",
        tool_call_id="call-1",
        requires_confirmation=True,
        approval_type="required",
        approval_id="approval-1",
    )
    requirement = RunRequirement(tool_execution=tool)
    run_output = SimpleNamespace(
        run_id="run-1",
        metadata={"tais_runtime": request.runtime_metadata()},
        requirements=[requirement],
        tools=[tool],
    )
    db = ResumeDb(
        approval=_security_approval(
            status="rejected",
            resolution_data={"note": "证据不足，暂不封禁"},
        ),
        run_output=run_output,
    )
    continued_kwargs = {}

    class ContinueAgent:
        def acontinue_run(self, **kwargs):
            continued_kwargs.update(kwargs)

            async def events():
                yield SimpleNamespace(event="RunCompleted")
                db.approval = {**db.approval, "run_status": "COMPLETED"}

            return events()

    @asynccontextmanager
    async def agent_context(_request):
        yield ContinueAgent()

    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(get_db=lambda: db)
    )
    with (
        patch.object(runtime, "security_agent_context", new=agent_context),
        patch.object(
            security_run_runtime,
            "notify_submitter_of_hitl_resolution",
            new=AsyncMock(),
        ) as notify,
    ):
        await runtime._resume_job("approval-1")

    assert tool.confirmed is False
    assert tool.confirmation_note == "Rejected by administrator: 证据不足，暂不封禁"
    assert run_output.metadata["approval"]["id"] == "approval-1"
    assert run_output.metadata["approval"]["status"] == "rejected"
    assert run_output.metadata["approval"]["resolution_data"] == {"note": "证据不足，暂不封禁"}
    assert continued_kwargs["run_response"] is run_output
    assert "requirements" not in continued_kwargs
    notify.assert_awaited_once()
    notify_call = notify.await_args
    assert notify_call is not None
    assert notify_call.kwargs["rejection_reason"] == "证据不足，暂不封禁"


@pytest.mark.asyncio
async def test_resume_job_marks_agno_run_and_trace_error_and_notifies_both_sides():
    db = ResumeDb()
    runtime = security_run_runtime.SecurityRunRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(get_db=lambda: db)
    )
    with (
        patch.object(
            runtime,
            "_load_approval_run",
            new=AsyncMock(side_effect=RuntimeError("continuation failed")),
        ),
        patch(
            "api.services.tracing_service.mark_trace_error",
            new=AsyncMock(),
        ) as mark_trace,
        patch.object(
            security_run_runtime,
            "notify_hitl_resume_failure",
            new=AsyncMock(),
        ) as notify,
    ):
        await runtime._resume_job("approval-1")

    assert db.status_updates == [("run-1", security_run_runtime.RunStatus.error)]
    mark_trace.assert_awaited_once_with("run-1")
    notify.assert_awaited_once()
    notify_call = notify.await_args
    assert notify_call is not None
    assert notify_call.kwargs["submitter_id"] == "user-1"
    assert notify_call.kwargs["error"] == "continuation failed"



@pytest.mark.asyncio
async def test_run_completed_falls_back_to_request_session_id():
    """Agno may omit session_id on RunCompleted; keep the request session for UI/history."""
    runtime = security_run_runtime.SecurityRunRuntime()

    class NoSessionCompletedAgent:
        async def arun(self, *_args, **_kwargs):
            yield {
                "event": "RunStarted",
                "run_id": "run-sess",
                "session_id": "session-client",
                "model": "test-model",
                "model_provider": "test",
            }
            yield {"event": "RunContent", "run_id": "run-sess", "content": "ok"}
            # Intentionally omit session_id on completed.
            yield {
                "event": "RunCompleted",
                "run_id": "run-sess",
                "metrics": {"total_tokens": 1},
            }

    events = [
        event
        async for event in runtime._stream_agent_events(
            NoSessionCompletedAgent(),
            security_run_runtime.SecurityRunRequest.from_chat_args(
                "hello",
                session_id="session-client",
                user_id="user-1",
            ),
        )
    ]
    completed = next(event for event in events if event.event == "run.completed")
    assert completed.data.get("session_id") == "session-client"

@pytest.mark.asyncio
async def test_stream_agent_events_emits_run_retrying_and_clears_partial_content_path():
    """Model-layer stream retry publishes run.retrying before the stream restarts."""
    runtime = security_run_runtime.SecurityRunRuntime()

    class RetryingModel:
        def __init__(self):
            self.retries = 2
            self.delay_between_retries = 0
            self.exponential_backoff = False
            self.name = "test"
            self.id = "test-model"
            self.calls = 0

        def classify_error(self, error):
            return error

        def _is_retryable_error(self, _error):
            return True

        def _get_retry_delay(self, _attempt):
            return 0

        async def ainvoke_stream(self, **_kwargs):
            self.calls += 1
            if self.calls == 1:
                from agno.exceptions import ModelProviderError

                raise ModelProviderError("auth_unavailable", status_code=503)
            if False:  # pragma: no cover
                yield None

        async def _ainvoke_stream_with_retry(self, **kwargs):
            # Placeholder replaced by notifier install.
            if False:  # pragma: no cover
                yield None

    model = RetryingModel()

    class RetryAgent:
        def __init__(self):
            self.model = model

        async def arun(self, *_args, **_kwargs):
            # Drive the patched stream retry path once so the notifier fires.
            async for _ in self.model._ainvoke_stream_with_retry():
                pass
            yield {
                "event": "RunStarted",
                "run_id": "run-retry",
                "session_id": "session-1",
                "model": "test-model",
                "model_provider": "test",
            }
            yield {"event": "RunContent", "run_id": "run-retry", "content": "recovered"}
            yield {
                "event": "RunCompleted",
                "run_id": "run-retry",
                "session_id": "session-1",
                "metrics": {"total_tokens": 1},
            }

    chunks = [
        event
        async for event in runtime._stream_agent_events(
            RetryAgent(),
            security_run_runtime.SecurityRunRequest.from_chat_args(
                "hello",
                session_id="session-1",
                user_id="user-1",
            ),
        )
    ]
    retry_events = [c for c in chunks if c.event == "run.retrying"]
    assert retry_events, chunks
    assert retry_events[0].data["attempt"] == 1
    assert retry_events[0].data["max_attempts"] == 3
    assert any(c.event == "content.delta" and c.data.get("delta") == "recovered" for c in chunks)



def test_security_operations_prompt_hygiene():
    """Base prompt must not advertise missing skills or full skill SOPs."""
    prompt = (
        Path(security_run_runtime.PROMPT_DIR)
        / security_run_runtime.SECURITY_OPERATIONS_PROMPT
    ).read_text(encoding="utf-8")
    assert "threat-trace-skill" not in prompt
    assert "darknet-trace-skill" not in prompt
    assert "get_skill_instructions" in prompt
    # Keep prompt lean relative to progressive skill loading.
    assert len(prompt) < 3500


@pytest.mark.asyncio
async def test_send_feishu_notify_uses_server_webhook_when_omitted(monkeypatch):
    from api.mcp.tools import basic as basic_tools
    from pydantic import SecretStr

    class _Settings:
        feishu_webhook_url = SecretStr("https://feishu.example/hook")

    posted: dict = {}

    class _Resp:
        status_code = 200

        def json(self):
            return {"code": 0}

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, headers=None, content=None):
            posted["url"] = url
            posted["content"] = content
            return _Resp()

    monkeypatch.setattr(basic_tools, "httpx", type("H", (), {"AsyncClient": _Client}))
    monkeypatch.setattr("api.config.get_settings", lambda: _Settings())
    result = await basic_tools.send_feishu_notify(title="t", content_md="c")
    assert result == {"code": 0, "msg": "success"}
    assert posted["url"] == "https://feishu.example/hook"



@pytest.mark.asyncio
async def test_enable_tools_false_skips_mcp_and_skills():
    created: dict = {}
    mcp_entered = {"value": False}

    class TrackingMcp:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            mcp_entered["value"] = True
            return self

        async def __aexit__(self, *_args):
            return None

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda *_a, **_k: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: [Path(temp_dir) / "skill"],
                get_mcp_url=lambda: "http://example/mcp",
                get_mcp_token=lambda: "tok",
                mcp_tools_factory=TrackingMcp,
                agent_factory=agent_factory,
            )
        )
        request = security_run_runtime.SecurityRunRequest.from_chat_args(
            "hello",
            enable_tools=False,
            search_knowledge=False,
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            async with runtime.security_agent_context(request):
                pass

    assert mcp_entered["value"] is False
    assert created["tools"] == []
    assert created["skills"] is None
    assert created["instructions"] == ["lite"]
    assert created["num_history_runs"] == 0
    assert created["add_history_to_context"] is False
    assert created["add_datetime_to_context"] is False
    assert created["add_memories_to_context"] is False
    assert created["enable_session_summaries"] is False
    assert created["session_summary_manager"] is None
    assert request.runtime_metadata()["enable_tools"] is False


@pytest.mark.asyncio
async def test_enable_tools_true_connects_mcp():
    mcp_entered = {"value": False}

    class TrackingMcp:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            mcp_entered["value"] = True
            return self

        async def __aexit__(self, *_args):
            return None

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda *_a, **_k: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: [],
                get_mcp_url=lambda: "http://example/mcp",
                get_mcp_token=lambda: "tok",
                mcp_tools_factory=TrackingMcp,
                agent_factory=lambda **_k: SimpleNamespace(),
            )
        )
        request = security_run_runtime.SecurityRunRequest.from_chat_args(
            "帮我做一次威胁研判", enable_tools=True
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            async with runtime.security_agent_context(request):
                pass

    assert mcp_entered["value"] is True
    assert request.skill_names is None



def test_infer_chat_skill_names_trivial_and_targeted():
    assert security_run_runtime.infer_chat_skill_names("ping") == []
    assert security_run_runtime.infer_chat_skill_names("Reply with exactly: pong") == []
    assert security_run_runtime.infer_chat_skill_names("hello") == []
    assert security_run_runtime.infer_chat_skill_names("CVE-2024-1234 风险如何") == [
        "cve-intel-skill"
    ]
    assert security_run_runtime.infer_chat_skill_names(
        "对主机 10.0.0.1 模拟隔离"
    ) == ["hitl-containment-skill"]
    assert security_run_runtime.infer_chat_skill_names("执行安全剧本排查") == [
        "playbook-skill"
    ]
    assert security_run_runtime.infer_chat_skill_names("查一下内网 NDR 告警") == [
        "intranet-ip-skill"
    ]
    # multi-match
    skills = security_run_runtime.infer_chat_skill_names(
        "CVE-2024-1 并用剧本处置"
    )
    assert skills == ["cve-intel-skill", "playbook-skill"]
    # general security ops → all enabled (None)
    assert security_run_runtime.infer_chat_skill_names("帮我做一次威胁研判") is None
    # non-security prose → no skills
    assert security_run_runtime.infer_chat_skill_names("用 Markdown 写一首短诗") == []


def test_from_chat_args_infers_and_preserves_skill_names():
    inferred = security_run_runtime.SecurityRunRequest.from_chat_args(
        "CVE-2024-9999 分析"
    )
    assert inferred.skill_names == ["cve-intel-skill"]
    assert inferred.runtime_metadata()["skill_names"] == ["cve-intel-skill"]

    explicit = security_run_runtime.SecurityRunRequest.from_chat_args(
        "CVE-2024-9999 分析",
        skill_names=["playbook-skill"],
    )
    assert explicit.skill_names == ["playbook-skill"]

    no_infer = security_run_runtime.SecurityRunRequest.from_chat_args(
        "CVE-2024-9999 分析",
        skill_names=None,
        infer_skills=False,
    )
    assert no_infer.skill_names is None

    tools_off = security_run_runtime.SecurityRunRequest.from_chat_args(
        "CVE-2024-9999 分析",
        enable_tools=False,
    )
    assert tools_off.skill_names == []
    assert tools_off.runtime_metadata()["skill_names"] == []
    assert tools_off.runtime_metadata()["enable_tools"] is False


@pytest.mark.asyncio
async def test_build_security_agent_filters_skills_by_inference():
    created: dict = {}
    skill_dirs = [
        Path("/skills/cve-intel-skill"),
        Path("/skills/playbook-skill"),
        Path("/skills/hitl-containment-skill"),
    ]

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    def resolve(names=None):
        if names is None:
            return skill_dirs
        wanted = set(names)
        return [p for p in skill_dirs if p.name in wanted]

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda *_a, **_k: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: skill_dirs,
                resolve_enabled_skill_dirs=resolve,
                get_mcp_url=lambda: "http://example/mcp",
                get_mcp_token=lambda: "tok",
                mcp_tools_factory=lambda **_k: SimpleNamespace(),
                agent_factory=agent_factory,
            )
        )
        request = security_run_runtime.SecurityRunRequest.from_chat_args(
            "分析 CVE-2024-1234",
            enable_tools=True,
            search_knowledge=False,
        )
        with (
            patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir),
            patch.object(
                security_run_runtime,
                "_load_local_skills",
                side_effect=lambda dirs: ("skills", list(dirs)),
            ),
        ):
            await runtime._build_security_agent(None, request)

    assert request.skill_names == ["cve-intel-skill"]
    assert created["skills"] == ("skills", ["/skills/cve-intel-skill"])


@pytest.mark.asyncio
async def test_build_security_agent_skips_skills_on_trivial_turn():
    created: dict = {}

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda *_a, **_k: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: [Path("/skills/cve-intel-skill")],
                get_mcp_url=lambda: "http://example/mcp",
                get_mcp_token=lambda: "tok",
                mcp_tools_factory=lambda **_k: SimpleNamespace(),
                agent_factory=agent_factory,
            )
        )
        request = security_run_runtime.SecurityRunRequest.from_chat_args(
            "ping",
            enable_tools=True,
            search_knowledge=False,
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            await runtime._build_security_agent(None, request)

    assert request.skill_names == []
    assert created["skills"] is None
    assert created["instructions"] == ["lite"]
    assert created["num_history_runs"] == 0
    assert created["add_history_to_context"] is False
    assert created["add_datetime_to_context"] is False



def test_should_connect_mcp_and_prefix_filter():
    assert security_run_runtime.should_connect_mcp(None, enable_tools=True) is True
    assert security_run_runtime.should_connect_mcp([], enable_tools=True) is False
    assert security_run_runtime.should_connect_mcp(["cve-intel-skill"], enable_tools=True) is True
    assert security_run_runtime.should_connect_mcp(None, enable_tools=False) is False

    assert security_run_runtime.mcp_prefixes_for_skills(None) is None
    assert security_run_runtime.mcp_prefixes_for_skills([]) == set()
    assert security_run_runtime.mcp_prefixes_for_skills(["cve-intel-skill"]) == {"basic_"}
    assert security_run_runtime.mcp_prefixes_for_skills(["hitl-containment-skill"]) == {
        "basic_",
        "hitl_",
    }
    assert security_run_runtime.mcp_prefixes_for_skills(["playbook-skill"]) == {
        "basic_",
        "playbook_",
    }
    assert security_run_runtime.mcp_prefixes_for_skills(
        ["hitl-containment-skill", "playbook-skill"]
    ) == {"basic_", "hitl_", "playbook_"}


def test_filter_mcp_tools_by_prefixes_keeps_external():
    from agno.tools.function import Function

    hitl = Function(name="hitl_simulate_containment", entrypoint=lambda: None)
    play = Function(name="playbook_list_workflows", entrypoint=lambda: None)
    basic = Function(name="basic_send_feishu_notify", entrypoint=lambda: None)
    external = Function(name="custom_scan", entrypoint=lambda: None)
    mcp_tools = SimpleNamespace(
        functions={
            hitl.name: hitl,
            play.name: play,
            basic.name: basic,
            external.name: external,
        },
        async_functions={},
    )
    removed = security_run_runtime.filter_mcp_tools_by_prefixes(
        mcp_tools, {"basic_", "hitl_"}
    )
    assert "playbook_list_workflows" in removed
    assert set(mcp_tools.functions) == {
        "hitl_simulate_containment",
        "basic_send_feishu_notify",
        "custom_scan",
    }


@pytest.mark.asyncio
async def test_trivial_turn_skips_mcp_connect_even_when_tools_enabled():
    mcp_entered = {"value": False}

    class TrackingMcp:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            mcp_entered["value"] = True
            return self

        async def __aexit__(self, *_args):
            return None

    created: dict = {}

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda *_a, **_k: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: [Path("/skills/cve-intel-skill")],
                get_mcp_url=lambda: "http://example/mcp",
                get_mcp_token=lambda: "tok",
                mcp_tools_factory=TrackingMcp,
                agent_factory=agent_factory,
            )
        )
        request = security_run_runtime.SecurityRunRequest.from_chat_args(
            "ping",
            enable_tools=True,
            search_knowledge=False,
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            async with runtime.security_agent_context(request):
                pass

    assert request.skill_names == []
    assert mcp_entered["value"] is False
    assert created["tools"] == []
    assert created["skills"] is None
    assert created["instructions"] == ["lite"]
    assert created["num_history_runs"] == 0
    assert created["add_history_to_context"] is False
    assert created["add_datetime_to_context"] is False
    assert created["add_memories_to_context"] is False
    assert created["enable_session_summaries"] is False
    assert created["session_summary_manager"] is None
    assert created["store_tool_messages"] is False



def test_is_lean_tool_surface():
    assert security_run_runtime.is_lean_tool_surface([], enable_tools=True) is True
    # tools-off is not auto-lite; clients badge via enable_tools
    assert security_run_runtime.is_lean_tool_surface(None, enable_tools=False) is False
    assert security_run_runtime.is_lean_tool_surface([], enable_tools=False) is False
    assert security_run_runtime.is_lean_tool_surface(None, enable_tools=True) is False
    assert security_run_runtime.is_lean_tool_surface(
        ["cve-intel-skill"], enable_tools=True
    ) is False


@pytest.mark.asyncio
async def test_lean_surface_skips_memory_context_when_memory_enabled():
    """Auto-lite / tools-off must not inject memories even if memory_enabled."""
    created: dict = {}

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda *_a, **_k: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: [],
                agent_factory=agent_factory,
            )
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            await runtime._build_security_agent(
                None,
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "ping",
                    enable_tools=True,
                    memory_enabled=True,
                    search_knowledge=True,
                ),
            )
    assert created["instructions"] == ["lite"]
    assert created["update_memory_on_run"] is True
    assert created["add_memories_to_context"] is False
    assert created["search_knowledge"] is False
    assert created["knowledge"] is None
    assert created["add_search_knowledge_instructions"] is False
    assert created["num_history_runs"] == 0
    assert created["add_history_to_context"] is False
    assert created["add_datetime_to_context"] is False


@pytest.mark.asyncio
async def test_lean_surface_keeps_short_history_with_session_id():
    """Continuing a lean session still loads a short history window."""
    created: dict = {}

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda *_a, **_k: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: [],
                agent_factory=agent_factory,
            )
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            await runtime._build_security_agent(
                None,
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "ping",
                    session_id="session-lean-1",
                    enable_tools=True,
                    search_knowledge=False,
                ),
            )
    assert created["instructions"] == ["lite"]
    assert created["num_history_runs"] == 2
    assert created["add_history_to_context"] is True
    assert created["add_datetime_to_context"] is False
    assert created["add_memories_to_context"] is False


@pytest.mark.asyncio
async def test_full_tool_surface_keeps_history_and_datetime():
    created: dict = {}

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    skill_dirs = [Path("/skills/cve-intel-skill")]

    def resolve(names=None):
        if names is None:
            return skill_dirs
        wanted = set(names)
        return [p for p in skill_dirs if p.name in wanted]

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda *_a, **_k: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: skill_dirs,
                resolve_enabled_skill_dirs=resolve,
                agent_factory=agent_factory,
            )
        )
        with (
            patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir),
            patch.object(
                security_run_runtime,
                "_load_local_skills",
                side_effect=lambda dirs: ("skills", list(dirs)),
            ),
        ):
            await runtime._build_security_agent(
                None,
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "分析 CVE-2024-1234",
                    session_id="session-full-1",
                    enable_tools=True,
                    search_knowledge=False,
                ),
            )
    assert created["instructions"] == ["full"]
    assert created["num_history_runs"] == 5
    assert created["add_history_to_context"] is True
    assert created["add_datetime_to_context"] is True
    assert created["add_memories_to_context"] is True


@pytest.mark.asyncio
async def test_lean_surface_skips_knowledge_even_when_requested():
    created: dict = {}
    kb_called = {"value": False}

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    def get_kb():
        kb_called["value"] = True
        return object()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda *_a, **_k: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=get_kb,
                get_enabled_skill_dirs=lambda: [],
                agent_factory=agent_factory,
            )
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            await runtime._build_security_agent(
                None,
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "hello",
                    enable_tools=False,
                    search_knowledge=True,
                    knowledge_owner_user_id="u1",
                ),
            )
    assert kb_called["value"] is False
    assert created["search_knowledge"] is False
    assert created["knowledge"] is None
    assert created["knowledge_filters"] is None
    assert created["add_search_knowledge_instructions"] is False


@pytest.mark.asyncio
async def test_full_tool_surface_loads_knowledge_when_requested():
    created: dict = {}
    kb = object()

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    skill_dirs = [Path("/skills/cve-intel-skill")]

    def resolve(names=None):
        if names is None:
            return skill_dirs
        wanted = set(names)
        return [p for p in skill_dirs if p.name in wanted]

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=lambda *_a, **_k: object(),
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: kb,
                get_enabled_skill_dirs=lambda: skill_dirs,
                resolve_enabled_skill_dirs=resolve,
                agent_factory=agent_factory,
            )
        )
        with (
            patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir),
            patch.object(
                security_run_runtime,
                "_load_local_skills",
                side_effect=lambda dirs: ("skills", list(dirs)),
            ),
        ):
            await runtime._build_security_agent(
                None,
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "分析 CVE-2024-1234",
                    enable_tools=True,
                    search_knowledge=True,
                    knowledge_owner_user_id="owner-1",
                ),
            )
    assert created["search_knowledge"] is True
    assert created["knowledge"] is kb
    assert created["knowledge_filters"] == {"user_id": "owner-1"}
    assert created["add_search_knowledge_instructions"] is True


@pytest.mark.asyncio
async def test_lean_surface_disables_live_search_even_when_requested():
    created: dict = {}
    models: list = []

    def agent_factory(**kwargs):
        created.update(kwargs)
        return SimpleNamespace()

    async def build_model(model_id=None, reasoning_effort=None, live_search=None):
        models.append({"live_search": live_search, "model_id": model_id})
        return object()

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=build_model,
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: [],
                agent_factory=agent_factory,
            )
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            await runtime._build_security_agent(
                None,
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "ping",
                    enable_tools=True,
                    live_search=True,
                    search_knowledge=True,
                ),
            )
    assert created["instructions"] == ["lite"]
    assert models and models[0]["live_search"] is False


@pytest.mark.asyncio
async def test_full_tool_surface_forwards_live_search():
    models: list = []
    skill_dirs = [Path("/skills/cve-intel-skill")]

    def agent_factory(**kwargs):
        return SimpleNamespace()

    async def build_model(model_id=None, reasoning_effort=None, live_search=None):
        models.append({"live_search": live_search})
        return object()

    def resolve(names=None):
        if names is None:
            return skill_dirs
        wanted = set(names)
        return [p for p in skill_dirs if p.name in wanted]

    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_PROMPT).write_text(
            "full", encoding="utf-8"
        )
        (prompt_dir / security_run_runtime.SECURITY_OPERATIONS_LITE_PROMPT).write_text(
            "lite", encoding="utf-8"
        )
        runtime = security_run_runtime.SecurityRunRuntime(
            security_run_runtime.SecurityRunRuntimeDependencies(
                build_model=build_model,
                get_db=lambda: object(),
                get_async_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: skill_dirs,
                resolve_enabled_skill_dirs=resolve,
                agent_factory=agent_factory,
            )
        )
        with (
            patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir),
            patch.object(
                security_run_runtime,
                "_load_local_skills",
                side_effect=lambda dirs: ("skills", list(dirs)),
            ),
        ):
            await runtime._build_security_agent(
                None,
                security_run_runtime.SecurityRunRequest.from_chat_args(
                    "分析 CVE-2024-1234",
                    enable_tools=True,
                    live_search=True,
                    search_knowledge=False,
                ),
            )
    assert models and models[0]["live_search"] is True

