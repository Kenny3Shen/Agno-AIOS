import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from inspect import isawaitable, iscoroutinefunction
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from agno.agent import Agent
from agno.approval import approval as require_approval
from agno.run.approval import acheck_and_apply_approval_resolution
from agno.run import RunStatus
from agno.run.agent import RunEvent
from agno.run.requirement import RunRequirement
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
from api.services.notification_service import (
    notify_admins_of_hitl_approval,
    notify_hitl_resume_failure,
    notify_submitter_of_hitl_resolution,
)
from api.services.chat_settings import get_chat_settings_async
from api.services.chat_run_events import (
    ChatRunEvent,
    completed_payload,
    event_value,
    paused_payload,
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
HITL_MCP_TOOL_PREFIX = "hitl_"
RUNTIME_METADATA_KEY = "tais_runtime"
RUNTIME_METADATA_VERSION = 1


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


def _mcp_header_provider(token: str) -> Callable[..., dict[str, str]]:
    def provide_headers(run_context: Any | None = None, **_kwargs: Any) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {token}"}
        if run_context is None:
            return headers
        headers.update(
            {
                "X-Agno-User-ID": str(getattr(run_context, "user_id", "") or ""),
                "X-Agno-Session-ID": str(getattr(run_context, "session_id", "") or ""),
                "X-Agno-Run-ID": str(getattr(run_context, "run_id", "") or ""),
            }
        )
        return headers

    return provide_headers


def mark_hitl_mcp_tools(mcp_tools: Any) -> list[str]:
    """Apply Agno's blocking approval decorator to the HITL MCP namespace."""
    marked: list[str] = []
    registries = (
        getattr(mcp_tools, "functions", None),
        getattr(mcp_tools, "async_functions", None),
    )
    seen: set[int] = set()
    for registry in registries:
        if not isinstance(registry, dict):
            continue
        for name, function in registry.items():
            if not str(name).startswith(HITL_MCP_TOOL_PREFIX) or id(function) in seen:
                continue
            require_approval(type="required")(function)
            seen.add(id(function))
            marked.append(str(name))
    return marked


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

    def runtime_metadata(self) -> dict[str, object]:
        return {
            "version": RUNTIME_METADATA_VERSION,
            "model_id": self.model_id or "",
            "reasoning_effort": self.reasoning_effort or "",
            "knowledge_owner_user_id": self.knowledge_owner_user_id or "",
            "memory_enabled": self.memory_enabled,
            "store_raw_tool_io": self.store_raw_tool_io,
        }

    @classmethod
    def from_run_metadata(
        cls,
        metadata: object,
        *,
        session_id: str,
        user_id: str,
    ) -> "SecurityRunRequest":
        root = metadata if isinstance(metadata, dict) else {}
        context = root.get(RUNTIME_METADATA_KEY)
        if not isinstance(context, dict):
            raise ValueError("Paused run is missing T.A.I.S runtime metadata")
        version = context.get("version")
        if not isinstance(version, int) or version != RUNTIME_METADATA_VERSION:
            raise ValueError("Paused run runtime metadata version is unsupported")
        return cls.from_chat_args(
            "Continue the approved security operation.",
            session_id=session_id,
            model_id=str(context.get("model_id") or "") or None,
            reasoning_effort=str(context.get("reasoning_effort") or "") or None,
            user_id=user_id,
            knowledge_owner_user_id=str(context.get("knowledge_owner_user_id") or "") or None,
            memory_enabled=bool(context.get("memory_enabled", True)),
            store_raw_tool_io=bool(context.get("store_raw_tool_io", False)),
        )


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
        self._resume_tasks: dict[str, asyncio.Task[None]] = {}

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

    @staticmethod
    def _is_security_chat_approval(approval_record: dict[str, Any]) -> bool:
        return (
            str(approval_record.get("source_type") or "") == "agent"
            and str(approval_record.get("agent_id") or "") == "security-operations"
            and bool(str(approval_record.get("run_id") or ""))
            and bool(str(approval_record.get("session_id") or ""))
            and bool(str(approval_record.get("user_id") or ""))
        )

    async def _load_approval_run(self, approval_record: dict[str, Any]) -> Any:
        if not self._is_security_chat_approval(approval_record):
            raise ValueError("Approval is not a resumable security chat run")
        session_id = str(approval_record["session_id"])
        user_id = str(approval_record["user_id"])
        run_id = str(approval_record["run_id"])
        session = await self.dependencies.get_db().get_session(
            session_id,
            user_id=user_id,
        )
        runs = getattr(session, "runs", None) if session is not None else None
        if not isinstance(runs, list):
            raise ValueError("Paused run session is missing")
        run_output = next(
            (item for item in runs if str(getattr(item, "run_id", "") or "") == run_id),
            None,
        )
        if run_output is None:
            raise ValueError("Paused run is missing from its Agno session")
        return run_output

    async def _drain_continuation(self, continued: Any) -> None:
        if hasattr(continued, "__aiter__"):
            async for _event in continued:
                pass
            return
        result = await continued
        if hasattr(result, "__aiter__"):
            async for _event in result:
                pass

    async def _resume_job(self, approval_id: str) -> None:
        db = self.dependencies.get_db()
        try:
            approval_record = await db.get_approval(approval_id)
            if not isinstance(approval_record, dict):
                raise ValueError("Approval not found")
            if str(approval_record.get("status") or "") not in {"approved", "rejected"}:
                raise ValueError("Approval must be resolved before resuming")

            run_output = await self._load_approval_run(approval_record)
            request = SecurityRunRequest.from_run_metadata(
                getattr(run_output, "metadata", None),
                session_id=str(approval_record["session_id"]),
                user_id=str(approval_record["user_id"]),
            )
            if str(approval_record["status"]) == "rejected":
                apply_rejection_note(
                    run_output,
                    approval_id=approval_id,
                    resolution_data=approval_record.get("resolution_data"),
                )
            # Let Agno update every persisted ToolExecution (both
            # RunOutput.tools and requirements) from its approval record.
            # Passing manually-mutated requirements here can leave those two
            # representations out of sync and turn an approved call into a
            # synthetic rejection during continuation.
            await acheck_and_apply_approval_resolution(
                db,
                str(approval_record["run_id"]),
                run_output,
            )
            async with self.security_agent_context(request) as agent:
                continue_kwargs: dict[str, Any] = {
                    "run_response": run_output,
                    "session_id": request.session_id,
                    "user_id": request.agent_user_id,
                    "stream": True,
                    "stream_events": True,
                }
                await self._drain_continuation(agent.acontinue_run(**continue_kwargs))

            if str(approval_record["status"]) == "approved" and not approved_tool_executed(
                run_output, approval_id
            ):
                raise RuntimeError("Approved HITL tool did not produce an execution result")

            refreshed = await db.get_approval(approval_id)
            final_approval = refreshed if isinstance(refreshed, dict) else approval_record
            final_run_status = str(final_approval.get("run_status") or "").upper()
            if final_run_status != RunStatus.completed.value:
                raise RuntimeError(
                    "Agno continuation ended without COMPLETED status: "
                    f"{final_run_status or 'UNKNOWN'}"
                )
            await notify_submitter_of_hitl_resolution(
                approval_id=approval_id,
                tool_name=str(final_approval.get("tool_name") or "tool"),
                submitter_id=str(final_approval.get("user_id") or ""),
                status=str(final_approval.get("status") or "approved"),
                rejection_reason=_approval_rejection_reason(final_approval.get("resolution_data")),
                run_id=str(final_approval.get("run_id") or ""),
                session_id=str(final_approval.get("session_id") or ""),
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("恢复 HITL Run 失败: {}", approval_id)
            approval_record = await db.get_approval(approval_id)
            if isinstance(approval_record, dict):
                run_id = str(approval_record.get("run_id") or "")
                if run_id:
                    await db.update_approval_run_status(run_id, RunStatus.error)
                    from api.services.tracing_service import mark_trace_error

                    await mark_trace_error(run_id)
                await notify_hitl_resume_failure(
                    approval_id=approval_id,
                    tool_name=str(approval_record.get("tool_name") or "tool"),
                    submitter_id=str(approval_record.get("user_id") or ""),
                    run_id=run_id,
                    session_id=str(approval_record.get("session_id") or ""),
                    error=str(exc)[:500],
                )

    def _forget_resume_task(self, approval_id: str, task: asyncio.Task[None]) -> None:
        if self._resume_tasks.get(approval_id) is task:
            self._resume_tasks.pop(approval_id, None)

    async def schedule_resume(
        self,
        approval_id: str,
        *,
        retry_error: bool = False,
    ) -> str:
        active = self._resume_tasks.get(approval_id)
        if active is not None and not active.done():
            return RunStatus.running.value

        db = self.dependencies.get_db()
        approval_record = await db.get_approval(approval_id)
        if not isinstance(approval_record, dict):
            raise ValueError("Approval not found")
        if not self._is_security_chat_approval(approval_record):
            raise ValueError("Approval is not a resumable security chat run")
        if str(approval_record.get("status") or "") not in {"approved", "rejected"}:
            raise ValueError("Approval must be resolved before resuming")

        run_status = str(approval_record.get("run_status") or "").upper()
        if run_status == RunStatus.completed.value:
            return RunStatus.completed.value
        if run_status == RunStatus.error.value and not retry_error:
            raise ValueError("Failed run requires an explicit retry")

        run_id = str(approval_record["run_id"])
        await db.update_approval_run_status(run_id, RunStatus.running)
        task = asyncio.create_task(
            self._resume_job(approval_id),
            name=f"hitl-resume:{approval_id}",
        )
        self._resume_tasks[approval_id] = task
        task.add_done_callback(lambda completed: self._forget_resume_task(approval_id, completed))
        return RunStatus.running.value

    async def recover_resolved_runs(self) -> int:
        recovered = 0
        db = self.dependencies.get_db()
        for status in ("approved", "rejected"):
            page = 1
            while True:
                rows, total = await db.get_approvals(status=status, limit=100, page=page)
                for approval_record in rows:
                    if not isinstance(approval_record, dict) or not self._is_security_chat_approval(approval_record):
                        continue
                    run_status = str(approval_record.get("run_status") or "").upper()
                    if run_status not in {RunStatus.paused.value, RunStatus.running.value}:
                        continue
                    await self.schedule_resume(str(approval_record["id"]))
                    recovered += 1
                if page * 100 >= int(total):
                    break
                page += 1
        return recovered

    async def shutdown(self) -> None:
        tasks = [task for task in self._resume_tasks.values() if not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._resume_tasks.clear()

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
                metadata={RUNTIME_METADATA_KEY: request.runtime_metadata()},
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
                elif event_type == RunEvent.run_paused.value:
                    paused = paused_payload(event)
                    approval_id = str(paused.get("approval_id") or "")
                    if approval_id and run_id:
                        session_id = str(paused.get("session_id") or request.session_id or "")
                        await notify_admins_of_hitl_approval(
                            approval_id=approval_id,
                            tool_name=str(paused.get("tool_name") or ""),
                            submitter_user_id=request.agent_user_id,
                            run_id=run_id,
                            session_id=session_id,
                        )
                    yield ChatRunEvent("run.paused", paused)
                    self.unregister_run(user_id=request.agent_user_id, run_id=run_id)
                    registered_run_ids.discard(run_id)
                elif event_type == RunEvent.run_continued.value:
                    yield ChatRunEvent("run.continued", {"run_id": run_id, "session_id": str(event_value(event, "session_id", "") or "")})
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
        token = await _run_sync_dependency(self.dependencies.get_mcp_token)
        server_params = StreamableHTTPClientParams(
            url=await _run_sync_dependency(self.dependencies.get_mcp_url),
        )
        async with self.dependencies.mcp_tools_factory(
            server_params=server_params,
            transport="streamable-http",
            timeout_seconds=20,
            header_provider=_mcp_header_provider(token),
        ) as mcp_tools:
            marked = mark_hitl_mcp_tools(mcp_tools)
            if marked:
                logger.debug("Agno required approval applied to MCP tools: {}", marked)
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



def _approval_rejection_reason(resolution_data: object) -> str:
    if not isinstance(resolution_data, dict):
        return ""
    return str(
        resolution_data.get("rejection_reason")
        or resolution_data.get("note")
        or ""
    ).strip()


def _rejection_confirmation_note(resolution_data: object) -> str:
    """Build the Agno ``confirmation_note`` used when a HITL tool is rejected."""
    reason = _approval_rejection_reason(resolution_data)
    return f"Rejected by administrator: {reason}" if reason else "Rejected by administrator"


def _requirements_for_run(run_output: Any) -> list[RunRequirement]:
    """Collect HITL requirements from a paused run, rebuilding from tools if needed."""
    requirements = list(getattr(run_output, "requirements", None) or [])
    if requirements:
        return requirements
    rebuilt: list[RunRequirement] = []
    for tool in list(getattr(run_output, "tools", None) or []):
        requires_confirmation = bool(getattr(tool, "requires_confirmation", False))
        approval_type = getattr(tool, "approval_type", None)
        if requires_confirmation or approval_type == "required":
            rebuilt.append(RunRequirement(tool_execution=tool))
    return rebuilt


def apply_approval_to_requirements(
    run_output: Any,
    *,
    approval_id: str,
    status: str,
    resolution_data: object,
) -> list[RunRequirement] | None:
    """Resolve Agno requirements while preserving an administrator rejection note."""
    if status not in {"approved", "rejected"}:
        raise ValueError(f"Approval is not resolved: {status or 'unknown'}")

    requirements = _requirements_for_run(run_output)
    if not requirements:
        return None
    targets = [
        requirement
        for requirement in requirements
        if str(getattr(getattr(requirement, "tool_execution", None), "approval_id", "") or "")
        == approval_id
    ]
    if not targets:
        # Agno can persist active approval requirements without copying the
        # approval record ID onto each ToolExecution. In that shape, resolve
        # every still-open confirmation requirement carried by this approval Run.
        targets = [
            requirement
            for requirement in requirements
            if getattr(requirement, "needs_confirmation", False)
        ]
    if not targets:
        return None

    rejection_note = _rejection_confirmation_note(resolution_data)
    applied = False
    for requirement in targets:
        if not getattr(requirement, "needs_confirmation", False):
            continue
        if status == "approved":
            requirement.confirm()
        else:
            requirement.reject(note=rejection_note)
        applied = True
    return requirements if applied else None


def apply_rejection_note(
    run_output: Any,
    *,
    approval_id: str,
    resolution_data: object,
) -> None:
    """Preserve the administrator note without resolving Agno's requirement."""
    note = _rejection_confirmation_note(resolution_data)
    for tool in list(getattr(run_output, "tools", None) or []):
        if str(getattr(tool, "approval_id", "") or "") == approval_id:
            tool.confirmation_note = note
    for requirement in _requirements_for_run(run_output):
        tool = getattr(requirement, "tool_execution", None)
        if tool is not None and str(getattr(tool, "approval_id", "") or "") == approval_id:
            tool.confirmation_note = note


def approved_tool_executed(run_output: Any, approval_id: str) -> bool:
    """A completed approval must correspond to a successful HITL tool result."""
    tools = [
        tool
        for tool in list(getattr(run_output, "tools", None) or [])
        if str(getattr(tool, "approval_id", "") or "") == approval_id
    ]
    return any(
        getattr(tool, "confirmed", None) is True
        and not bool(getattr(tool, "tool_call_error", False))
        and getattr(tool, "result", None) not in (None, "")
        for tool in tools
    )


async def resume_security_run(approval_id: str, *, retry_error: bool = False) -> str:
    return await DEFAULT_SECURITY_RUN_RUNTIME.schedule_resume(
        approval_id,
        retry_error=retry_error,
    )


async def recover_security_runs() -> int:
    return await DEFAULT_SECURITY_RUN_RUNTIME.recover_resolved_runs()


async def shutdown_security_runtime() -> None:
    await DEFAULT_SECURITY_RUN_RUNTIME.shutdown()
