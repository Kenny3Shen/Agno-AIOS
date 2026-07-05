from dataclasses import dataclass
from pathlib import Path
from inspect import isawaitable
from typing import Any, AsyncIterator, Callable, cast
from urllib.parse import urlencode

from agno.agent import Agent
from agno.models.openai import OpenAILike
from agno.run.agent import RunEvent
from agno.skills import LocalSkills, Skills
from agno.tools.mcp import MCPTools
from anyio import Path as AsyncPath
from anyio import to_thread
from loguru import logger

from api.config import get_settings
from api.services.knowledge_service import get_async_knowledge_base_async

from api.services.model_config_service import get_model_for_run_async
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.skill_service import get_enabled_skill_dirs_async


async def _build_model_async(model_id: str | None = None) -> OpenAILike:
    model = await get_model_for_run_async(model_id)
    return OpenAILike(
        id=model["model_id"],
        api_key=model["api_key"],
        base_url=model["base_url"],
    )


def _get_mcp_token() -> str:
    return get_settings().mcp_token.get_secret_value().strip()


def _build_mcp_url() -> str:
    base_url = get_settings().mcp_server_url.strip()
    token = _get_mcp_token()
    if not base_url:
        raise RuntimeError("MCP_SERVER_URL 未配置，请在 .env 或系统配置中设置 MCP 服务地址。")
    if not token:
        raise RuntimeError("MCP_TOKEN 未配置，请在 .env 或系统配置中设置 MCP 访问 Token。")
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}{urlencode({'token': token})}"


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


def _is_provider_block_error(error: Exception) -> bool:
    message = str(error).lower()
    return any(marker in message for marker in PROVIDER_BLOCK_MARKERS)


@dataclass(frozen=True)
class SecurityRunRequest:
    """Security Operations Assistant 的一次 Run 请求。"""

    message: str
    session_id: str | None
    model_id: str | None
    user_id: str | None
    knowledge_owner_user_id: str | None

    @classmethod
    def from_chat_args(
        cls,
        message: str,
        session_id: str | None = None,
        model_id: str | None = None,
        user_id: str | None = None,
        knowledge_owner_user_id: str | None = None,
    ) -> "SecurityRunRequest":
        return cls(
            message=message,
            session_id=session_id,
            model_id=model_id,
            user_id=user_id,
            knowledge_owner_user_id=knowledge_owner_user_id,
        )

    @property
    def agent_user_id(self) -> str:
        return (self.user_id or "anonymous").strip() or "anonymous"


@dataclass(frozen=True)
class SecurityRunRuntimeDependencies:
    build_model: Callable[[str | None], Any] = _build_model_async
    get_db: Callable[[], Any] = get_async_agno_postgres_db
    get_async_knowledge_base: Callable[[], Any] = get_async_knowledge_base_async
    get_enabled_skill_dirs: Callable[[], Any] = get_enabled_skill_dirs_async
    get_mcp_url: Callable[[], str] = _build_mcp_url
    mcp_tools_factory: Callable[..., Any] = MCPTools
    agent_factory: Callable[..., Any] = Agent


class SecurityRunRuntime:
    """把安全运营助手 Run orchestration 收到一个 deep module 后面。"""

    def __init__(
        self,
        dependencies: SecurityRunRuntimeDependencies | None = None,
    ) -> None:
        self.dependencies = dependencies or SecurityRunRuntimeDependencies()

    async def _build_enabled_skills(self) -> Skills | None:
        enabled_dirs = [
            str(skill_dir)
            for skill_dir in await _maybe_await(self.dependencies.get_enabled_skill_dirs())
        ]
        if not enabled_dirs:
            return None
        return await to_thread.run_sync(_load_local_skills, enabled_dirs)

    async def _stream_agent_content(
        self,
        agent: Any,
        request: SecurityRunRequest,
    ) -> AsyncIterator[str]:
        async for event in agent.arun(
            request.message,
            session_id=request.session_id,
            user_id=request.agent_user_id,
            stream=True,
        ):
            event_type: str | None = None
            content: Any = None
            if isinstance(event, dict):
                event_dict = cast(dict[str, Any], event)
                event_type = event_dict.get("event")
                content = event_dict.get("content")
            else:
                event_type = getattr(event, "event", None)
                content = getattr(event, "content", None)

            if (
                event_type == RunEvent.run_content.value
                and isinstance(content, str)
                and content
            ):
                yield content

    async def build_fallback_agent(self, model_id: str | None = None) -> Agent:
        return self.dependencies.agent_factory(
            id="security-operations",
            name="安全防御助手",
            role="安全防御运营助手",
            description="无工具模式下的安全防御运营助手。",
            instructions=[await _load_prompt_async(SAFE_FALLBACK_PROMPT)],
            model=await _maybe_await(self.dependencies.build_model(model_id)),
            db=self.dependencies.get_db(),
            update_memory_on_run=True,
            enable_session_summaries=True,
            add_datetime_to_context=True,
            markdown=True,
        )

    async def _build_security_agent(
        self,
        mcp_tools: Any,
        request: SecurityRunRequest,
    ) -> Agent:
        return self.dependencies.agent_factory(
            id="security-operations",
            name="安全运营助手",
            role="安全运营综合专家",
            description="集威胁情报分析与安全剧本执行于一体的安全运营助手，可完成情报检索、深度分析和自动化处置全流程。",
            instructions=[await _load_prompt_async(SECURITY_OPERATIONS_PROMPT)],
            model=await _maybe_await(self.dependencies.build_model(request.model_id)),
            tools=[mcp_tools],
            knowledge=await _maybe_await(self.dependencies.get_async_knowledge_base()),
            knowledge_filters={"user_id": request.knowledge_owner_user_id}
            if request.knowledge_owner_user_id
            else None,
            search_knowledge=True,
            add_search_knowledge_instructions=True,
            skills=await self._build_enabled_skills(),
            db=self.dependencies.get_db(),
            dependencies=_agent_dependencies(),
            add_dependencies_to_context=True,
            add_history_to_context=True,
            update_memory_on_run=True,
            enable_session_summaries=True,
            num_history_runs=5,
            add_datetime_to_context=True,
            markdown=True,
        )

    async def stream(self, request: SecurityRunRequest) -> AsyncIterator[str]:
        try:
            async with self.dependencies.mcp_tools_factory(
                transport="streamable-http",
                url=self.dependencies.get_mcp_url(),
                timeout_seconds=20,
            ) as mcp_tools:
                security_agent = await _maybe_await(
                    self._build_security_agent(mcp_tools, request)
                )

                async for chunk in self._stream_agent_content(
                    security_agent,
                    request,
                ):
                    yield chunk
        except Exception as exc:
            if not _is_provider_block_error(exc):
                raise
            logger.warning("模型服务拦截完整 Agent 上下文，切换到无工具降级模式: {}", exc)
            yield "模型服务拦截了完整 Agent 上下文，已切换到无工具安全模式。\n\n"
            fallback_agent = await _maybe_await(self.build_fallback_agent(request.model_id))
            async for chunk in self._stream_agent_content(
                fallback_agent,
                request,
            ):
                yield chunk


DEFAULT_SECURITY_RUN_RUNTIME = SecurityRunRuntime()


async def _stream_agent_content(
    agent: Any,
    message: str,
    *,
    session_id: str | None,
    user_id: str | None,
) -> AsyncIterator[str]:
    request = SecurityRunRequest.from_chat_args(
        message,
        session_id=session_id,
        user_id=user_id,
    )
    async for chunk in DEFAULT_SECURITY_RUN_RUNTIME._stream_agent_content(
        agent,
        request,
    ):
        yield chunk


async def stream_security_run(
    request: SecurityRunRequest,
    *,
    runtime: SecurityRunRuntime | None = None,
) -> AsyncIterator[str]:
    active_runtime = runtime or DEFAULT_SECURITY_RUN_RUNTIME
    async for chunk in active_runtime.stream(request):
        yield chunk


async def stream_chat_with_agent(
    message: str,
    session_id: str | None = None,
    model_id: str | None = None,
    user_id: str | None = None,
    knowledge_owner_user_id: str | None = None,
) -> AsyncIterator[str]:
    """流式聊天，使用单个 Agent 统一处理安全运营任务"""
    request = SecurityRunRequest.from_chat_args(
        message,
        session_id=session_id,
        model_id=model_id,
        user_id=user_id,
        knowledge_owner_user_id=knowledge_owner_user_id,
    )
    async for chunk in stream_security_run(request):
        yield chunk
