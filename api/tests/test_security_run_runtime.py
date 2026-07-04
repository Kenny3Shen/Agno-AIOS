from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from api.services import security_run_runtime
import pytest


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

    def _build_fallback_agent(self, model_id=None):
        return FallbackAgent()


def test_load_prompt_reads_static_prompt_file():
    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / "agent.md").write_text("\n外置提示词\n", encoding="utf-8")
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            assert security_run_runtime._load_prompt("agent.md") == "外置提示词"


def test_load_prompt_rejects_empty_prompt_file():
    with TemporaryDirectory() as temp_dir:
        prompt_dir = Path(temp_dir)
        (prompt_dir / "agent.md").write_text("  \n", encoding="utf-8")
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            with pytest.raises(RuntimeError, match="提示词文件为空"):
                security_run_runtime._load_prompt("agent.md")


def test_security_agent_loads_prompt_when_agent_is_built():
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
                get_knowledge_base=lambda: object(),
                get_enabled_skill_dirs=lambda: [],
                agent_factory=agent_factory,
            )
        )
        with patch.object(security_run_runtime, "PROMPT_DIR", prompt_dir):
            runtime._build_security_agent(
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
            runtime._build_security_agent(
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


def test_fallback_agent_loads_prompt_when_agent_is_built():
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
            runtime._build_fallback_agent(model_id="model-1")
    assert created["instructions"] == ["降级提示词"]


def test_fallback_agent_keeps_memory_and_summary():
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
    runtime._build_fallback_agent(model_id="model-1")
    assert created["update_memory_on_run"]
    assert created["enable_session_summaries"]
    assert "tools" not in created
    assert "knowledge" not in created


@pytest.mark.asyncio
async def test_stream_agent_content_filters_run_content_events():
    chunks = [
        chunk
        async for chunk in security_run_runtime._stream_agent_content(
            FakeAgent(), "hello", session_id="session-1", user_id="u1"
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
async def test_mcp_url_includes_runtime_token():
    env = {
        "MCP_SERVER_URL": "http://127.0.0.1:8000/mcp/?transport=stream",
        "MCP_TOKEN": "secret token",
    }
    with patch.object(security_run_runtime.os, "environ", env):
        assert (
            security_run_runtime._build_mcp_url()
            == "http://127.0.0.1:8000/mcp/?transport=stream&token=secret+token"
        )


@pytest.mark.asyncio
async def test_security_run_request_drives_provider_block_fallback():
    runtime = BlockingRuntime(
        security_run_runtime.SecurityRunRuntimeDependencies(
            get_mcp_url=lambda: "http://127.0.0.1:8000/mcp/?token=test",
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
    assert "无工具安全模式" in chunks[0]
    assert chunks[1] == "fallback chunk"
