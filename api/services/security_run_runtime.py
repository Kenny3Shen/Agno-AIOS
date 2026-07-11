from dataclasses import dataclass
from contextlib import asynccontextmanager
from pathlib import Path
from inspect import isawaitable, iscoroutinefunction
from typing import Any, AsyncIterator, Callable

from agno.agent import Agent
from agno.run.agent import RunEvent
from agno.session.summary import SessionSummaryManager
from agno.skills import LocalSkills, Skills
from agno.tools.mcp import MCPTools, StreamableHTTPClientParams
from anyio import Path as AsyncPath
from anyio import to_thread
from loguru import logger

from api.config import get_settings
from api.services.knowledge_service import get_async_knowledge_base_async

from api.services.model_config_service import get_model_for_run
from api.services.model_factory import build_agno_model
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.skill_service import get_enabled_skill_dirs
from api.services.chat_settings import get_chat_settings_async
from api.services.chat_run_events import (
    ChatRunEvent,
    completed_payload,
    event_value,
    source_items,
    tool_update,
)


async def _build_model(
    model_id: str | None = None,
    reasoning_effort: str | None = None,
) -> Any:
    config = await get_model_for_run(model_id)
    if reasoning_effort is None:
        return build_agno_model(config)
    return build_agno_model(config, reasoning_effort=reasoning_effort)


def _build_mcp_url() -> str:
    base_url = get_settings().mcp_server_url.strip()
    if not base_url:
        raise RuntimeError("MCP_SERVER_URL 未配置，请在 .env 或系统配置中设置 MCP 服务地址。")
    return base_url


def _build_mcp_token() -> str:
    token = get_settings().mcp_token.get_secret_value().strip()
    if not token:
        raise RuntimeError("MCP_TOKEN 未配置，请在 .env 或系统配置中设置 MCP 访问 Token。")
    return token


PROMPT_DIR = Path(__file__).resolve().parents[1] / "agent" / "prompts"
SECURITY_OPERATIONS_PROMPT = "security_operations.md"
SAFE_FALLBACK_PROMPT = "safe_fallback.md"


async def _load_prompt_async(filename: str) -> str:
    prompt_path = PROMPT_DIR / filename
    try:
        prompt = (await AsyncPath(prompt_path).read_text(encoding="utf-8")).strip()
    except OSError as exc:
        raise RuntimeError(f"无法读取 Agent 提示词文件: {prompt_path}") from exc
    if not prompt:
        raise RuntimeError(f"Agent 提示词文件为空: {prompt_path}")
    return prompt


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


async def _run_sync_dependency(func: Callable[..., Any], *args: Any) -> Any:
    if iscoroutinefunction(func):
        return await func(*args)
    return await _maybe_await(await to_thread.run_sync(func, *args))


PROVIDER_BLOCK_MARKERS = (
    "your request was blocked",
    "request was blocked",
    "blocked by",
    "content was blocked",
)


def _agent_dependencies() -> dict[str, str]:
    return {
        "feishu_webhook_url": get_settings().feishu_webhook_url.get_secret_value(),
    }


def _load_local_skills(enabled_dirs: list[str]) -> Skills:
    return Skills(loaders=[LocalSkills(path) for path in enabled_dirs])


def _session_summary_manager(model: Any) -> SessionSummaryManager:
    return SessionSummaryManager(model=model)


def _is_provider_block_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in PROVIDER_BLOCK_MARKERS)


@dataclass(frozen=True)
class SecurityRunRequest:
    """Security Operations Assistant 的一次 Run 请求。"""

    message: str
    session_id: str | None
    model_id: str | None
    reasoning_effort: str | None
    user_id: str | None
    knowledge_owner_user_id: str | None
    memory_enabled: bool = True
    store_raw_tool_io: bool = False

    @classmethod
    def from_chat_args(
        cls,
        message: str,
        session_id: str | None = None,
        model_id: str | None = None,
        reasoning_effort: str | None = None,
        user_id: str | None = None,
        knowledge_owner_user_id: str | None = None,
        memory_enabled: bool = True,
        store_raw_tool_io: bool = False,
    ) -> "SecurityRunRequest":
        return cls(
            message=message,
            session_id=session_id,
            model_id=model_id,
            reasoning_effort=reasoning_effort,
            user_id=user_id,
            knowledge_owner_user_id=knowledge_owner_user_id,
            memory_enabled=memory_enabled,
            store_raw_tool_io=store_raw_tool_io,
        )

    @property
    def agent_user_id(self) -> str:
        return (self.user_id or "anonymous").strip() or "anonymous"


@dataclass(frozen=True)
class SecurityRunRuntimeDependencies:
    build_model: Callable[..., Any] = _build_model
    get_db: Callable[[], Any] = get_async_agno_postgres_db
    get_async_knowledge_base: Callable[[], Any] = get_async_knowledge_base_async
    get_enabled_skill_dirs: Callable[[], Any] = get_enabled_skill_dirs
    get_mcp_url: Callable[[], str] = _build_mcp_url
    get_mcp_token: Callable[[], str] = _build_mcp_token
    mcp_tools_factory: Callable[..., Any] = MCPTools
    agent_factory: Callable[..., Any] = Agent


class SecurityRunRuntime:
    """把安全运营助手 Run orchestration 收到一个 deep module 后面。"""

    def __init__(
        self,
        dependencies: SecurityRunRuntimeDependencies | None = None,
    ) -> None:
        self.dependencies = dependencies or SecurityRunRuntimeDependencies()
        self._active_agents: dict[tuple[str, str], Any] = {}

    def register_run(self, *, user_id: str, run_id: str, agent: Any) -> None:
        if run_id:
            self._active_agents[(user_id, run_id)] = agent

    def unregister_run(self, *, user_id: str, run_id: str) -> None:
        if run_id:
            self._active_agents.pop((user_id, run_id), None)

    def cancel_run(self, *, user_id: str, run_id: str) -> bool:
        agent = self._active_agents.get((user_id, run_id))
        if agent is None:
            return False
        return bool(agent.cancel_run(run_id))

    async def _build_model(
        self,
        model_id: str | None,
        reasoning_effort: str | None,
    ) -> Any:
        if reasoning_effort is None:
            return await _run_sync_dependency(self.dependencies.build_model, model_id)
        return await _run_sync_dependency(
            self.dependencies.build_model,
            model_id,
            reasoning_effort,
        )

    async def _build_enabled_skills(self) -> Skills | None:
        enabled_dirs = [
            str(skill_dir)
            for skill_dir in await _run_sync_dependency(
                self.dependencies.get_enabled_skill_dirs
            )
        ]
        if not enabled_dirs:
            return None
        return await to_thread.run_sync(_load_local_skills, enabled_dirs)

    async def _stream_agent_events(
        self,
        agent: Any,
        request: SecurityRunRequest,
        chat_settings: Any | None = None,
    ) -> AsyncIterator[ChatRunEvent]:
        show_raw_reasoning = bool(getattr(chat_settings, "show_raw_reasoning", False))
        show_raw_tool_io = bool(getattr(chat_settings, "show_raw_tool_io", False))
        show_thought_chain = bool(getattr(chat_settings, "show_thought_chain", True))
        registered_run_ids: set[str] = set()
        try:
            async for event in agent.arun(
                request.message,
                session_id=request.session_id,
                user_id=request.agent_user_id,
                stream=True,
                stream_events=True,
            ):
                event_type = str(event_value(event, "event", ""))
                run_id = str(event_value(event, "run_id", "") or "")
                if event_type == RunEvent.run_started.value:
                    if run_id:
                        registered_run_ids.add(run_id)
                    self.register_run(user_id=request.agent_user_id, run_id=run_id, agent=agent)
                    yield ChatRunEvent("run.started", {
                        "run_id": run_id,
                        "session_id": str(event_value(event, "session_id", request.session_id or "") or ""),
                        "model": str(event_value(event, "model", "") or ""),
                        "provider": str(event_value(event, "model_provider", "") or ""),
                    })
                elif event_type == RunEvent.run_content.value:
                    content = event_value(event, "content")
                    if isinstance(content, str) and content:
                        yield ChatRunEvent("content.delta", {"run_id": run_id, "delta": content})
                elif event_type == RunEvent.reasoning_content_delta.value:
                    if show_raw_reasoning:
                        reasoning = event_value(event, "content", event_value(event, "reasoning", ""))
                        if isinstance(reasoning, str) and reasoning:
                            yield ChatRunEvent("reasoning.delta", {"run_id": run_id, "delta": reasoning})
                elif event_type in {RunEvent.reasoning_started.value, RunEvent.reasoning_step.value, RunEvent.reasoning_completed.value}:
                    if show_thought_chain:
                        completed = event_type == RunEvent.reasoning_completed.value
                        summary = event_value(event, "message", event_value(event, "content", ""))
                        yield ChatRunEvent("thought.update", {"run_id": run_id, "thought": {
                            "id": "reasoning", "type": "reasoning", "title": "模型推理",
                            "status": "completed" if completed else "running",
                            "summary": str(summary or "正在推理")[:280],
                        }})
                elif event_type == RunEvent.tool_call_started.value:
                    if show_thought_chain:
                        yield ChatRunEvent("tool.update", {"run_id": run_id, "tool": tool_update(event_value(event, "tool"), "running", include_raw_io=show_raw_tool_io)})
                elif event_type == RunEvent.tool_call_completed.value:
                    if show_thought_chain:
                        yield ChatRunEvent("tool.update", {"run_id": run_id, "tool": tool_update(event_value(event, "tool"), "completed", include_raw_io=show_raw_tool_io)})
                elif event_type == RunEvent.tool_call_error.value:
                    if show_thought_chain:
                        yield ChatRunEvent("tool.update", {"run_id": run_id, "tool": tool_update(event_value(event, "tool"), "error", include_raw_io=show_raw_tool_io)})
                elif event_type == RunEvent.run_completed.value:
                    sources = source_items(event_value(event, "citations")) or source_items(event_value(event, "references"))
                    if sources:
                        yield ChatRunEvent("sources", {"run_id": run_id, "items": sources})
                    yield ChatRunEvent("run.completed", completed_payload(event))
                    self.unregister_run(user_id=request.agent_user_id, run_id=run_id)
                    registered_run_ids.discard(run_id)
                elif event_type == RunEvent.run_cancelled.value:
                    yield ChatRunEvent("run.cancelled", {"run_id": run_id, "reason": str(event_value(event, "reason", "已停止生成") or "已停止生成")})
                    self.unregister_run(user_id=request.agent_user_id, run_id=run_id)
                    registered_run_ids.discard(run_id)
                elif event_type == RunEvent.run_error.value:
                    yield ChatRunEvent("run.failed", {"run_id": run_id, "code": "AGENT_RUN_ERROR", "message": "安全分析运行失败", "retryable": True})
                    self.unregister_run(user_id=request.agent_user_id, run_id=run_id)
                    registered_run_ids.discard(run_id)
        finally:
            for run_id in registered_run_ids:
                self.unregister_run(user_id=request.agent_user_id, run_id=run_id)

    async def build_fallback_agent(
        self,
        model_id: str | None = None,
        reasoning_effort: str | None = None,
        memory_enabled: bool = True,
    ) -> Agent:
        model = await self._build_model(model_id, reasoning_effort)
        return self.dependencies.agent_factory(
            id="security-operations",
            name="安全防御助手",
            role="安全防御运营助手",
            description="无工具模式下的安全防御运营助手。",
            instructions=[await _load_prompt_async(SAFE_FALLBACK_PROMPT)],
            model=model,
            db=self.dependencies.get_db(),
            update_memory_on_run=memory_enabled,
            add_memories_to_context=memory_enabled,
            store_tool_messages=False,
            enable_session_summaries=True,
            session_summary_manager=_session_summary_manager(model),
            add_datetime_to_context=True,
            markdown=True,
        )

    async def _build_security_agent(
        self,
        mcp_tools: Any,
        request: SecurityRunRequest,
    ) -> Agent:
        model = await self._build_model(request.model_id, request.reasoning_effort)
        return self.dependencies.agent_factory(
            id="security-operations",
            name="安全运营助手",
            role="安全运营综合专家",
            description="集威胁情报分析与安全剧本执行于一体的安全运营助手，可完成情报检索、深度分析和自动化处置全流程。",
            instructions=[await _load_prompt_async(SECURITY_OPERATIONS_PROMPT)],
            model=model,
            tools=[mcp_tools],
            knowledge=await _maybe_await(self.dependencies.get_async_knowledge_base()),
            knowledge_filters={"user_id": request.knowledge_owner_user_id}
            if request.knowledge_owner_user_id
            else None,
            search_knowledge=True,
            add_search_knowledge_instructions=True,
            skills=await self._build_enabled_skills(),
            db=self.dependencies.get_db(),
            dependencies=await _run_sync_dependency(_agent_dependencies),
            add_dependencies_to_context=True,
            add_history_to_context=True,
            update_memory_on_run=request.memory_enabled,
            add_memories_to_context=request.memory_enabled,
            store_tool_messages=request.store_raw_tool_io,
            enable_session_summaries=True,
            session_summary_manager=_session_summary_manager(model),
            num_history_runs=5,
            add_datetime_to_context=True,
            markdown=True,
        )

    @asynccontextmanager
    async def security_agent_context(self, request: SecurityRunRequest) -> AsyncIterator[Agent]:
        server_params = StreamableHTTPClientParams(
            url=await _run_sync_dependency(self.dependencies.get_mcp_url),
            headers={
                "Authorization": "Bearer "
                + await _run_sync_dependency(self.dependencies.get_mcp_token),
                "X-Agno-User-ID": request.agent_user_id,
                "X-Agno-Session-ID": request.session_id or "",
            },
        )
        async with self.dependencies.mcp_tools_factory(
            server_params=server_params,
            transport="streamable-http",
            timeout_seconds=20,
        ) as mcp_tools:
            security_agent = await _maybe_await(
                self._build_security_agent(mcp_tools, request)
            )
            yield security_agent

    async def stream(self, request: SecurityRunRequest) -> AsyncIterator[ChatRunEvent]:
        chat_settings = await get_chat_settings_async()
        try:
            async with self.security_agent_context(request) as security_agent:
                async for event in self._stream_agent_events(
                    security_agent,
                    request,
                    chat_settings,
                ):
                    yield event
        except Exception as exc:
            if not _is_provider_block_error(exc):
                raise
            logger.warning("模型服务拦截完整 Agent 上下文，切换到无工具降级模式: {}", exc)
            yield ChatRunEvent("content.delta", {"run_id": "", "delta": "模型服务拦截了完整 Agent 上下文，已切换到无工具安全模式。\n\n"})
            fallback_agent = await _maybe_await(
                self.build_fallback_agent(
                    request.model_id, memory_enabled=request.memory_enabled
                )
                if request.reasoning_effort is None
                else self.build_fallback_agent(
                    request.model_id,
                    request.reasoning_effort,
                    memory_enabled=request.memory_enabled,
                )
            )
            async for event in self._stream_agent_events(
                fallback_agent,
                request,
                chat_settings,
            ):
                yield event


DEFAULT_SECURITY_RUN_RUNTIME = SecurityRunRuntime()


async def stream_security_run(
    request: SecurityRunRequest,
    *,
    runtime: SecurityRunRuntime | None = None,
) -> AsyncIterator[ChatRunEvent]:
    active_runtime = runtime or DEFAULT_SECURITY_RUN_RUNTIME
    async for event in active_runtime.stream(request):
        yield event


def cancel_security_run(*, user_id: str, run_id: str) -> bool:
    return DEFAULT_SECURITY_RUN_RUNTIME.cancel_run(user_id=user_id, run_id=run_id)
