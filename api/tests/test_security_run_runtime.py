from pathlib import Path
import threading
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from agno.models.deepseek import DeepSeek
import pytest
from pydantic import SecretStr

from api.services import runtime_env, security_run_runtime


class FakeAgent:
    async def arun(self, *_args, **_kwargs):
        yield {"event": "RunContent", "content": "dict chunk"}
        yield {"event": "Other", "content": "ignored"}
        yield SimpleNamespace(event="RunContent", content="object chunk")
        yield SimpleNamespace(event="RunContent", content="")


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

    def build_fallback_agent(self, model_id=None):
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
async def test_stream_agent_content_filters_run_content_events():
    runtime = security_run_runtime.SecurityRunRuntime()
    chunks = [
        chunk
        async for chunk in runtime._stream_agent_content(
            FakeAgent(),
            security_run_runtime.SecurityRunRequest.from_chat_args(
                "hello",
                session_id="session-1",
                user_id="u1",
            ),
        )
    ]
    assert chunks == ["dict chunk", "object chunk"]


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
    assert chunks[0]
    assert chunks[1] == "fallback chunk"
