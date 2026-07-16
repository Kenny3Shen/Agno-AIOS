import asyncio
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from inspect import isawaitable, iscoroutinefunction
from pathlib import Path
from typing import Any, AsyncIterator, Callable

from agno.agent import Agent
from agno.exceptions import ModelProviderError, RetryableModelProviderError
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
from api.services.skill_service import get_enabled_skill_dirs, resolve_enabled_skill_dirs
from api.services.notification_service import (
    notify_admins_of_hitl_approval,
    notify_hitl_resume_failure,
    notify_submitter_of_hitl_resolution,
)
from api.services.chat_settings_service import get_chat_settings_async
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
    live_search: bool | None = None,
) -> Any:
    config = await get_model_for_run(model_id)
    if live_search is not None:
        config = {**config, "live_search_enabled": bool(live_search)}
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
SECURITY_OPERATIONS_LITE_PROMPT = "security_operations_lite.md"
SAFE_FALLBACK_PROMPT = "safe_fallback.md"
HITL_MCP_TOOL_PREFIX = "hitl_"
RUNTIME_METADATA_KEY = "tais_runtime"

RUNTIME_METADATA_VERSION = 1

# Chat skill attach: align with Workflow step skills[] (enabled ∩ wanted).
# None = all enabled; [] = none; non-empty = filter by skill dir/metadata name.
_TRIVIAL_TURN_RE = re.compile(
    r"^(?:hi|hello|hey|yo|thanks?|thank\s+you|thx|pong|ping|ok|okay|test|"
    r"你好|您好|在吗|谢谢|多谢|嗯+|好的|收到|测试)"
    r"[\s!.。！？~～]*$",
    re.IGNORECASE,
)
_INSTRUCTION_ONLY_RE = re.compile(
    r"^(?:reply with|say |output |print |respond with|只回复|仅回复|回答)[\s\S]{0,48}$",
    re.IGNORECASE,
)
_CVE_SKILL_RE = re.compile(
    r"cve-\d{4}-\d+|\bcve\b|漏洞|poc\b|exploit|0-?day|cve情报",
    re.IGNORECASE,
)
_HITL_SKILL_RE = re.compile(
    r"隔离|封禁|containment|\bisolat(?:e|ion)\b|\bblock(?:ed|ing)?\b|"
    r"模拟.*(?:隔离|封禁)|(?:隔离|封禁).*模拟",
    re.IGNORECASE,
)

_PLAYBOOK_SKILL_RE = re.compile(
    r"剧本|playbook|自动化.?处置|octomation",
    re.IGNORECASE,
)
_INTRANET_SKILL_RE = re.compile(
    r"内网|\bndr\b|intranet|doc_id|ndr告警",
    re.IGNORECASE,
)
_SECURITY_SIGNAL_RE = re.compile(
    r"cve|漏洞|poc|exploit|告警|威胁|研判|隔离|封禁|剧本|playbook|"
    r"内网|ndr|hitl|mcp|skill|知识库|情报|资产|攻击|malware|ransomware|"
    r"phishing|siem|soc|incident|ir\b|contain",
    re.IGNORECASE,
)


def _is_trivial_chat_turn(message: str) -> bool:
    text = message.strip()
    if not text:
        return True
    if _TRIVIAL_TURN_RE.match(text):
        return True
    if _INSTRUCTION_ONLY_RE.match(text):
        return True
    if len(text) <= 2 and not any(ch.isdigit() for ch in text):
        return True
    return False


def infer_chat_skill_names(message: str) -> list[str] | None:
    """Pick Local Skills for this Chat turn.

    Returns:
      - ``[]``: attach no skills (trivial / instruction-only / no security signal)
      - ``[names…]``: enabled ∩ these names
      - ``None``: keep all enabled skills (general security ops turn)
    """
    text = (message or "").strip()
    if not text or _is_trivial_chat_turn(text):
        return []
    matched: list[str] = []
    if _CVE_SKILL_RE.search(text):
        matched.append("cve-intel-skill")
    if _HITL_SKILL_RE.search(text):
        matched.append("hitl-containment-skill")
    if _PLAYBOOK_SKILL_RE.search(text):
        matched.append("playbook-skill")
    if _INTRANET_SKILL_RE.search(text):
        matched.append("intranet-ip-skill")
    if matched:
        # preserve stable order, unique
        seen: set[str] = set()
        ordered: list[str] = []
        for name in matched:
            if name not in seen:
                seen.add(name)
                ordered.append(name)
        return ordered
    if not _SECURITY_SIGNAL_RE.search(text):
        # General Q&A / non-ops: skip skill schemas (MCP still available when tools on).
        return []
    return None



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
    """Runtime tool deps for Agno.

    Secrets (e.g. Feishu webhook) stay server-side in MCP tools and must not be
    injected into the model context via ``add_dependencies_to_context``.
    """
    return {}


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
    search_knowledge: bool = True
    live_search: bool | None = None
    enable_tools: bool = True
    # None = all enabled skills; list = enabled ∩ names (Workflow-style).
    skill_names: list[str] | None = None

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
        search_knowledge: bool = True,
        live_search: bool | None = None,
        enable_tools: bool = True,
        skill_names: list[str] | None = None,
        *,
        infer_skills: bool = True,
    ) -> "SecurityRunRequest":
        resolved_skills = skill_names
        if skill_names is None and infer_skills:
            resolved_skills = infer_chat_skill_names(message)
        return cls(
            message=message,
            session_id=session_id,
            model_id=model_id,
            reasoning_effort=reasoning_effort,
            user_id=user_id,
            knowledge_owner_user_id=knowledge_owner_user_id,
            memory_enabled=memory_enabled,
            store_raw_tool_io=store_raw_tool_io,
            search_knowledge=search_knowledge,
            live_search=live_search,
            enable_tools=enable_tools,
            skill_names=resolved_skills,
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
            "search_knowledge": self.search_knowledge,
            "live_search": self.live_search,
            "enable_tools": self.enable_tools,
            "skill_names": list(self.skill_names)
            if self.skill_names is not None
            else None,
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
        live_raw = context.get("live_search")
        live_search: bool | None
        if live_raw is None:
            live_search = None
        else:
            live_search = bool(live_raw)
        raw_skills = context.get("skill_names")
        skill_names: list[str] | None
        if raw_skills is None:
            skill_names = None
        elif isinstance(raw_skills, list):
            skill_names = [str(item).strip() for item in raw_skills if str(item).strip()]
        else:
            skill_names = None
        return cls.from_chat_args(
            "Continue the approved security operation.",
            session_id=session_id,
            model_id=str(context.get("model_id") or "") or None,
            reasoning_effort=str(context.get("reasoning_effort") or "") or None,
            user_id=user_id,
            knowledge_owner_user_id=str(context.get("knowledge_owner_user_id") or "") or None,
            memory_enabled=bool(context.get("memory_enabled", True)),
            store_raw_tool_io=bool(context.get("store_raw_tool_io", False)),
            search_knowledge=bool(context.get("search_knowledge", True)),
            live_search=live_search,
            enable_tools=bool(context.get("enable_tools", True)),
            skill_names=skill_names,
            infer_skills=False,
        )


@dataclass(frozen=True)
class SecurityRunRuntimeDependencies:
    build_model: Callable[..., Any] = _build_model
    get_db: Callable[[], Any] = get_async_agno_postgres_db
    get_async_knowledge_base: Callable[[], Any] = get_async_knowledge_base_async
    get_enabled_skill_dirs: Callable[[], Any] = get_enabled_skill_dirs
    resolve_enabled_skill_dirs: Callable[..., Any] = resolve_enabled_skill_dirs
    get_mcp_url: Callable[[], str] = _build_mcp_url
    get_mcp_token: Callable[[], str] = _build_mcp_token
    mcp_tools_factory: Callable[..., Any] = MCPTools
    agent_factory: Callable[..., Any] = Agent



def _install_stream_retry_notifier(model: Any, queue: asyncio.Queue[dict[str, Any] | None]) -> Callable[[], None]:
    """Patch Agno model stream retry so workbench can surface attempt/delay to the UI.

    Agno restarts the entire stream on ModelProviderError; without a signal the
    Chat UI keeps partial content and looks non-streaming after a successful retry.
    """
    if model is None:
        return lambda: None
    original = getattr(model, "_ainvoke_stream_with_retry", None)
    if original is None or not callable(original):
        return lambda: None

    async def _ainvoke_stream_with_retry_notifying(self: Any, **kwargs: Any):
        last_exception: ModelProviderError | None = None
        retries_with_guidance_count = kwargs.pop("retries_with_guidance_count", 0)
        total_attempts = int(getattr(self, "retries", 0) or 0) + 1

        for attempt in range(total_attempts):
            try:
                async for response in self.ainvoke_stream(**kwargs):
                    yield response
                return
            except ModelProviderError as exc:
                last_exception = self.classify_error(exc)
                if not self._is_retryable_error(last_exception):
                    raise last_exception from exc
                if attempt < total_attempts - 1:
                    delay = float(self._get_retry_delay(attempt))
                    queue.put_nowait(
                        {
                            "attempt": attempt + 1,
                            "max_attempts": total_attempts,
                            "delay_seconds": delay,
                            "message": str(last_exception),
                        }
                    )
                    await asyncio.sleep(delay)
            except RetryableModelProviderError as exc:
                current_count = retries_with_guidance_count
                limit = int(getattr(self, "retry_with_guidance_limit", 0) or 0)
                if current_count >= limit:
                    raise ModelProviderError(
                        message=f"Max retries with guidance reached. Error: {exc.original_error}",
                        model_name=self.name,
                        model_id=self.id,
                    ) from exc
                kwargs.pop("retry_with_guidance", None)
                kwargs["retries_with_guidance_count"] = current_count + 1
                from agno.models.message import Message as AgnoMessage

                kwargs["messages"].append(
                    AgnoMessage(role="user", content=exc.retry_guidance_message, temporary=True)
                )
                async for response in self._ainvoke_stream_with_retry(
                    **kwargs, retry_with_guidance=True
                ):
                    yield response
                return

        if last_exception is not None:
            raise last_exception
        raise RuntimeError("Model stream retry exhausted without an exception")

    bound = _ainvoke_stream_with_retry_notifying.__get__(model, type(model))
    setattr(model, "_ainvoke_stream_with_retry", bound)

    def restore() -> None:
        setattr(model, "_ainvoke_stream_with_retry", original)

    return restore


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
                logger.error("HITL resume aborted: approval {} not found", approval_id)
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
            if not isinstance(approval_record, dict):
                logger.error(
                    "HITL resume failure for {} could not load approval for notifications: {}",
                    approval_id,
                    exc,
                )
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
        live_search: bool | None = None,
    ) -> Any:
        return await _run_sync_dependency(
            self.dependencies.build_model,
            model_id,
            reasoning_effort,
            live_search,
        )

    async def _build_enabled_skills(
        self,
        skill_names: list[str] | None = None,
    ) -> Skills | None:
        """Load Local Skills.

        ``skill_names`` mirrors Workflow step binding:
        None → all enabled; [] → none; list → enabled ∩ names.
        """
        if skill_names is not None and not skill_names:
            return None
        if skill_names is None:
            dirs_raw = await _run_sync_dependency(
                self.dependencies.get_enabled_skill_dirs
            )
        else:
            dirs_raw = await _run_sync_dependency(
                self.dependencies.resolve_enabled_skill_dirs,
                skill_names,
            )
        enabled_dirs = [str(skill_dir) for skill_dir in dirs_raw]
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
        retry_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        restore_retry = _install_stream_retry_notifier(
            getattr(agent, "model", None), retry_queue
        )
        active_run_id = ""
        agent_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        async def _produce_agent_events() -> None:
            try:
                async for event in agent.arun(
                    request.message,
                    session_id=request.session_id,
                    user_id=request.agent_user_id,
                    metadata={RUNTIME_METADATA_KEY: request.runtime_metadata()},
                    stream=True,
                    stream_events=True,
                ):
                    await agent_queue.put(("event", event))
            except BaseException as exc:
                await agent_queue.put(("error", exc))
            finally:
                await agent_queue.put(("done", None))

        def _retry_event(retry_info: dict[str, Any]) -> ChatRunEvent:
            return ChatRunEvent(
                "run.retrying",
                {
                    "run_id": active_run_id,
                    "attempt": retry_info.get("attempt"),
                    "max_attempts": retry_info.get("max_attempts"),
                    "delay_seconds": retry_info.get("delay_seconds"),
                    "message": str(retry_info.get("message") or ""),
                },
            )

        producer = asyncio.create_task(
            _produce_agent_events(), name="security-run-agent-events"
        )
        agent_waiter: asyncio.Task[tuple[str, Any]] | None = asyncio.create_task(
            agent_queue.get(), name="security-run-agent-wait"
        )
        retry_waiter: asyncio.Task[dict[str, Any] | None] | None = asyncio.create_task(
            retry_queue.get(), name="security-run-retry-wait"
        )
        try:
            while True:
                wait_set = {t for t in (agent_waiter, retry_waiter) if t is not None}
                done, _pending = await asyncio.wait(
                    wait_set, return_when=asyncio.FIRST_COMPLETED
                )
                if retry_waiter is not None and retry_waiter in done:
                    retry_info = retry_waiter.result()
                    retry_waiter = asyncio.create_task(retry_queue.get(), name="security-run-retry-wait")
                    if isinstance(retry_info, dict):
                        yield _retry_event(retry_info)
                if agent_waiter is None or agent_waiter not in done:
                    continue
                kind, payload = agent_waiter.result()
                if kind == "done":
                    agent_waiter = None
                    break
                if kind == "error":
                    agent_waiter = None
                    raise payload
                agent_waiter = asyncio.create_task(agent_queue.get(), name="security-run-agent-wait")
                event = payload
                event_type = str(event_value(event, "event", ""))
                run_id = str(event_value(event, "run_id", "") or "")
                if run_id:
                    active_run_id = run_id
                if event_type == RunEvent.run_started.value:
                    if run_id:
                        registered_run_ids.add(run_id)
                    self.register_run(
                        user_id=request.agent_user_id, run_id=run_id, agent=agent
                    )
                    yield ChatRunEvent(
                        "run.started",
                        {
                            "run_id": run_id,
                            "session_id": str(
                                event_value(
                                    event, "session_id", request.session_id or ""
                                )
                                or ""
                            ),
                            "model": str(event_value(event, "model", "") or ""),
                            "provider": str(
                                event_value(event, "model_provider", "") or ""
                            ),
                        },
                    )
                elif event_type == RunEvent.run_content.value:
                    content = event_value(event, "content")
                    if isinstance(content, str) and content:
                        yield ChatRunEvent(
                            "content.delta", {"run_id": run_id, "delta": content}
                        )
                elif event_type == RunEvent.reasoning_content_delta.value:
                    if show_raw_reasoning:
                        reasoning = event_value(
                            event, "content", event_value(event, "reasoning", "")
                        )
                        if isinstance(reasoning, str) and reasoning:
                            yield ChatRunEvent(
                                "reasoning.delta",
                                {"run_id": run_id, "delta": reasoning},
                            )
                elif event_type in {
                    RunEvent.reasoning_started.value,
                    RunEvent.reasoning_step.value,
                    RunEvent.reasoning_completed.value,
                }:
                    if show_thought_chain:
                        completed = event_type == RunEvent.reasoning_completed.value
                        summary = event_value(
                            event, "message", event_value(event, "content", "")
                        )
                        yield ChatRunEvent(
                            "thought.update",
                            {
                                "run_id": run_id,
                                "thought": {
                                    "id": "reasoning",
                                    "type": "reasoning",
                                    "title": "模型推理",
                                    "status": "completed" if completed else "running",
                                    "summary": str(summary or "正在推理")[:280],
                                },
                            },
                        )
                elif event_type == RunEvent.tool_call_started.value:
                    if show_thought_chain:
                        yield ChatRunEvent(
                            "tool.update",
                            {
                                "run_id": run_id,
                                "tool": tool_update(
                                    event_value(event, "tool"),
                                    "running",
                                    include_raw_io=show_raw_tool_io,
                                ),
                            },
                        )
                elif event_type == RunEvent.tool_call_completed.value:
                    if show_thought_chain:
                        yield ChatRunEvent(
                            "tool.update",
                            {
                                "run_id": run_id,
                                "tool": tool_update(
                                    event_value(event, "tool"),
                                    "completed",
                                    include_raw_io=show_raw_tool_io,
                                ),
                            },
                        )
                elif event_type == RunEvent.tool_call_error.value:
                    if show_thought_chain:
                        yield ChatRunEvent(
                            "tool.update",
                            {
                                "run_id": run_id,
                                "tool": tool_update(
                                    event_value(event, "tool"),
                                    "error",
                                    include_raw_io=show_raw_tool_io,
                                ),
                            },
                        )
                elif event_type == RunEvent.run_paused.value:
                    paused = paused_payload(event)
                    approval_id = str(paused.get("approval_id") or "")
                    if approval_id and run_id:
                        session_id = str(
                            paused.get("session_id") or request.session_id or ""
                        )
                        await notify_admins_of_hitl_approval(
                            approval_id=approval_id,
                            tool_name=str(paused.get("tool_name") or ""),
                            submitter_user_id=request.agent_user_id,
                            run_id=run_id,
                            session_id=session_id,
                        )
                    yield ChatRunEvent("run.paused", paused)
                    self.unregister_run(
                        user_id=request.agent_user_id, run_id=run_id
                    )
                    registered_run_ids.discard(run_id)
                elif event_type == RunEvent.run_continued.value:
                    yield ChatRunEvent(
                        "run.continued",
                        {
                            "run_id": run_id,
                            "session_id": str(
                                event_value(event, "session_id", "") or ""
                            ),
                        },
                    )
                elif event_type == RunEvent.run_completed.value:
                    sources = source_items(
                        event_value(event, "citations")
                    ) or source_items(event_value(event, "references"))
                    if sources:
                        yield ChatRunEvent(
                            "sources", {"run_id": run_id, "items": sources}
                        )
                    yield ChatRunEvent("run.completed", completed_payload(event))
                    self.unregister_run(
                        user_id=request.agent_user_id, run_id=run_id
                    )
                    registered_run_ids.discard(run_id)
                elif event_type == RunEvent.run_cancelled.value:
                    yield ChatRunEvent(
                        "run.cancelled",
                        {
                            "run_id": run_id,
                            "reason": str(
                                event_value(event, "reason", "已停止生成")
                                or "已停止生成"
                            ),
                        },
                    )
                    self.unregister_run(
                        user_id=request.agent_user_id, run_id=run_id
                    )
                    registered_run_ids.discard(run_id)
                elif event_type == RunEvent.run_error.value:
                    yield ChatRunEvent(
                        "run.failed",
                        {
                            "run_id": run_id,
                            "code": "AGENT_RUN_ERROR",
                            "message": "安全分析运行失败",
                            "retryable": True,
                        },
                    )
                    self.unregister_run(
                        user_id=request.agent_user_id, run_id=run_id
                    )
                    registered_run_ids.discard(run_id)
        finally:
            restore_retry()
            if not producer.done():
                producer.cancel()
                try:
                    await producer
                except asyncio.CancelledError:
                    pass
            for waiter in (agent_waiter, retry_waiter):
                if waiter is not None and not waiter.done():
                    waiter.cancel()
            while True:
                try:
                    retry_info = retry_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if isinstance(retry_info, dict):
                    yield _retry_event(retry_info)
            for run_id in registered_run_ids:
                self.unregister_run(user_id=request.agent_user_id, run_id=run_id)

    async def build_fallback_agent(
        self,
        model_id: str | None = None,
        reasoning_effort: str | None = None,
        memory_enabled: bool = True,
        live_search: bool | None = None,
    ) -> Agent:
        model = await self._build_model(model_id, reasoning_effort, live_search=live_search)
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
        mcp_tools: Any | None,
        request: SecurityRunRequest,
    ) -> Agent:
        model = await self._build_model(
            request.model_id,
            request.reasoning_effort,
            live_search=request.live_search,
        )
        knowledge = None
        search_knowledge = bool(request.search_knowledge)
        if search_knowledge:
            knowledge = await _maybe_await(self.dependencies.get_async_knowledge_base())
        enable_tools = bool(request.enable_tools)
        prompt_name = (
            SECURITY_OPERATIONS_PROMPT if enable_tools else SECURITY_OPERATIONS_LITE_PROMPT
        )
        tools = [mcp_tools] if enable_tools and mcp_tools is not None else []
        skills = (
            await self._build_enabled_skills(request.skill_names)
            if enable_tools
            else None
        )
        # Lean mode: shorter history, no session-summary manager (extra model work).
        history_runs = 5 if enable_tools else 2
        session_summaries = enable_tools
        return self.dependencies.agent_factory(
            id="security-operations",
            name="安全运营助手",
            description="安全运营助手：研判、知识检索、剧本与 HITL 处置。",
            instructions=[await _load_prompt_async(prompt_name)],
            model=model,
            tools=tools,
            knowledge=knowledge,
            knowledge_filters={"user_id": request.knowledge_owner_user_id}
            if request.knowledge_owner_user_id and search_knowledge
            else None,
            search_knowledge=search_knowledge,
            add_search_knowledge_instructions=search_knowledge,
            skills=skills,
            db=self.dependencies.get_db(),
            dependencies=await _run_sync_dependency(_agent_dependencies),
            add_dependencies_to_context=False,
            add_history_to_context=True,
            update_memory_on_run=request.memory_enabled,
            add_memories_to_context=request.memory_enabled,
            store_tool_messages=request.store_raw_tool_io,
            enable_session_summaries=session_summaries,
            session_summary_manager=_session_summary_manager(model) if session_summaries else None,
            num_history_runs=history_runs,
            add_datetime_to_context=True,
            markdown=True,
        )

    @asynccontextmanager
    async def security_agent_context(self, request: SecurityRunRequest) -> AsyncIterator[Agent]:
        if not request.enable_tools:
            security_agent = await _maybe_await(
                self._build_security_agent(None, request)
            )
            yield security_agent
            return

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
                    request.model_id,
                    memory_enabled=request.memory_enabled,
                    live_search=request.live_search,
                )
                if request.reasoning_effort is None
                else self.build_fallback_agent(
                    request.model_id,
                    request.reasoning_effort,
                    memory_enabled=request.memory_enabled,
                    live_search=request.live_search,
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
    # Agno convention: rejection text lives only in ``note``.
    return str(resolution_data.get("note") or "").strip()


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
