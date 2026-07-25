import asyncio
import re
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from inspect import isawaitable, iscoroutinefunction
from pathlib import Path
from types import SimpleNamespace
from typing import Any, AsyncIterator, Callable, Literal

from agno.agent import Agent
from agno.exceptions import ModelProviderError, RetryableModelProviderError
from agno.approval import approval as require_approval
from agno.run.approval import acheck_and_apply_approval_resolution
from agno.run import RunStatus
from agno.run.agent import RunEvent
from agno.run.team import TeamRunEvent
from agno.run.requirement import RunRequirement
from agno.session.summary import SessionSummaryManager
from agno.skills import LocalSkills, Skills
from agno.tools.mcp import MCPTools, StreamableHTTPClientParams
from anyio import Path as AsyncPath
from anyio import to_thread
from loguru import logger

from api.auth.claims import Role, normalize_actor_role
from api.config import get_settings
from api.persistence.durable_jobs import JobKind, JobState, retry_job
from api.services.durable_job_service import enqueue_durable_job
from api.services.knowledge_service import (
    build_knowledge_retriever,
    get_async_knowledge_base_async,
)

from api.services.model_config_service import get_model_for_run
from api.services.model_factory import build_agno_model
from api.services.postgres_store import get_async_agno_postgres_db
from api.mcp.config import issue_delegation_token
from api.services.capability_policy_service import (
    effective_mcp_server_names_for_actor,
    effective_skill_dirs_for_actor,
)
from api.services.skill_service import (
    get_enabled_skill_dirs,
    parse_skill_metadata,
    resolve_enabled_skill_dirs,
)
from api.services.notification_service import (
    notify_admins_of_hitl_approval,
    notify_hitl_resume_failure,
    notify_submitter_of_hitl_resolution,
)
from api.services.agent_catalog import (
    DEFAULT_AGENT_ID,
    get_agent_profile,
    profile_attaches_skills,
    profile_connects_mcp,
    resolve_chat_run_target,
)
from api.services.team_runtime import (
    build_team,
    get_team_profile,
    is_team_id,
    team_feature_enabled,
)
from api.services.agent_tools import (
    analysis_workspace_context,
    build_tools_for_profile,
    profile_uses_analysis_sandbox,
    stage_media_into_analysis_dir,
)
from api.services.chat_settings_service import (
    get_chat_settings_async,
    resolve_tool_call_limit,
)
from api.services.memory_capture import soc_memory_agent_instructions
from api.services.memory_manager_service import (
    build_memory_manager,
    capture_tool_content_memories,
)
from api.services.chat_run_events import (
    ChatRunEvent,
    completed_payload,
    event_value,
    paused_payload,
    source_items,
    team_tasks_payload,
    tool_update,
)
from api.services.guardrails import (
    apply_guardrails_kwargs,
    guardrail_failure_payload,
    is_input_check_error,
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

def _event_matches(event_type: str, name: str) -> bool:
    """True if event_type equals Agent or Team enum value for ``name``."""
    agent_ev = getattr(RunEvent, name, None)
    team_ev = getattr(TeamRunEvent, name, None)
    if agent_ev is not None and event_type == agent_ev.value:
        return True
    if team_ev is not None and event_type == team_ev.value:
        return True
    return False



def _agno_global_cancel(run_id: str) -> bool:
    """Store Agno cancellation intent by run_id (AgentOS cancel-before-start path)."""
    if not run_id:
        return False
    try:
        from agno.run.cancel import cancel_run as agno_cancel_run

        return bool(agno_cancel_run(run_id))
    except Exception:  # noqa: BLE001 — cancel is best-effort
        return False


async def _agno_global_acancel(run_id: str) -> bool:
    if not run_id:
        return False
    try:
        from agno.run.cancel import acancel_run as agno_acancel_run

        return bool(await agno_acancel_run(run_id))
    except Exception:  # noqa: BLE001
        return _agno_global_cancel(run_id)


def _invoke_runner_cancel(runner: Any | None, run_id: str) -> bool:
    """Cancel an Agno Agent/Team run (sync).

    Prefers instance/type ``cancel_run``, then global ``agno.run.cancel``.
    Agno exposes cancel as a ``@staticmethod``; tests may bind instance methods.
    """
    if not run_id:
        return False
    if runner is not None:
        inst = getattr(runner, "cancel_run", None)
        if callable(inst):
            try:
                return bool(inst(run_id))
            except TypeError:
                pass
        cls_fn = getattr(type(runner), "cancel_run", None)
        if callable(cls_fn):
            try:
                return bool(cls_fn(run_id))
            except TypeError:
                try:
                    return bool(cls_fn(runner, run_id))
                except Exception:
                    pass
    return _agno_global_cancel(run_id)


async def _ainvoke_runner_cancel(runner: Any | None, run_id: str) -> bool:
    """Cancel an Agno Agent/Team run (async; prefer ``acancel_run`` like AgentOS)."""
    if not run_id:
        return False
    if runner is not None:
        inst = getattr(runner, "acancel_run", None)
        if callable(inst):
            try:
                result = inst(run_id)
                if isawaitable(result):
                    result = await result
                return bool(result)
            except TypeError:
                pass
        cls_fn = getattr(type(runner), "acancel_run", None)
        if callable(cls_fn):
            try:
                result = cls_fn(run_id)
                if isawaitable(result):
                    result = await result
                return bool(result)
            except TypeError:
                try:
                    result = cls_fn(runner, run_id)
                    if isawaitable(result):
                        result = await result
                    return bool(result)
                except Exception:
                    pass
        # Sync cancel_run still marks the global manager immediately.
        synced = _invoke_runner_cancel(runner, run_id)
        if synced:
            return True
    return await _agno_global_acancel(run_id)


def _is_member_agent_event(event: Any) -> bool:
    """Member agent events during a Team run.

    Fully-identified member events have ``agent_id`` + ``parent_run_id`` and no
    ``team_id``. Agno also converts member ``RunContent`` into
    ``IntermediateRunContentEvent(content=...)`` (identity fields omitted) but
    still stamps ``parent_run_id`` when the Team forwards the stream — treat
    those as member so content never leaks into the leader answer.
    """
    team_id = str(event_value(event, "team_id", "") or "")
    if team_id:
        return False
    parent = str(event_value(event, "parent_run_id", "") or "")
    return bool(parent)


def _member_label(
    event: Any,
    *,
    fallback: tuple[str, str] | None = None,
) -> tuple[str, str]:
    member_id = str(event_value(event, "agent_id", "") or "").strip()
    if member_id:
        member_name = (
            str(event_value(event, "agent_name", "") or member_id).strip() or member_id
        )
        return member_id, member_name
    if fallback:
        return fallback
    return "member", "member"


def _resolve_member_identity(
    event: Any,
    *,
    by_run: dict[str, tuple[str, str]],
    last: list[tuple[str, str] | None],
) -> tuple[str, str]:
    """Resolve member id/name; remember last seen for identity-stripped deltas.

    Prefer ``run_id`` mapping (filled from earlier events with ``agent_id``).
    Fall back to the most recent member only when ``run_id`` is missing — never
    bind a *new* run_id to the previous member (broadcast/coordinate interleave).
    """
    run_id = str(event_value(event, "run_id", "") or "").strip()
    explicit_id = str(event_value(event, "agent_id", "") or "").strip()
    if explicit_id:
        name = (
            str(event_value(event, "agent_name", "") or explicit_id).strip()
            or explicit_id
        )
        identity = (explicit_id, name)
        last[0] = identity
        if run_id:
            by_run[run_id] = identity
        return identity
    if run_id and run_id in by_run:
        identity = by_run[run_id]
        last[0] = identity
        return identity
    if run_id:
        # Seen a new member run without identity yet; keep generic until agent_id
        # arrives so we don't mis-label as the previous member.
        return "member", "member"
    if last[0] is not None:
        return last[0]
    return "member", "member"


def _should_emit_member_thought(
    last_emit: dict[str, tuple[str, float]],
    *,
    member_id: str,
    summary: str,
    force: bool = False,
    min_interval_s: float = 0.25,
    min_growth: int = 12,
) -> bool:
    """Throttle member thought.update while streaming token deltas.

    Frontend merges by thought id, but unbounded SSE still wastes bandwidth
    (broadcast can emit 100+ content deltas per member).
    """
    now = time.monotonic()
    summary = (summary or "").strip()
    prev = last_emit.get(member_id)
    if force or prev is None:
        last_emit[member_id] = (summary, now)
        return True
    prev_summary, prev_t = prev
    if summary == prev_summary:
        return False
    grew = len(summary) - len(prev_summary)
    if (now - prev_t) >= min_interval_s or grew >= min_growth:
        last_emit[member_id] = (summary, now)
        return True
    return False



def _append_member_content_delta(
    acc: dict[str, str],
    *,
    member_id: str,
    delta: str,
    max_len: int = 280,
) -> str:
    """Accumulate member stream deltas into a rolling ThoughtChain summary."""
    if not delta:
        return acc.get(member_id, "")
    prev = acc.get(member_id, "")
    # If provider sends growing cumulative snapshots, avoid double-append.
    if prev and delta.startswith(prev):
        merged = delta
    elif prev and prev.endswith(delta):
        merged = prev
    else:
        merged = prev + delta
    if len(merged) > max_len:
        merged = merged[-max_len:]
    acc[member_id] = merged
    return merged




def _project_tool_update(
    event: Any,
    status: Literal["running", "completed", "error"],
    *,
    include_raw_io: bool = False,
) -> dict[str, Any]:
    """Project tool step; prefix member identity for Team member tools."""
    projected = tool_update(
        event_value(event, "tool"),
        status,
        include_raw_io=include_raw_io,
    )
    if not _is_member_agent_event(event):
        return projected
    member_id, member_name = _member_label(event)
    raw_id = str(projected.get("id") or "tool")
    raw_name = str(projected.get("name") or "工具调用")
    projected["id"] = f"member:{member_id}:{raw_id}"
    projected["name"] = f"[{member_name}] {raw_name}"
    projected["member_id"] = member_id
    projected["member_name"] = member_name
    return projected



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

_INTRANET_SKILL_RE = re.compile(
    r"内网|\bndr\b|intranet|doc_id|ndr告警",
    re.IGNORECASE,
)
_IP_BLACKLIST_SKILL_RE = re.compile(
    r"\b(?:\d{1,3}\.){3}\d{1,3}\b|"
    r"黑名单|blocklist|blacklist|ip.?reputation|威胁情报.?ip|"
    r"恶意.?ip|恶意外联|c2\b|botnet|firehol|spamhaus|dshield",
    re.IGNORECASE,
)
_SECURITY_SIGNAL_RE = re.compile(
    r"cve|漏洞|poc|exploit|告警|威胁|研判|隔离|封禁|工作流|workflow|"
    r"内网|ndr|hitl|mcp|skill|知识库|情报|资产|攻击|malware|ransomware|"
    r"phishing|siem|soc|incident|ir\b|contain|黑名单|blocklist|blacklist",
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
    if _INTRANET_SKILL_RE.search(text):
        matched.append("intranet-ip-skill")
    if _IP_BLACKLIST_SKILL_RE.search(text):
        matched.append("ip-blacklist-skill")
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


# Built-in MCP namespaces (FastMCP mount prefixes). External tools use other prefixes.
_BUILTIN_MCP_PREFIXES = ("basic_", "hitl_")
_SKILL_TO_MCP_PREFIXES: dict[str, tuple[str, ...]] = {
    "hitl-containment-skill": ("hitl_",),
    # cve-intel-skill / intranet-ip-skill are Local Skills only.
}


def should_connect_mcp(
    skill_names: list[str] | None,
    *,
    enable_tools: bool,
    agent_id: str | None = None,
) -> bool:
    """Skip MCP session when tools are off, agent has no MCP, or no skills attached.

    Trivial / non-ops turns set ``skill_names=[]``; connecting would still inject
    every MCP tool schema into the model context. Specialist agents
    (data-analysis / deep-research) never open MCP.
    """
    if not enable_tools:
        return False
    if is_team_id(agent_id):
        return False
    if not profile_connects_mcp(agent_id):
        return False
    if skill_names is not None and len(skill_names) == 0:
        return False
    return True


def is_lean_tool_surface(
    skill_names: list[str] | None,
    *,
    enable_tools: bool,
) -> bool:
    """True for **auto-intent lite** only: tools switch on, intent attached no skills.

    User tools-off (``enable_tools=False``) is a separate UI mode and must not set
    ``lean_mode`` — clients use ``enable_tools`` for that badge.
    """
    if not enable_tools:
        return False
    return skill_names is not None and len(skill_names) == 0


def mcp_prefixes_for_skills(skill_names: list[str] | None) -> set[str] | None:
    """Return allowed builtin MCP prefixes, or None for no filter (all tools).

    - ``None`` skill_names → all tools (general security ops)
    - ``[]`` → empty set (caller should skip connect)
    - named skills → union of mapped prefixes + always ``basic_`` for notify
    """
    if skill_names is None:
        return None
    if not skill_names:
        return set()
    prefixes: set[str] = {"basic_"}
    for name in skill_names:
        prefixes.update(_SKILL_TO_MCP_PREFIXES.get(str(name).strip(), ()))
    return prefixes


def filter_mcp_tools_by_prefixes(
    mcp_tools: Any,
    allowed_prefixes: set[str] | None,
) -> list[str]:
    """Drop builtin tools outside ``allowed_prefixes``; keep external tool names.

    Returns removed tool names. ``allowed_prefixes is None`` means keep all.
    """
    if allowed_prefixes is None:
        return []
    removed: list[str] = []
    registries = (
        getattr(mcp_tools, "functions", None),
        getattr(mcp_tools, "async_functions", None),
    )
    for registry in registries:
        if not isinstance(registry, dict):
            continue
        drop: list[str] = []
        for name in list(registry.keys()):
            tool_name = str(name)
            is_builtin = any(tool_name.startswith(p) for p in _BUILTIN_MCP_PREFIXES)
            if not is_builtin:
                continue
            if any(tool_name.startswith(p) for p in allowed_prefixes):
                continue
            drop.append(tool_name)
        for tool_name in drop:
            registry.pop(tool_name, None)
            if tool_name not in removed:
                removed.append(tool_name)
    return removed


@dataclass(frozen=True)
class SecurityRunRequest:
    """一次 Chat Agent Run 请求（默认安全运营；可切换数据分析/深度研究）。"""

    message: str
    session_id: str | None
    model_id: str | None
    reasoning_effort: str | None
    user_id: str | None
    knowledge_owner_user_id: str | None
    actor_role: Role = "user"
    actor_is_superuser: bool = False
    memory_enabled: bool = True
    store_raw_tool_io: bool = False
    search_knowledge: bool = True
    live_search: bool | None = None
    enable_tools: bool = True
    # Built-in agent profile id (security-operations | data-analysis | deep-research).
    agent_id: str = DEFAULT_AGENT_ID
    # None = all enabled skills; list = enabled ∩ names (Workflow-style).
    skill_names: list[str] | None = None
    effective_skill_names: tuple[str, ...] = ()
    effective_mcp_server_names: tuple[str, ...] = ()
    capability_snapshot_resolved: bool = False
    # Agno media forwarded to the model for this turn.
    images: tuple[Any, ...] = ()
    files: tuple[Any, ...] = ()
    # Raw attachments retained only for the isolated data-analysis / Team
    # workspace.  Docling-converted documents belong here so providers that do
    # not support ``file`` input receive their Markdown text only.
    workspace_files: tuple[Any, ...] = ()
    audio: tuple[Any, ...] = ()
    videos: tuple[Any, ...] = ()
    # Light UI metadata only (name/mime/kind); not sent to the model.
    attachments: tuple[dict[str, str], ...] = ()

    def __post_init__(self) -> None:
        """Freeze a canonical, fail-closed actor capability snapshot.

        Paused HITL runs restore this request from persisted JSON.  Only an
        actual JSON boolean ``true`` may retain superuser authority; a truthy
        malformed value such as the string ``"false"`` must not elevate it.
        """
        is_superuser = self.actor_is_superuser is True
        object.__setattr__(self, "actor_is_superuser", is_superuser)
        object.__setattr__(
            self,
            "actor_role",
            normalize_actor_role(self.actor_role, is_superuser=is_superuser),
        )

    @classmethod
    def from_chat_args(
        cls,
        message: str,
        session_id: str | None = None,
        model_id: str | None = None,
        reasoning_effort: str | None = None,
        user_id: str | None = None,
        knowledge_owner_user_id: str | None = None,
        actor_role: str = "user",
        actor_is_superuser: bool = False,
        memory_enabled: bool = True,
        store_raw_tool_io: bool = False,
        search_knowledge: bool = True,
        live_search: bool | None = None,
        enable_tools: bool = True,
        agent_id: str | None = None,
        skill_names: list[str] | None = None,
        images: tuple[Any, ...] | list[Any] | None = None,
        files: tuple[Any, ...] | list[Any] | None = None,
        workspace_files: tuple[Any, ...] | list[Any] | None = None,
        audio: tuple[Any, ...] | list[Any] | None = None,
        videos: tuple[Any, ...] | list[Any] | None = None,
        attachments: tuple[dict[str, str], ...] | list[dict[str, str]] | None = None,
        *,
        infer_skills: bool = True,
    ) -> "SecurityRunRequest":
        kind, resolved_agent = resolve_chat_run_target(agent_id)
        # Teams and specialist agents never attach security Local Skills.
        attaches_skills = kind == "agent" and profile_attaches_skills(resolved_agent)
        if not enable_tools or not attaches_skills:
            # Tools-off, team, or specialist agents: no Local Skills attach.
            resolved_skills: list[str] | None = []
        else:
            resolved_skills = skill_names
            if skill_names is None and infer_skills:
                resolved_skills = infer_chat_skill_names(message)
        normalized_superuser = actor_is_superuser is True
        return cls(
            message=message,
            session_id=session_id,
            model_id=model_id,
            reasoning_effort=reasoning_effort,
            user_id=user_id,
            knowledge_owner_user_id=knowledge_owner_user_id,
            actor_role=normalize_actor_role(
                actor_role, is_superuser=normalized_superuser
            ),
            actor_is_superuser=normalized_superuser,
            memory_enabled=memory_enabled,
            store_raw_tool_io=store_raw_tool_io,
            search_knowledge=search_knowledge,
            live_search=live_search,
            enable_tools=enable_tools,
            agent_id=resolved_agent,
            skill_names=resolved_skills,
            images=tuple(images or ()),
            files=tuple(files or ()),
            workspace_files=tuple(workspace_files or ()),
            audio=tuple(audio or ()),
            videos=tuple(videos or ()),
            attachments=tuple(attachments or ()),
        )

    @classmethod
    def from_eval_args(
        cls,
        message: str,
        *,
        target: object,
        session_id: str | None = None,
        model_id: str | None = None,
        reasoning_effort: str | None = None,
        user_id: str | None = None,
        knowledge_owner_user_id: str | None = None,
        actor_role: str = "user",
        actor_is_superuser: bool = False,
        memory_enabled: bool = False,
        store_raw_tool_io: bool = False,
        search_knowledge: bool = False,
        live_search: bool | None = None,
        enable_tools: bool = True,
    ) -> "SecurityRunRequest":
        """Build an Eval request without Chat's unknown-target fallback.

        Eval contracts are only meaningful if the declared target was the
        component that actually ran.  The Chat constructor intentionally has a
        friendlier defaulting rule for a stale browser preference; this strict
        constructor is deliberately separate so no Eval can inherit it.
        """
        from api.services.eval_targets import parse_eval_target

        resolved_target = parse_eval_target(target, require_available=True)
        attaches_skills = (
            resolved_target.kind == "agent"
            and profile_attaches_skills(resolved_target.id)
        )
        normalized_superuser = actor_is_superuser is True
        return cls(
            message=message,
            session_id=session_id,
            model_id=model_id,
            reasoning_effort=reasoning_effort,
            user_id=user_id,
            knowledge_owner_user_id=knowledge_owner_user_id,
            actor_role=normalize_actor_role(
                actor_role, is_superuser=normalized_superuser
            ),
            actor_is_superuser=normalized_superuser,
            memory_enabled=memory_enabled,
            store_raw_tool_io=store_raw_tool_io,
            search_knowledge=search_knowledge,
            live_search=live_search,
            enable_tools=enable_tools,
            agent_id=resolved_target.id,
            # Eval tool availability is explicit and stable: enabled ops
            # agents receive their entire allowed surface, while Teams and
            # specialist Agents never receive security Local Skills.
            skill_names=None if enable_tools and attaches_skills else [],
        )

    @property
    def agent_user_id(self) -> str:
        return (self.user_id or "anonymous").strip() or "anonymous"

    @property
    def memory_user_id(self) -> str | None:
        """Fail-closed owner for long-term memory (never anonymous/default)."""
        uid = (self.user_id or "").strip()
        if not uid or uid in {"anonymous", "default"}:
            return None
        return uid

    @property
    def capability_actor(self) -> Any:
        return SimpleNamespace(
            id=self.agent_user_id,
            role=self.actor_role,
            is_superuser=self.actor_is_superuser,
        )

    def runtime_metadata(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "version": RUNTIME_METADATA_VERSION,
            "agent_id": str(self.agent_id or DEFAULT_AGENT_ID),
            "model_id": self.model_id or "",
            "reasoning_effort": self.reasoning_effort or "",
            "knowledge_owner_user_id": self.knowledge_owner_user_id or "",
            "actor_role": self.actor_role,
            "actor_is_superuser": self.actor_is_superuser,
            "memory_enabled": self.memory_enabled,
            "store_raw_tool_io": self.store_raw_tool_io,
            "search_knowledge": self.search_knowledge,
            "live_search": self.live_search,
            "enable_tools": self.enable_tools,
            "skill_names": (
                list(self.effective_skill_names)
                if self.capability_snapshot_resolved
                else (list(self.skill_names) if self.skill_names is not None else None)
            ),
        }
        if self.capability_snapshot_resolved:
            payload["mcp_server_names"] = list(self.effective_mcp_server_names)
        if self.attachments:
            payload["attachments"] = [dict(item) for item in self.attachments]
        return payload

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
            actor_role=str(context.get("actor_role") or "user"),
            actor_is_superuser=context.get("actor_is_superuser") is True,
            memory_enabled=bool(context.get("memory_enabled", True)),
            store_raw_tool_io=bool(context.get("store_raw_tool_io", False)),
            search_knowledge=bool(context.get("search_knowledge", True)),
            live_search=live_search,
            enable_tools=bool(context.get("enable_tools", True)),
            agent_id=str(context.get("agent_id") or DEFAULT_AGENT_ID),
            skill_names=skill_names,
            infer_skills=False,
        )


@dataclass(frozen=True)
class SecurityRunRuntimeDependencies:
    build_model: Callable[..., Any] = _build_model
    get_db: Callable[[], Any] = get_async_agno_postgres_db
    get_async_knowledge_base: Callable[[], Any] = get_async_knowledge_base_async
    # Legacy hooks remain injectable for existing focused tests and extensions.
    # Production uses the actor-aware defaults below.
    get_enabled_skill_dirs: Callable[[], Any] = get_enabled_skill_dirs
    resolve_enabled_skill_dirs: Callable[..., Any] = resolve_enabled_skill_dirs
    effective_skill_dirs_for_actor: Callable[..., Any] = effective_skill_dirs_for_actor
    effective_mcp_server_names_for_actor: Callable[..., Any] = effective_mcp_server_names_for_actor
    get_mcp_url: Callable[[], str] = _build_mcp_url
    get_mcp_token: Callable[[], str] = _build_mcp_token
    issue_mcp_delegation_token: Callable[[str], str] = issue_delegation_token
    mcp_tools_factory: Callable[..., Any] = MCPTools
    agent_factory: Callable[..., Any] = Agent



async def _sleep_interruptible(
    delay: float,
    cancel_event: asyncio.Event | None,
    *,
    slice_seconds: float = 0.1,
) -> None:
    """Sleep that can be cut short when the workbench cancels the run."""
    remaining = max(0.0, float(delay))
    if cancel_event is None:
        if remaining:
            await asyncio.sleep(remaining)
        return
    while remaining > 0:
        if cancel_event.is_set():
            raise asyncio.CancelledError()
        step = min(slice_seconds, remaining)
        await asyncio.sleep(step)
        remaining -= step
    if cancel_event.is_set():
        raise asyncio.CancelledError()


def _install_stream_retry_notifier(
    model: Any,
    queue: asyncio.Queue[dict[str, Any] | None],
    cancel_event: asyncio.Event | None = None,
) -> Callable[[], None]:
    """Patch Agno model stream retry so workbench can surface attempt/delay to the UI.

    Agno restarts the entire stream on ModelProviderError; without a signal the
    Chat UI keeps partial content and looks non-streaming after a successful retry.

    ``cancel_event`` lets POST /chat/runs/{id}/cancel interrupt the retry backoff
    sleep (otherwise a multi-second delay would ignore stop until the next token).
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
                    await _sleep_interruptible(delay, cancel_event)
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


class _LiveChatStreamHub:
    """Fan-out buffer for one detached chat worker.

    Primary SSE and later re-attach clients all subscribe here. Leave-page
    cancels only the subscriber; the worker keeps publishing until COMPLETED.

    Mirrors AgentOS ``EventsBuffer`` + ``SSESubscriberManager`` patterns:
    monotonic ``event_index`` per event, bounded buffer, and optional
    ``last_event_index`` catch-up on re-attach.
    """

    # AgentOS default max_events_per_run is 10_000.
    MAX_EVENTS = 10_000

    __slots__ = ("buffer", "subscribers", "done", "error", "_lock", "_next_index")

    def __init__(self) -> None:
        self.buffer: list[ChatRunEvent] = []
        self.subscribers: list[asyncio.Queue[ChatRunEvent | BaseException | None]] = []
        self.done = False
        self.error: BaseException | None = None
        self._lock = asyncio.Lock()
        self._next_index = 0

    def _stamp(self, event: ChatRunEvent) -> ChatRunEvent:
        idx = self._next_index
        self._next_index += 1
        data = dict(event.data)
        data["event_index"] = idx
        return ChatRunEvent(event=event.event, data=data)

    @staticmethod
    def _event_index(event: ChatRunEvent) -> int | None:
        raw = event.data.get("event_index")
        if isinstance(raw, int):
            return raw
        if isinstance(raw, float) and raw.is_integer():
            return int(raw)
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
        return None

    def _events_after(self, last_event_index: int | None) -> list[ChatRunEvent]:
        """Events strictly after ``last_event_index`` (AgentOS get_events semantics)."""
        if last_event_index is None:
            return list(self.buffer)
        return [
            event
            for event in self.buffer
            if (idx := self._event_index(event)) is None or idx > last_event_index
        ]

    async def publish(self, event: ChatRunEvent) -> None:
        async with self._lock:
            stamped = self._stamp(event)
            self.buffer.append(stamped)
            if len(self.buffer) > self.MAX_EVENTS:
                self.buffer = self.buffer[-self.MAX_EVENTS :]
            targets = list(self.subscribers)
        for queue in targets:
            queue.put_nowait(stamped)

    async def finish(self, error: BaseException | None = None) -> None:
        async with self._lock:
            if self.done:
                return
            self.done = True
            self.error = error
            targets = list(self.subscribers)
            self.subscribers.clear()
        sentinel: BaseException | None = error
        for queue in targets:
            queue.put_nowait(sentinel)

    async def subscribe(
        self, *, last_event_index: int | None = None
    ) -> AsyncIterator[ChatRunEvent]:
        """Catch-up then live fan-out.

        Subscribe registration happens under the same lock as catch-up so events
        published mid-subscribe are not lost (AgentOS resume PATH 1 pattern).
        """
        queue: asyncio.Queue[ChatRunEvent | BaseException | None] = asyncio.Queue()
        async with self._lock:
            for event in self._events_after(last_event_index):
                queue.put_nowait(event)
            if self.done:
                queue.put_nowait(self.error)
            else:
                self.subscribers.append(queue)
        try:
            while True:
                item = await queue.get()
                if item is None:
                    return
                if isinstance(item, BaseException):
                    raise item
                # Dedup: live queue may race with catch-up on rare re-entrancy.
                if last_event_index is not None:
                    idx = self._event_index(item)
                    if idx is not None and idx <= last_event_index:
                        continue
                    if idx is not None:
                        last_event_index = idx
                yield item
        finally:
            async with self._lock:
                if queue in self.subscribers:
                    self.subscribers.remove(queue)


class SecurityRunRuntime:
    """把安全运营助手 Run orchestration 收到一个 deep module 后面。"""

    def __init__(
        self,
        dependencies: SecurityRunRuntimeDependencies | None = None,
    ) -> None:
        self.dependencies = dependencies or SecurityRunRuntimeDependencies()
        self._active_agents: dict[tuple[str, str], Any] = {}
        self._stream_cancels: dict[tuple[str, str], asyncio.Event] = {}
        # user_id -> cancel event for the in-flight chat stream (covers retry
        # backoff before run.started is processed / registered under run_id).
        self._user_stream_cancels: dict[str, asyncio.Event] = {}
        # (user_id, session_id) -> cancel event for the latest live stream on that
        # session. Leave-page keeps a detached worker; regenerate / a new turn on
        # the same session must supersede that worker so two Agno runs do not
        # race session persistence.
        self._session_stream_cancels: dict[tuple[str, str], asyncio.Event] = {}
        # (user_id, session_id) -> run_ids currently registered for that stream.
        self._session_run_ids: dict[tuple[str, str], set[str]] = {}
        # (user_id, session_id) -> live event hub for leave/return re-attach.
        self._session_live_hubs: dict[tuple[str, str], _LiveChatStreamHub] = {}

    def register_run(
        self,
        *,
        user_id: str,
        run_id: str,
        agent: Any,
        cancel_event: asyncio.Event | None = None,
        session_id: str | None = None,
    ) -> None:
        if not run_id:
            return
        key = (user_id, run_id)
        self._active_agents[key] = agent
        if cancel_event is not None:
            self._stream_cancels[key] = cancel_event
        session = str(session_id or "").strip()
        if user_id and session:
            self._session_run_ids.setdefault((user_id, session), set()).add(run_id)

    def unregister_run(
        self,
        *,
        user_id: str,
        run_id: str,
        session_id: str | None = None,
    ) -> None:
        if run_id:
            key = (user_id, run_id)
            self._active_agents.pop(key, None)
            self._stream_cancels.pop(key, None)
            session = str(session_id or "").strip()
            if user_id and session:
                runs = self._session_run_ids.get((user_id, session))
                if runs is not None:
                    runs.discard(run_id)
                    if not runs:
                        self._session_run_ids.pop((user_id, session), None)

    def cancel_run(self, *, user_id: str, run_id: str) -> bool:
        """Sync cancel (tests / supersede). Prefer :meth:`acancel_run` on request paths.

        Returns False when this owner has no live run and no in-flight stream
        cancel event (HTTP 404). Unlike bare AgentOS, we do not accept cancel for
        arbitrary run_ids without a known stream.
        """
        key = (user_id, run_id)
        cancel_event = self._stream_cancels.get(key) or self._user_stream_cancels.get(
            user_id
        )
        if cancel_event is not None:
            cancel_event.set()
        agent = self._active_agents.get(key)
        if agent is None:
            # Retry backoff / stream before agent registration: local Event is enough.
            # Still stamp Agno intent when we know the run_id.
            if cancel_event is not None and run_id:
                _agno_global_cancel(run_id)
            return cancel_event is not None
        cancelled = False
        try:
            cancelled = _invoke_runner_cancel(agent, run_id)
        except Exception as exc:  # noqa: BLE001 — cancel is best-effort
            logger.debug("cancel_run on runner failed run_id={}: {}", run_id, exc)
        return cancelled or cancel_event is not None

    async def acancel_run(self, *, user_id: str, run_id: str) -> bool:
        """Async cancel aligned with AgentOS ``await agent.acancel_run``."""
        key = (user_id, run_id)
        cancel_event = self._stream_cancels.get(key) or self._user_stream_cancels.get(
            user_id
        )
        if cancel_event is not None:
            cancel_event.set()
        agent = self._active_agents.get(key)
        if agent is None:
            if cancel_event is not None and run_id:
                await _agno_global_acancel(run_id)
            return cancel_event is not None
        cancelled = False
        try:
            cancelled = await _ainvoke_runner_cancel(agent, run_id)
        except Exception as exc:  # noqa: BLE001
            logger.debug("acancel_run on runner failed run_id={}: {}", run_id, exc)
        return cancelled or cancel_event is not None

    def supersede_session_stream(
        self,
        *,
        user_id: str,
        session_id: str,
        keep_cancel: asyncio.Event | None = None,
    ) -> bool:
        """Cancel any prior live stream for this session (regenerate / new turn).

        Leave-page detaches the SSE consumer but keeps Agno running. Starting a
        new chat on the same session must stop that background worker so the
        new run is the only writer of session history.
        """
        owner = str(user_id or "").strip()
        session = str(session_id or "").strip()
        if not owner or not session:
            return False
        session_key = (owner, session)
        previous = self._session_stream_cancels.get(session_key)
        cancelled = False
        if previous is not None and previous is not keep_cancel:
            previous.set()
            cancelled = True
            # Only drop the hub when we actually superseded a prior stream.
            # Same-stream re-entry (keep_cancel is the active event) must leave
            # the live hub registered for leave/return re-attach.
            self._session_live_hubs.pop(session_key, None)
        run_ids = list(self._session_run_ids.get(session_key) or ())
        for run_id in run_ids:
            if self.cancel_run(user_id=owner, run_id=run_id):
                cancelled = True
        return cancelled

    def get_live_hub(
        self, *, user_id: str, session_id: str
    ) -> _LiveChatStreamHub | None:
        owner = str(user_id or "").strip()
        session = str(session_id or "").strip()
        if not owner or not session:
            return None
        hub = self._session_live_hubs.get((owner, session))
        if hub is None:
            return None
        return hub

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

    async def _resume_job(self, approval_id: str) -> str:
        """Continue one resolved security HITL run in the calling worker.

        This deliberately contains no task scheduling.  The durable-job worker
        owns process lifetime, leasing, and retries; keeping the actual Agno
        continuation here also preserves the existing failure status and
        notification behavior for both a fresh worker and a recovered lease.
        """
        db = self.dependencies.get_db()
        try:
            approval_record = await db.get_approval(approval_id)
            if not isinstance(approval_record, dict):
                logger.error("HITL resume aborted: approval {} not found", approval_id)
                raise ValueError("Approval not found")
            if str(approval_record.get("status") or "") not in {"approved", "rejected"}:
                raise ValueError("Approval must be resolved before resuming")
            current_run_status = str(approval_record.get("run_status") or "").upper()
            if current_run_status == RunStatus.completed.value:
                # A worker can be reclaimed after Agno persisted completion but
                # before it recorded the durable job's terminal state.  Do not
                # continue the already-completed tool call a second time.  The
                # resolution notification is deliberately at-least-once: the
                # prior worker may have exited before it emitted it.
                await notify_submitter_of_hitl_resolution(
                    approval_id=approval_id,
                    tool_name=str(approval_record.get("tool_name") or "tool"),
                    submitter_id=str(approval_record.get("user_id") or ""),
                    status=str(approval_record.get("status") or "approved"),
                    rejection_reason=_approval_rejection_reason(
                        approval_record.get("resolution_data")
                    ),
                    run_id=str(approval_record.get("run_id") or ""),
                    session_id=str(approval_record.get("session_id") or ""),
                )
                return RunStatus.completed.value
            if current_run_status == RunStatus.error.value:
                # A reclaimed lease must not turn an already-failed run into
                # an implicit retry.  The approval retry endpoint transitions
                # it back to RUNNING before requeuing the durable job.
                return RunStatus.error.value

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
            return RunStatus.completed.value
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
            return RunStatus.error.value

    async def schedule_resume(
        self,
        approval_id: str,
        *,
        retry_error: bool = False,
    ) -> str:
        normalized_approval_id = str(approval_id or "").strip()
        if not normalized_approval_id:
            raise ValueError("approval_id is required")
        db = self.dependencies.get_db()
        approval_record = await db.get_approval(normalized_approval_id)
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
        # A recovered process may find a run already marked RUNNING after the
        # old API process died between status persistence and enqueueing.  It
        # still needs to enqueue below, but does not need another status write.
        if run_status != RunStatus.running.value:
            await db.update_approval_run_status(run_id, RunStatus.running)
        job = await enqueue_durable_job(
            kind=JobKind.SECURITY_HITL_RESUME,
            payload={"approval_id": normalized_approval_id},
            idempotency_key=f"security-hitl-resume:{normalized_approval_id}",
        )
        # A manual retry is the one case in which a terminal idempotent row
        # must run again.  Retrying the same row retains its audit trail and
        # prevents a second continuation from being enqueued concurrently.
        if retry_error and job.state in {JobState.FAILED, JobState.CANCELLED}:
            await retry_job(job.id)
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
        """Keep lifecycle compatibility without cancelling durable work.

        Security continuations are leased by the standalone durable worker,
        not this API process.  Cancelling them during API shutdown would make
        deployment ordering affect an already accepted approval.
        """
        return None

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

    async def _resolve_effective_capabilities(
        self, request: SecurityRunRequest
    ) -> SecurityRunRequest:
        """Snapshot the user-effective surface once for this Agent run."""
        if request.capability_snapshot_resolved:
            return request
        if not request.enable_tools:
            return replace(
                request,
                effective_skill_names=(),
                effective_mcp_server_names=(),
                capability_snapshot_resolved=True,
            )

        skill_names: tuple[str, ...] = ()
        if profile_attaches_skills(request.agent_id):
            dirs_raw = await self._resolve_skill_dirs_for_request(request)
            skill_names = tuple(
                parse_skill_metadata(Path(directory)).name for directory in dirs_raw
            )

        mcp_names_raw: list[str] = []
        if profile_connects_mcp(request.agent_id) and not self._uses_legacy_skill_hooks():
            mcp_names_raw = await _run_sync_dependency(
                self.dependencies.effective_mcp_server_names_for_actor,
                request.capability_actor,
            )
        return replace(
            request,
            effective_skill_names=skill_names,
            effective_mcp_server_names=tuple(str(name) for name in mcp_names_raw),
            capability_snapshot_resolved=True,
        )

    async def _build_enabled_skills(
        self, request: SecurityRunRequest | None = None
    ) -> Skills | None:
        """Load Local Skills.

        ``skill_names`` mirrors Workflow step binding:
        None → all enabled; [] → none; list → enabled ∩ names.
        """
        if request is None:
            dirs_raw = await _run_sync_dependency(
                self.dependencies.get_enabled_skill_dirs
            )
            enabled_dirs = [str(skill_dir) for skill_dir in dirs_raw]
            if not enabled_dirs:
                return None
            return await to_thread.run_sync(_load_local_skills, enabled_dirs)
        skill_names = request.skill_names
        if skill_names is not None and not skill_names:
            return None
        dirs_raw = await self._resolve_skill_dirs_for_request(request)
        enabled_dirs = [str(skill_dir) for skill_dir in dirs_raw]
        if not enabled_dirs:
            return None
        return await to_thread.run_sync(_load_local_skills, enabled_dirs)

    def _uses_legacy_skill_hooks(self) -> bool:
        effective_skill_resolver = getattr(
            self.dependencies,
            "effective_skill_dirs_for_actor",
            effective_skill_dirs_for_actor,
        )
        legacy_resolver = getattr(
            self.dependencies,
            "resolve_enabled_skill_dirs",
            resolve_enabled_skill_dirs,
        )
        legacy_mcp_token = getattr(
            self.dependencies,
            "get_mcp_token",
            _build_mcp_token,
        )
        return (
            effective_skill_resolver is effective_skill_dirs_for_actor
            and (
                self.dependencies.get_enabled_skill_dirs is not get_enabled_skill_dirs
                or legacy_resolver is not resolve_enabled_skill_dirs
                or legacy_mcp_token is not _build_mcp_token
            )
        )

    async def _resolve_skill_dirs_for_request(
        self, request: SecurityRunRequest
    ) -> Any:
        if self._uses_legacy_skill_hooks():
            if request.skill_names is None:
                return await _run_sync_dependency(
                    self.dependencies.get_enabled_skill_dirs
                )
            return await _run_sync_dependency(
                self.dependencies.resolve_enabled_skill_dirs,
                request.skill_names,
            )
        return await _run_sync_dependency(
            self.dependencies.effective_skill_dirs_for_actor,
            request.capability_actor,
            request.skill_names,
        )

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
        stream_cancel = asyncio.Event()
        owner_user_id = str(request.agent_user_id or "")
        session_id_key = str(request.session_id or "").strip()
        session_key = (
            (owner_user_id, session_id_key) if owner_user_id and session_id_key else None
        )
        # Stop any prior leave-page worker for this session (also covered by
        # stream_security_run before hub registration; kept for direct tests).
        if session_key is not None:
            self.supersede_session_stream(
                user_id=owner_user_id,
                session_id=session_id_key,
                keep_cancel=stream_cancel,
            )
            self._session_stream_cancels[session_key] = stream_cancel
            self._session_run_ids.setdefault(session_key, set())
        if owner_user_id:
            self._user_stream_cancels[owner_user_id] = stream_cancel
        retry_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        restore_retry = _install_stream_retry_notifier(
            getattr(agent, "model", None),
            retry_queue,
            cancel_event=stream_cancel,
        )
        active_run_id = ""
        agent_queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        def _register_live_run(run_id: str) -> None:
            self.register_run(
                user_id=request.agent_user_id,
                run_id=run_id,
                agent=agent,
                cancel_event=stream_cancel,
                session_id=session_id_key or None,
            )

        def _unregister_live_run(run_id: str) -> None:
            self.unregister_run(
                user_id=request.agent_user_id,
                run_id=run_id,
                session_id=session_id_key or None,
            )

        async def _produce_agent_events() -> None:
            try:
                media_kwargs: dict[str, Any] = {}
                if request.images:
                    media_kwargs["images"] = list(request.images)
                if request.files:
                    media_kwargs["files"] = list(request.files)
                if request.audio:
                    media_kwargs["audio"] = list(request.audio)
                if request.videos:
                    media_kwargs["videos"] = list(request.videos)
                async for event in agent.arun(
                    request.message,
                    session_id=request.session_id,
                    user_id=request.agent_user_id,
                    metadata={RUNTIME_METADATA_KEY: request.runtime_metadata()},
                    stream=True,
                    stream_events=True,
                    **media_kwargs,
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
        # Keep one waiter for the full stream lifetime.  Creating one per
        # received event left a cancelled ``security-run-cancel-wait`` task
        # pending when a client closed the SSE generator immediately.
        cancel_waiter: asyncio.Task[bool] = asyncio.create_task(
            stream_cancel.wait(), name="security-run-cancel-wait"
        )
        cancelled_emitted = False
        # True after leader terminal events so finally does not cancel Agno mid-persist.
        # Early client disconnect after run.completed used to mark runs CANCELLED and
        # break multi-turn Team history (get_messages skips cancelled runs).
        run_finished_naturally = False
        # member_id (or member_id:reasoning) -> throttle state for thought.update
        member_thought_emit: dict[str, tuple[str, float]] = {}
        # member_id -> content stream; member_id:reasoning -> reasoning stream (isolated)
        member_content_acc: dict[str, str] = {}
        # member run_id -> (agent_id, agent_name); last explicit member for stripped deltas
        member_identity_by_run: dict[str, tuple[str, str]] = {}
        last_member_identity: list[tuple[str, str] | None] = [None]
        # Team leader content emitted via content.delta (for empty-completion recovery)
        leader_content_emitted = False
        # Member error summaries when member fails but team continues
        member_error_notes: list[str] = []

        async def _arequest_runner_cancel() -> None:
            if not active_run_id:
                return
            try:
                await _ainvoke_runner_cancel(agent, active_run_id)
            except Exception:  # noqa: BLE001
                pass

        try:
            while True:
                if stream_cancel.is_set():
                    if not producer.done():
                        producer.cancel()
                    await _arequest_runner_cancel()
                    if not cancelled_emitted:
                        cancelled_emitted = True
                        yield ChatRunEvent(
                            "run.cancelled",
                            {
                                "run_id": active_run_id,
                                "reason": "已停止生成",
                            },
                        )
                    break
                wait_set: set[asyncio.Task[Any]] = {
                    t for t in (agent_waiter, retry_waiter) if t is not None
                }
                wait_set.add(cancel_waiter)
                done, _pending = await asyncio.wait(
                    wait_set, return_when=asyncio.FIRST_COMPLETED
                )
                if cancel_waiter in done:
                    # User/stop requested: stop producer and emit one cancelled event.
                    if not producer.done():
                        producer.cancel()
                    await _arequest_runner_cancel()
                    if not cancelled_emitted:
                        cancelled_emitted = True
                        yield ChatRunEvent(
                            "run.cancelled",
                            {
                                "run_id": active_run_id,
                                "reason": "已停止生成",
                            },
                        )
                    break
                if retry_waiter is not None and retry_waiter in done:
                    retry_info = retry_waiter.result()
                    retry_waiter = asyncio.create_task(retry_queue.get(), name="security-run-retry-wait")
                    if isinstance(retry_info, dict) and not stream_cancel.is_set():
                        yield _retry_event(retry_info)
                if agent_waiter is None or agent_waiter not in done:
                    continue
                kind, payload = agent_waiter.result()
                if kind == "done":
                    agent_waiter = None
                    break
                if kind == "error":
                    agent_waiter = None
                    # Cancel during model retry backoff (or agent.arun) → clean cancelled SSE.
                    if isinstance(payload, asyncio.CancelledError) or stream_cancel.is_set():
                        await _arequest_runner_cancel()
                        if not cancelled_emitted:
                            cancelled_emitted = True
                            yield ChatRunEvent(
                                "run.cancelled",
                                {
                                    "run_id": active_run_id,
                                    "reason": "已停止生成",
                                },
                            )
                        break
                    if is_input_check_error(payload):
                        detail = guardrail_failure_payload(payload)
                        yield ChatRunEvent(
                            "run.failed",
                            {
                                "run_id": active_run_id or "",
                                **detail,
                            },
                        )
                        break
                    raise payload
                agent_waiter = asyncio.create_task(agent_queue.get(), name="security-run-agent-wait")
                event = payload
                event_type = str(event_value(event, "event", ""))
                run_id = str(event_value(event, "run_id", "") or "")
                is_member_event = _is_member_agent_event(event)
                member_id = ""
                member_name = ""
                if is_member_event:
                    member_id, member_name = _resolve_member_identity(
                        event,
                        by_run=member_identity_by_run,
                        last=last_member_identity,
                    )
                display_run_id = active_run_id or run_id
                if run_id and not is_member_event:
                    active_run_id = run_id
                    display_run_id = run_id
                    # Bind cancel early so POST /cancel works during model retry
                    # even if the client cancels before we fully process run.started.
                    # Team member runs share parent_run_id; only register leader/top-level.
                    if run_id not in registered_run_ids:
                        registered_run_ids.add(run_id)
                        _register_live_run(run_id)
                if _event_matches(event_type, "run_started"):
                    if run_id and not is_member_event and run_id not in registered_run_ids:
                        registered_run_ids.add(run_id)
                        _register_live_run(run_id)
                    if is_member_event and show_thought_chain:
                        yield ChatRunEvent(
                            "thought.update",
                            {
                                "run_id": display_run_id or run_id,
                                "thought": {
                                    "id": f"member:{member_id}",
                                    "type": "member",
                                    "title": f"成员 · {member_name}",
                                    "status": "running",
                                    "summary": "开始执行",
                                },
                            },
                        )
                        continue
                    lean = is_lean_tool_surface(
                        request.skill_names,
                        enable_tools=bool(request.enable_tools),
                    )
                    # Prefer the agent flag set in _build_security_agent (lean skips KB).
                    # Teams may not mirror Agent.search_knowledge the same way.
                    search_knowledge_active = bool(
                        getattr(agent, "search_knowledge", False)
                    )
                    if is_team_id(request.agent_id):
                        search_knowledge_active = bool(
                            request.search_knowledge and request.enable_tools
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
                            "agent_id": str(request.agent_id or DEFAULT_AGENT_ID),
                            "enable_tools": bool(request.enable_tools),
                            "lean_mode": lean,
                            "search_knowledge": search_knowledge_active,
                            "skill_names": list(request.effective_skill_names),
                            "mcp_server_names": list(request.effective_mcp_server_names),
                        },
                    )
                elif _event_matches(event_type, "run_intermediate_content"):
                    # Leader intermediate drafts -> content.delta; member intermediate
                    # (often identity-stripped) -> ThoughtChain only.
                    content = event_value(event, "content")
                    if not (isinstance(content, str) and content):
                        continue
                    if is_member_event:
                        if show_thought_chain:
                            summary = _append_member_content_delta(
                                member_content_acc,
                                member_id=member_id,
                                delta=content,
                            )
                            if _should_emit_member_thought(
                                member_thought_emit,
                                member_id=member_id,
                                summary=summary,
                            ):
                                yield ChatRunEvent(
                                    "thought.update",
                                    {
                                        "run_id": display_run_id or run_id,
                                        "thought": {
                                            "id": f"member:{member_id}",
                                            "type": "member",
                                            "title": f"成员 · {member_name}",
                                            "status": "running",
                                            "summary": summary,
                                        },
                                    },
                                )
                        continue
                    leader_content_emitted = True
                    yield ChatRunEvent(
                        "content.delta", {"run_id": run_id, "delta": content}
                    )
                elif _event_matches(event_type, "run_content"):
                    content = event_value(event, "content")
                    if not (isinstance(content, str) and content):
                        continue
                    # Team member streams: show as thought chain, not final answer.
                    if is_member_event:
                        if show_thought_chain:
                            summary = _append_member_content_delta(
                                member_content_acc,
                                member_id=member_id,
                                delta=content,
                            )
                            if _should_emit_member_thought(
                                member_thought_emit,
                                member_id=member_id,
                                summary=summary,
                            ):
                                yield ChatRunEvent(
                                    "thought.update",
                                    {
                                        "run_id": display_run_id or run_id,
                                        "thought": {
                                            "id": f"member:{member_id}",
                                            "type": "member",
                                            "title": f"成员 · {member_name}",
                                            "status": "running",
                                            "summary": summary,
                                        },
                                    },
                                )
                        continue
                    leader_content_emitted = True
                    yield ChatRunEvent(
                        "content.delta", {"run_id": run_id, "delta": content}
                    )
                elif _event_matches(event_type, "reasoning_content_delta"):
                    reasoning = event_value(
                        event, "content", event_value(event, "reasoning", "")
                    )
                    if not (isinstance(reasoning, str) and reasoning):
                        continue
                    # Team member raw reasoning stays under ThoughtChain; only the
                    # leader/top-level run feeds the main reasoning panel.
                    if is_member_event:
                        if show_thought_chain:
                            reason_key = f"{member_id or 'member'}:reasoning"
                            summary = _append_member_content_delta(
                                member_content_acc,
                                member_id=reason_key,
                                delta=reasoning,
                            )
                            if _should_emit_member_thought(
                                member_thought_emit,
                                member_id=reason_key,
                                summary=summary,
                            ):
                                yield ChatRunEvent(
                                    "thought.update",
                                    {
                                        "run_id": display_run_id or run_id,
                                        "thought": {
                                            "id": f"member:{reason_key}",
                                            "type": "reasoning",
                                            "title": f"成员推理 · {member_name or member_id or 'member'}",
                                            "status": "running",
                                            "summary": summary,
                                        },
                                    },
                                )
                        continue
                    if show_raw_reasoning:
                        yield ChatRunEvent(
                            "reasoning.delta",
                            {"run_id": run_id, "delta": reasoning},
                        )
                elif (
                    _event_matches(event_type, "reasoning_started")
                    or _event_matches(event_type, "reasoning_step")
                    or _event_matches(event_type, "reasoning_completed")
                ):
                    if show_thought_chain:
                        completed = _event_matches(event_type, "reasoning_completed")
                        summary = event_value(
                            event, "message", event_value(event, "content", "")
                        )
                        summary_text = str(summary or "正在推理")[:280]
                        if is_member_event:
                            thought_id = f"member:{member_id}:reasoning"
                            title = f"成员推理 · {member_name}"
                            # Throttle reasoning_step noise; always emit start/complete.
                            if (
                                _event_matches(event_type, "reasoning_step")
                                and not _should_emit_member_thought(
                                    member_thought_emit,
                                    member_id=f"{member_id}:reasoning",
                                    summary=summary_text,
                                )
                            ):
                                continue
                            if _event_matches(event_type, "reasoning_completed"):
                                _should_emit_member_thought(
                                    member_thought_emit,
                                    member_id=f"{member_id}:reasoning",
                                    summary=summary_text,
                                    force=True,
                                )
                                member_content_acc.pop(f"{member_id}:reasoning", None)
                        else:
                            thought_id = "reasoning"
                            title = "模型推理"
                        yield ChatRunEvent(
                            "thought.update",
                            {
                                "run_id": display_run_id or run_id,
                                "thought": {
                                    "id": thought_id,
                                    "type": "reasoning",
                                    "title": title,
                                    "status": "completed" if completed else "running",
                                    "summary": summary_text,
                                },
                            },
                        )
                elif _event_matches(event_type, "task_state_updated"):
                    if not show_thought_chain:
                        continue
                    task_state = team_tasks_payload(
                        event_value(event, "tasks"),
                        task_summary=event_value(event, "task_summary"),
                        goal_complete=event_value(event, "goal_complete", False),
                        completion_summary=event_value(event, "completion_summary"),
                    )
                    # TeamTaskStateUpdated is a full snapshot. It lets the UI
                    # correct any dropped/interleaved incremental task events.
                    if (
                        task_state["tasks"]
                        or task_state["task_summary"]
                        or task_state["goal_complete"]
                        or task_state["completion_summary"]
                    ):
                        yield ChatRunEvent(
                            "team.tasks",
                            {
                                "run_id": display_run_id or run_id,
                                **task_state,
                            },
                        )
                elif (
                    _event_matches(event_type, "task_created")
                    or _event_matches(event_type, "task_updated")
                    or _event_matches(event_type, "task_iteration_started")
                    or _event_matches(event_type, "task_iteration_completed")
                ):
                    if not show_thought_chain:
                        continue
                    # Agno Team tasks mode (and some coordinate plans) emit task events.
                    task_id = str(
                        event_value(event, "task_id", "")
                        or event_value(event, "id", "")
                        or ""
                    ).strip()
                    title = str(
                        event_value(event, "title", "")
                        or event_value(event, "task_summary", "")
                        or ""
                    ).strip()
                    desc = str(event_value(event, "description", "") or "").strip()
                    status_raw = str(event_value(event, "status", "") or "").strip().lower()
                    if _event_matches(event_type, "task_iteration_started"):
                        iteration = event_value(event, "iteration", 0)
                        max_it = event_value(event, "max_iterations", 0)
                        title = title or f"任务迭代 {iteration}/{max_it}"
                        status = "running"
                        thought_id = f"task-iter:{iteration}"
                    elif _event_matches(event_type, "task_iteration_completed"):
                        iteration = event_value(event, "iteration", 0)
                        max_it = event_value(event, "max_iterations", 0)
                        summary = event_value(event, "task_summary")
                        title = title or f"任务迭代 {iteration}/{max_it} 完成"
                        if isinstance(summary, str) and summary.strip():
                            desc = summary.strip()
                        status = "completed"
                        thought_id = f"task-iter:{iteration}"
                    else:
                        thought_id = f"task:{task_id or title or 'item'}"
                        if status_raw in {"completed", "done", "success"}:
                            status = "completed"
                        elif status_raw in {"failed", "error", "blocked", "cancelled", "canceled"}:
                            status = "error"
                        elif status_raw in {"in_progress", "running", "pending"}:
                            status = "running"
                        else:
                            status = (
                                "running"
                                if _event_matches(event_type, "task_created")
                                else "completed"
                            )
                        if not title:
                            title = "团队任务"
                    yield ChatRunEvent(
                        "thought.update",
                        {
                            "run_id": display_run_id or run_id,
                            "thought": {
                                "id": thought_id,
                                "type": "task",
                                "title": title[:120],
                                "status": status,
                                "summary": (desc or title)[:280],
                            },
                        },
                    )
                elif _event_matches(event_type, "tool_call_started"):
                    if show_thought_chain:
                        yield ChatRunEvent(
                            "tool.update",
                            {
                                "run_id": display_run_id or run_id,
                                "tool": _project_tool_update(event, "running", include_raw_io=show_raw_tool_io),
                            },
                        )
                elif _event_matches(event_type, "tool_call_completed"):
                    if show_thought_chain:
                        yield ChatRunEvent(
                            "tool.update",
                            {
                                "run_id": display_run_id or run_id,
                                "tool": _project_tool_update(event, "completed", include_raw_io=show_raw_tool_io),
                            },
                        )
                elif _event_matches(event_type, "tool_call_error"):
                    if show_thought_chain:
                        yield ChatRunEvent(
                            "tool.update",
                            {
                                "run_id": display_run_id or run_id,
                                "tool": _project_tool_update(event, "error", include_raw_io=show_raw_tool_io),
                            },
                        )
                elif _event_matches(event_type, "run_paused"):
                    paused = paused_payload(event)
                    if not paused.get("session_id"):
                        paused["session_id"] = str(request.session_id or "")
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
                    run_finished_naturally = True
                    yield ChatRunEvent("run.paused", paused)
                    _unregister_live_run(run_id)
                    registered_run_ids.discard(run_id)
                elif _event_matches(event_type, "run_continued"):
                    yield ChatRunEvent(
                        "run.continued",
                        {
                            "run_id": run_id,
                            "session_id": str(
                                event_value(event, "session_id", request.session_id or "")
                                or request.session_id
                                or ""
                            ),
                        },
                    )
                elif _event_matches(event_type, "run_completed"):
                    if is_member_event:
                        if show_thought_chain:
                            reason_key = f"{member_id}:reasoning"
                            reason_summary = member_content_acc.pop(reason_key, None)
                            if reason_summary:
                                _should_emit_member_thought(
                                    member_thought_emit,
                                    member_id=reason_key,
                                    summary=str(reason_summary)[:280],
                                    force=True,
                                )
                                yield ChatRunEvent(
                                    "thought.update",
                                    {
                                        "run_id": display_run_id or run_id,
                                        "thought": {
                                            "id": f"member:{reason_key}",
                                            "type": "reasoning",
                                            "title": f"成员推理 · {member_name}",
                                            "status": "completed",
                                            "summary": str(reason_summary)[:280],
                                        },
                                    },
                                )
                            summary = event_value(event, "content")
                            if not isinstance(summary, str) or not str(summary).strip():
                                summary = member_content_acc.get(member_id) or "完成"
                            summary_text = str(summary)[:280]
                            member_content_acc.pop(member_id, None)
                            _should_emit_member_thought(
                                member_thought_emit,
                                member_id=member_id,
                                summary=summary_text,
                                force=True,
                            )
                            yield ChatRunEvent(
                                "thought.update",
                                {
                                    "run_id": display_run_id or run_id,
                                    "thought": {
                                        "id": f"member:{member_id}",
                                        "type": "member",
                                        "title": f"成员 · {member_name}",
                                        "status": "completed",
                                        "summary": summary_text,
                                    },
                                },
                            )
                        # Deep-research members often attach citations; keep them
                        # visible on the chat message with a member prefix.
                        member_sources = source_items(
                            event_value(event, "citations")
                        ) or source_items(event_value(event, "references"))
                        if member_sources:
                            for item in member_sources:
                                title = str(item.get("title") or "").strip()
                                prefix = f"[{member_name or member_id}] "
                                if title and not title.startswith(prefix):
                                    item["title"] = f"{prefix}{title}"
                            yield ChatRunEvent(
                                "sources",
                                {
                                    "run_id": display_run_id or run_id,
                                    "items": member_sources,
                                },
                            )
                        continue
                    sources = source_items(
                        event_value(event, "citations")
                    ) or source_items(event_value(event, "references"))
                    if sources:
                        yield ChatRunEvent(
                            "sources", {"run_id": run_id, "items": sources}
                        )
                    # Close any member thoughts still open (member RunCompleted lost /
                    # identity-stripped path / early client disconnect mid-member).
                    if show_thought_chain and member_content_acc:
                        for open_id, open_summary in list(member_content_acc.items()):
                            is_reason = open_id.endswith(":reasoning")
                            base_id = open_id[: -len(":reasoning")] if is_reason else open_id
                            open_name = base_id
                            for _rid, (mid, mname) in member_identity_by_run.items():
                                if mid == base_id:
                                    open_name = mname
                                    break
                            if (
                                last_member_identity[0]
                                and last_member_identity[0][0] == base_id
                            ):
                                open_name = last_member_identity[0][1]
                            summary_text = (open_summary or "完成")[:280]
                            yield ChatRunEvent(
                                "thought.update",
                                {
                                    "run_id": display_run_id or run_id,
                                    "thought": {
                                        "id": f"member:{open_id}",
                                        "type": "reasoning" if is_reason else "member",
                                        "title": (
                                            f"成员推理 · {open_name}"
                                            if is_reason
                                            else f"成员 · {open_name}"
                                        ),
                                        "status": "completed",
                                        "summary": summary_text,
                                    },
                                },
                            )
                        member_content_acc.clear()
                    completed = completed_payload(event)
                    if not completed.get("session_id"):
                        completed["session_id"] = str(request.session_id or "")
                    # Team: recover empty final answer when members failed or only
                    # intermediate tools ran (e.g. provider 403 on member).
                    if is_team_id(request.agent_id) and not (
                        isinstance(completed.get("content"), str)
                        and str(completed.get("content") or "").strip()
                    ):
                        recovery = ""
                        if member_error_notes:
                            recovery = (
                                "团队未能生成最终回答。成员错误：\n- "
                                + "\n- ".join(member_error_notes[-3:])
                            )
                        elif not leader_content_emitted:
                            recovery = (
                                "团队运行已结束，但未产生可展示的回答。"
                                "请重试或切换模型/检查成员工具依赖。"
                            )
                        if recovery:
                            completed["content"] = recovery[:2000]
                            if not leader_content_emitted:
                                yield ChatRunEvent(
                                    "content.delta",
                                    {
                                        "run_id": display_run_id or run_id,
                                        "delta": recovery[:2000],
                                    },
                                )
                                leader_content_emitted = True
                    # Set before yield: consumer may close the stream at this event.
                    run_finished_naturally = True
                    yield ChatRunEvent("run.completed", completed)
                    # Optional second-pass: remember durable facts from tool results.
                    if (
                        request.memory_enabled
                        and request.memory_user_id is not None
                        and bool(
                            getattr(chat_settings, "memory_tool_content_enabled", False)
                        )
                    ):
                        asyncio.create_task(
                            _maybe_capture_tool_content_memories(
                                agent=agent,
                                request=request,
                                event=event,
                            ),
                            name="memory-tool-content-capture",
                        )
                    _unregister_live_run(run_id)
                    registered_run_ids.discard(run_id)
                elif _event_matches(event_type, "run_cancelled"):
                    if is_member_event:
                        if show_thought_chain:
                            member_content_acc.pop(member_id, None)
                            member_content_acc.pop(f"{member_id}:reasoning", None)
                            yield ChatRunEvent(
                                "thought.update",
                                {
                                    "run_id": display_run_id or run_id,
                                    "thought": {
                                        "id": f"member:{member_id}:reasoning",
                                        "type": "reasoning",
                                        "title": f"成员推理 · {member_name}",
                                        "status": "error",
                                        "summary": "成员运行已取消",
                                    },
                                },
                            )
                            yield ChatRunEvent(
                                "thought.update",
                                {
                                    "run_id": display_run_id or run_id,
                                    "thought": {
                                        "id": f"member:{member_id}",
                                        "type": "member",
                                        "title": f"成员 · {member_name}",
                                        "status": "error",
                                        "summary": "成员运行已取消",
                                    },
                                },
                            )
                        continue
                    run_finished_naturally = True
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
                    _unregister_live_run(run_id)
                    registered_run_ids.discard(run_id)
                elif _event_matches(event_type, "run_error"):
                    detail = (
                        event_value(event, "content")
                        or event_value(event, "error")
                        or event_value(event, "message")
                        or "安全分析运行失败"
                    )
                    detail_text = str(detail).strip() or "安全分析运行失败"
                    # Team member failure: surface under ThoughtChain; do not fail the whole run.
                    if is_member_event:
                        note = f"{member_name or member_id}: {detail_text[:200]}"
                        member_error_notes.append(note)
                        if show_thought_chain:
                            member_content_acc.pop(member_id, None)
                            member_content_acc.pop(f"{member_id}:reasoning", None)
                            yield ChatRunEvent(
                                "thought.update",
                                {
                                    "run_id": display_run_id or run_id,
                                    "thought": {
                                        "id": f"member:{member_id}:reasoning",
                                        "type": "reasoning",
                                        "status": "error",
                                        "title": f"成员推理 · {member_name}",
                                        "summary": detail_text[:280],
                                    },
                                },
                            )
                            yield ChatRunEvent(
                                "thought.update",
                                {
                                    "run_id": display_run_id or run_id,
                                    "thought": {
                                        "id": f"member:{member_id}",
                                        "type": "member",
                                        "title": f"成员 · {member_name}",
                                        "status": "error",
                                        "summary": detail_text[:280],
                                    },
                                },
                            )
                        continue
                    run_finished_naturally = True
                    yield ChatRunEvent(
                        "run.failed",
                        {
                            "run_id": run_id,
                            "code": "AGENT_RUN_ERROR",
                            "message": detail_text,
                            "retryable": True,
                        },
                    )
                    _unregister_live_run(run_id)
                    registered_run_ids.discard(run_id)
        finally:
            # User cancel was requested via stream_cancel Event (Stop / cancel API).
            # Client disconnect is handled above stream_security_run (detached worker):
            # this generator normally runs inside that worker and is not cancelled on
            # leave-page. If the generator is still closed mid-run (tests / aclose),
            # drain Agno without treating CancelledError as Stop.
            user_stop = stream_cancel.is_set()
            if owner_user_id:
                current = self._user_stream_cancels.get(owner_user_id)
                if current is stream_cancel:
                    self._user_stream_cancels.pop(owner_user_id, None)
            if session_key is not None:
                current_session = self._session_stream_cancels.get(session_key)
                if current_session is stream_cancel:
                    self._session_stream_cancels.pop(session_key, None)
            restore_retry()
            request_cancelled = False
            detached_producer = False
            drain_timeout = 60 if run_finished_naturally else 600
            registered_snapshot = set(registered_run_ids)
            agent_user_id = request.agent_user_id
            session_for_cleanup = session_id_key or None

            async def _finish_producer(*, force_cancel: bool) -> None:
                if producer.done():
                    return
                if force_cancel:
                    producer.cancel()
                    try:
                        await producer
                    except asyncio.CancelledError:
                        pass
                    await _arequest_runner_cancel()
                    return
                try:
                    await asyncio.wait_for(producer, timeout=drain_timeout)
                except asyncio.TimeoutError:
                    producer.cancel()
                    try:
                        await producer
                    except asyncio.CancelledError:
                        pass
                    await _arequest_runner_cancel()

            if not producer.done():
                if user_stop:
                    await _finish_producer(force_cancel=True)
                else:
                    # Natural completion: short drain. Generator close: longer drain.
                    # Prefer finishing under the current task; if the parent is
                    # cancelled, detach so Agno is not cancelled via await chain.
                    drain_task = asyncio.create_task(
                        _finish_producer(force_cancel=False),
                        name="security-run-producer-drain",
                    )

                    async def _detach_after_drain() -> None:
                        try:
                            await drain_task
                        except Exception:  # noqa: BLE001 — best-effort background drain
                            logger.exception("detached chat producer drain failed")
                        finally:
                            for run_id in registered_snapshot:
                                self.unregister_run(
                                    user_id=agent_user_id,
                                    run_id=run_id,
                                    session_id=session_for_cleanup,
                                )

                    try:
                        await asyncio.shield(drain_task)
                    except asyncio.CancelledError:
                        request_cancelled = True
                        if not drain_task.done():
                            detached_producer = True
                            asyncio.create_task(
                                _detach_after_drain(),
                                name="security-run-detach-drain",
                            )
            waiters = tuple(
                waiter
                for waiter in (agent_waiter, retry_waiter, cancel_waiter)
                if waiter is not None
            )
            for waiter in waiters:
                if not waiter.done():
                    waiter.cancel()
            if waiters:
                try:
                    await asyncio.gather(*waiters, return_exceptions=True)
                except asyncio.CancelledError:
                    request_cancelled = True
            while True:
                try:
                    retry_info = retry_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if isinstance(retry_info, dict):
                    yield _retry_event(retry_info)
            if not detached_producer:
                for run_id in registered_run_ids:
                    _unregister_live_run(run_id)
            if request_cancelled:
                raise asyncio.CancelledError()

    async def build_fallback_agent(
        self,
        model_id: str | None = None,
        reasoning_effort: str | None = None,
        memory_enabled: bool = True,
        live_search: bool | None = None,
        user_id: str | None = None,
    ) -> Agent:
        model = await self._build_model(model_id, reasoning_effort, live_search=live_search)
        chat_settings = await get_chat_settings_async()
        use_summaries = bool(chat_settings.session_summaries_enabled)
        # Fail-closed: never write/read long-term memory under anonymous/default.
        memory_owner = (user_id or "").strip()
        memory_mode = str(getattr(chat_settings, "memory_mode", "") or "").strip().lower()
        if memory_mode not in {"off", "automatic", "agentic"}:
            memory_mode = (
                "agentic"
                if chat_settings.enable_agentic_memory
                else ("automatic" if memory_enabled else "off")
            )
        memory_ok = (
            memory_mode != "off"
            and bool(memory_enabled)
            and bool(memory_owner)
            and memory_owner not in {"anonymous", "default"}
        )
        agentic = memory_ok and memory_mode == "agentic"
        memory_manager = (
            await build_memory_manager(
                tool_content_enabled=bool(chat_settings.memory_tool_content_enabled),
                db=self.dependencies.get_db(),
                inject_config=chat_settings,
                inject_query="",
                agent_id=DEFAULT_AGENT_ID,
            )
            if memory_ok
            else None
        )
        fallback_instructions = [await _load_prompt_async(SAFE_FALLBACK_PROMPT)]
        if agentic:
            fallback_instructions.extend(
                soc_memory_agent_instructions(DEFAULT_AGENT_ID)
            )
        return self.dependencies.agent_factory(
            **apply_guardrails_kwargs(
                {
                    "id": "security-operations",
                    "name": "安全防御助手",
                    "role": "安全防御运营助手",
                    "description": "无工具模式下的安全防御运营助手。",
                    "instructions": fallback_instructions,
                    "model": model,
                    "db": self.dependencies.get_db(),
                    "memory_manager": memory_manager,
                    "update_memory_on_run": memory_ok and not agentic,
                    "add_memories_to_context": memory_ok,
                    "enable_agentic_memory": agentic,
                    "store_tool_messages": False,
                    "enable_session_summaries": use_summaries,
                    "session_summary_manager": (
                        _session_summary_manager(model) if use_summaries else None
                    ),
                    "add_session_summary_to_context": use_summaries,
                    "num_history_runs": int(chat_settings.num_history_runs),
                    "max_tool_calls_from_history": chat_settings.max_tool_calls_from_history,
                    "add_datetime_to_context": bool(
                        chat_settings.add_datetime_to_context
                    ),
                    "markdown": bool(chat_settings.markdown),
                }
            )
        )

    async def _build_security_agent(
        self,
        mcp_tools: Any | None,
        request: SecurityRunRequest,
    ) -> Agent:
        profile = get_agent_profile(request.agent_id)
        agent_id = str(profile["id"])
        enable_tools = bool(request.enable_tools)
        attaches_skills = bool(profile.get("attach_skills")) and enable_tools
        tools: list[Any] = []
        if enable_tools:
            if request.workspace_files and profile_uses_analysis_sandbox(profile):
                stage_media_into_analysis_dir(request.workspace_files)
            tools.extend(build_tools_for_profile(profile))
            if mcp_tools is not None:
                tools.append(mcp_tools)
        skills = (
            await self._build_enabled_skills(request)
            if attaches_skills
            else None
        )
        # Lean surface when tools off or intent filter attached nothing.
        # Cost path: skip MCP/Skills/knowledge/live-search, use lite prompt,
        # no datetime injection, shorter/no history on new sessions, and do
        # not inject long-term memories into the model context (still may
        # write memories after the run when memory_enabled).
        tool_surface = bool(tools) or skills is not None
        # Knowledge / live search are part of the full tool surface for security;
        # specialist agents keep explicit UI toggles even without MCP.
        specialist = agent_id != DEFAULT_AGENT_ID
        surface_active = tool_surface or (specialist and enable_tools)
        # Knowledge / live search follow explicit UI toggles whenever tools are on.
        # Auto-lean (empty skill_names) still skips MCP/Skills, but does not block
        # manual knowledge retrieval or live search.
        search_knowledge = bool(request.search_knowledge) and enable_tools
        if not enable_tools:
            live_search = False
        elif request.live_search is not None:
            live_search = bool(request.live_search)
        else:
            # Profile prefer_* only auto-enables on full tool surface.
            live_search = bool(profile.get("prefer_live_search")) and surface_active
        model = await self._build_model(
            request.model_id,
            request.reasoning_effort,
            live_search=live_search,
        )
        knowledge = None
        if search_knowledge:
            knowledge = await _maybe_await(self.dependencies.get_async_knowledge_base())
        if agent_id == DEFAULT_AGENT_ID:
            prompt_name = (
                str(profile.get("prompt_full") or SECURITY_OPERATIONS_PROMPT)
                if surface_active
                else str(profile.get("prompt_lite") or SECURITY_OPERATIONS_LITE_PROMPT)
            )
        else:
            prompt_name = str(profile.get("prompt_full") or profile.get("prompt_lite") or "")
        has_session = bool(str(request.session_id or "").strip())
        chat_settings = await get_chat_settings_async()
        settings_history = int(chat_settings.num_history_runs)
        profile_history = int(profile.get("history_runs") or settings_history or 5)
        # Prefer Settings override when set; otherwise profile default.
        # Lean path still trims history for cost.
        if surface_active:
            history_runs = settings_history if settings_history > 0 else profile_history
            add_history = history_runs > 0
            add_datetime = bool(chat_settings.add_datetime_to_context)
        else:
            history_runs = min(2, settings_history) if has_session else 0
            add_history = has_session and history_runs > 0
            add_datetime = False
        session_summaries = surface_active and bool(
            chat_settings.session_summaries_enabled
        )
        # Fail-closed: real user_id required before any long-term memory I/O.
        # memory_mode is the single source of truth (off / automatic / agentic).
        memory_owner = request.memory_user_id
        memory_mode = str(getattr(chat_settings, "memory_mode", "") or "").strip().lower()
        if memory_mode not in {"off", "automatic", "agentic"}:
            memory_mode = (
                "agentic"
                if chat_settings.enable_agentic_memory
                else ("automatic" if request.memory_enabled else "off")
            )
        memory_ok = (
            memory_mode != "off"
            and bool(request.memory_enabled)
            and memory_owner is not None
        )
        if bool(request.memory_enabled) and memory_owner is None:
            logger.warning(
                "memory fail-closed: missing user_id agent_id={}",
                agent_id,
            )
        inject_memories = memory_ok and surface_active
        agentic = memory_ok and memory_mode == "agentic"
        memory_manager = (
            await build_memory_manager(
                tool_content_enabled=bool(chat_settings.memory_tool_content_enabled),
                db=self.dependencies.get_db(),
                inject_config=chat_settings,
                inject_query=str(request.message or ""),
                agent_id=agent_id,
            )
            if memory_ok
            else None
        )
        tool_limit = resolve_tool_call_limit(
            profile.get("tool_call_limit"), chat_settings
        )
        description = str(profile.get("description") or profile.get("name") or agent_id)
        if agent_id == DEFAULT_AGENT_ID and not surface_active:
            description = "安全运营助手（轻量）：无 MCP/Skills，适合闲聊与概念解答。"
        agent_instructions: list[str] = (
            [await _load_prompt_async(prompt_name)] if prompt_name else []
        )
        if agentic:
            agent_instructions.extend(soc_memory_agent_instructions(agent_id))
        return self.dependencies.agent_factory(
            **apply_guardrails_kwargs(
                {
                    "id": agent_id,
                    "name": str(profile.get("name") or agent_id),
                    "role": str(profile.get("role") or ""),
                    "description": description,
                    "instructions": agent_instructions,
                    "model": model,
                    "tools": tools,
                    "knowledge": knowledge,
                    "knowledge_retriever": (
                        build_knowledge_retriever(knowledge)
                        if knowledge is not None
                        else None
                    ),
                    "knowledge_filters": (
                        {"user_id": request.knowledge_owner_user_id}
                        if request.knowledge_owner_user_id and search_knowledge
                        else None
                    ),
                    "search_knowledge": search_knowledge,
                    "add_search_knowledge_instructions": search_knowledge,
                    "skills": skills,
                    "db": self.dependencies.get_db(),
                    "dependencies": await _run_sync_dependency(_agent_dependencies),
                    "add_dependencies_to_context": False,
                    "add_history_to_context": add_history,
                    "memory_manager": memory_manager,
                    # Agno: agentic memory takes precedence over update_memory_on_run.
                    "update_memory_on_run": memory_ok and not agentic,
                    "add_memories_to_context": inject_memories,
                    "enable_agentic_memory": agentic and surface_active,
                    "store_tool_messages": (
                        request.store_raw_tool_io if surface_active else False
                    ),
                    "enable_session_summaries": session_summaries,
                    "session_summary_manager": (
                        _session_summary_manager(model) if session_summaries else None
                    ),
                    "add_session_summary_to_context": session_summaries,
                    "num_history_runs": history_runs,
                    "max_tool_calls_from_history": (
                        chat_settings.max_tool_calls_from_history
                        if surface_active
                        else None
                    ),
                    "add_datetime_to_context": add_datetime,
                    "tool_call_limit": tool_limit,
                    "markdown": bool(chat_settings.markdown),
                }
            )
        )

    @asynccontextmanager
    async def security_agent_context(self, request: SecurityRunRequest) -> AsyncIterator[Agent]:
        # Keep the run workspace alive for both tool construction and the
        # streamed Agent execution.  A nested caller (``stream``/resume) reuses
        # its workspace, while direct callers still get correct cleanup.
        with analysis_workspace_context() as _workspace:
            request = await self._resolve_effective_capabilities(request)
            if not should_connect_mcp(
                request.skill_names,
                enable_tools=bool(request.enable_tools),
                agent_id=request.agent_id,
            ):
                # Tools off, or trivial/non-ops turn with empty skill list: no MCP session.
                security_agent = await _maybe_await(
                    self._build_security_agent(None, request)
                )
                yield security_agent
                return

            delegation_issuer = getattr(
                self.dependencies,
                "issue_mcp_delegation_token",
                issue_delegation_token,
            )
            legacy_mcp_token = getattr(
                self.dependencies,
                "get_mcp_token",
                _build_mcp_token,
            )
            if (
                delegation_issuer is issue_delegation_token
                and legacy_mcp_token is not _build_mcp_token
            ):
                token = await _run_sync_dependency(legacy_mcp_token)
            else:
                token = await _run_sync_dependency(
                    delegation_issuer,
                    request.agent_user_id,
                )
            server_params = StreamableHTTPClientParams(
                url=await _run_sync_dependency(self.dependencies.get_mcp_url),
            )
            async with self.dependencies.mcp_tools_factory(
                server_params=server_params,
                transport="streamable-http",
                timeout_seconds=20,
                header_provider=_mcp_header_provider(token),
            ) as mcp_tools:
                allowed = mcp_prefixes_for_skills(request.skill_names)
                removed = filter_mcp_tools_by_prefixes(mcp_tools, allowed)
                if removed:
                    logger.debug(
                        "MCP tools filtered for skill intent skill_names={} removed={}",
                        request.skill_names,
                        removed,
                    )
                marked = mark_hitl_mcp_tools(mcp_tools)
                if marked:
                    logger.debug("Agno required approval applied to MCP tools: {}", marked)
                security_agent = await _maybe_await(
                    self._build_security_agent(mcp_tools, request)
                )
                yield security_agent

    @asynccontextmanager
    async def team_context(self, request: SecurityRunRequest) -> AsyncIterator[Any]:
        """Build one executable Team for a strict Eval or direct runtime caller.

        Chat streaming used to own the only Team construction path.  Evals need
        the actual ``TeamRunOutput`` (not a streamed Chat adapter) so that
        Accuracy and Reliability can grade the same Team run exactly once.
        """
        if not is_team_id(request.agent_id):
            raise ValueError(f"Eval target is not a Team: {request.agent_id}")
        if not team_feature_enabled():
            raise ValueError(
                "Eval Team target is disabled; set TAIS_ENABLE_AGNO_TEAM=1 before running it"
            )

        # Team members may execute concurrently, so bind before constructing
        # their File/Csv/Python toolkits and retain the scope until execution
        # has fully ended.
        with analysis_workspace_context() as _workspace:
            request = await self._resolve_effective_capabilities(request)
            enable_tools = bool(request.enable_tools)
            search_knowledge = bool(request.search_knowledge) and enable_tools
            # Align with specialist agents: explicit request wins; else team profile prefer_*.
            team_profile = get_team_profile(request.agent_id) or {}
            if not enable_tools:
                live_search = False
            elif request.live_search is not None:
                live_search = request.live_search
            else:
                live_search = bool(team_profile.get("prefer_live_search"))
            knowledge = None
            knowledge_filters = None
            if search_knowledge:
                knowledge = await _maybe_await(self.dependencies.get_async_knowledge_base())
                if request.knowledge_owner_user_id:
                    knowledge_filters = {"user_id": request.knowledge_owner_user_id}
            memory_ok = bool(request.memory_enabled) and request.memory_user_id is not None
            if bool(request.memory_enabled) and request.memory_user_id is None:
                logger.warning(
                    "memory fail-closed: missing user_id team_id={}",
                    request.agent_id,
                )
            team = await build_team(
                str(request.agent_id),
                model_id=request.model_id,
                reasoning_effort=request.reasoning_effort,
                live_search=live_search,
                search_knowledge=search_knowledge,
                knowledge=knowledge,
                knowledge_filters=knowledge_filters,
                memory_enabled=memory_ok,
                enable_tools=enable_tools,
                store_raw_tool_io=bool(request.store_raw_tool_io),
                media_files=request.workspace_files,
                inject_query=str(request.message or ""),
            )
            yield team

    async def _stream_team(
        self,
        request: SecurityRunRequest,
        chat_settings: Any | None = None,
    ) -> AsyncIterator[ChatRunEvent]:
        """Build and stream an Agno Team run (beta)."""
        async with self.team_context(request) as team:
            async for event in self._stream_agent_events(team, request, chat_settings):
                yield event

    async def stream(self, request: SecurityRunRequest) -> AsyncIterator[ChatRunEvent]:
        chat_settings = await get_chat_settings_async()
        # Fail closed before capability/DB resolution when Team beta is off.
        if is_team_id(request.agent_id) and not team_feature_enabled():
            yield ChatRunEvent(
                "run.failed",
                {
                    "run_id": "",
                    "code": "TEAM_DISABLED",
                    "message": "Agno Team 未启用（设置环境变量 TAIS_ENABLE_AGNO_TEAM=1）",
                    "retryable": False,
                },
            )
            return
        # One directory per Chat invocation, including Team and provider fallback
        # paths.  Nested helpers share it and its ``finally`` cleanup runs when
        # this async generator is closed on completion/disconnect.
        with analysis_workspace_context() as _workspace:
            try:
                request = await self._resolve_effective_capabilities(request)
                if is_team_id(request.agent_id):
                    try:
                        async for event in self._stream_team(request, chat_settings):
                            yield event
                    except ValueError as exc:
                        yield ChatRunEvent(
                            "run.failed",
                            {
                                "run_id": "",
                                "code": "TEAM_BUILD_ERROR",
                                "message": str(exc) or "无法构建 Team",
                                "retryable": False,
                            },
                        )
                    return
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
    """SSE-facing chat stream.

    Agno work (MCP, tools, model) runs on a **detached** asyncio Task backed by
    a session live hub. Leaving Chat cancels only this SSE subscriber; the
    worker keeps publishing so a later ``attach_live_security_run`` can catch
    up and continue streaming. Explicit Stop still uses ``cancel_run``.
    """
    active_runtime = runtime or DEFAULT_SECURITY_RUN_RUNTIME
    owner = str(request.agent_user_id or "").strip()
    session = str(request.session_id or "").strip()
    session_key = (owner, session) if owner and session else None
    # Cancel any prior leave-page worker *before* publishing a new hub, so
    # supersede inside _stream_agent_events does not wipe this stream's hub.
    if session_key is not None:
        active_runtime.supersede_session_stream(
            user_id=owner, session_id=session, keep_cancel=None
        )
    hub = _LiveChatStreamHub()
    if session_key is not None:
        active_runtime._session_live_hubs[session_key] = hub

    async def _run_to_completion() -> None:
        try:
            async for event in active_runtime.stream(request):
                await hub.publish(event)
            await hub.finish()
        except BaseException as exc:
            try:
                await hub.finish(exc if isinstance(exc, Exception) else None)
            except Exception:  # noqa: BLE001
                logger.exception("chat live hub failed to finish after error")
            if isinstance(exc, asyncio.CancelledError):
                return
            if not isinstance(exc, Exception):
                raise
            # Exception already stored on hub for subscribers.
        finally:
            if session_key is not None:
                current = active_runtime._session_live_hubs.get(session_key)
                if current is hub:
                    active_runtime._session_live_hubs.pop(session_key, None)

    worker = asyncio.create_task(
        _run_to_completion(),
        name="security-run-detached-worker",
    )
    try:
        async for event in hub.subscribe():
            yield event
        if not worker.done():
            await worker
    except (asyncio.CancelledError, GeneratorExit):
        # Leave page / SSE aclose: do not cancel the worker. Agno keeps running
        # with MCP + analysis workspace until COMPLETED is stored.
        raise
    except Exception:
        # Subscriber-side failure: stop the worker so we do not leak a long
        # Agno task for a broken pipe that is not a deliberate leave-page detach.
        if not worker.done():
            worker.cancel()
            try:
                await worker
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        raise


async def attach_live_security_run(
    *,
    user_id: str,
    session_id: str,
    last_event_index: int | None = None,
    runtime: SecurityRunRuntime | None = None,
) -> AsyncIterator[ChatRunEvent]:
    """Re-attach to a leave-page detached chat worker (catch-up + live).

    ``last_event_index`` matches AgentOS ``/resume``: only events strictly after
    that monotonic index are replayed, then live deltas follow.
    """
    active_runtime = runtime or DEFAULT_SECURITY_RUN_RUNTIME
    hub = active_runtime.get_live_hub(user_id=user_id, session_id=session_id)
    if hub is None:
        return
    async for event in hub.subscribe(last_event_index=last_event_index):
        yield event


def _tool_result_summaries_from_event(event: Any, *, limit: int = 8) -> list[str]:
    """Extract truncated tool result strings from a run.completed-style event."""
    tools = event_value(event, "tools", [])
    if not isinstance(tools, list):
        return []
    summaries: list[str] = []
    for raw in tools:
        if len(summaries) >= limit:
            break
        if isinstance(raw, dict):
            name = str(raw.get("tool_name") or raw.get("name") or "tool").strip()
            result = raw.get("result", raw.get("output", raw.get("content")))
        else:
            name = str(
                getattr(raw, "tool_name", None) or getattr(raw, "name", None) or "tool"
            ).strip()
            result = getattr(raw, "result", None)
            if result is None:
                result = getattr(raw, "output", None)
        if result is None:
            continue
        text = result if isinstance(result, str) else str(result)
        text = text.strip()
        if not text:
            continue
        if len(text) > 1_500:
            text = text[:1_500] + "…"
        summaries.append(f"[{name}] {text}")
    return summaries


async def _maybe_capture_tool_content_memories(
    *,
    agent: Any,
    request: SecurityRunRequest,
    event: Any,
) -> None:
    """Background: optional MemoryManager pass over tool results (Settings flag)."""
    owner = request.memory_user_id
    if owner is None:
        return
    summaries = _tool_result_summaries_from_event(event)
    if not summaries:
        return
    try:
        manager = getattr(agent, "memory_manager", None)
        if manager is None:
            manager = await build_memory_manager(
                tool_content_enabled=True,
                db=getattr(agent, "db", None),
            )
        await capture_tool_content_memories(
            memory_manager=manager,
            user_id=owner,
            agent_id=str(getattr(agent, "id", None) or request.agent_id or ""),
            tool_summaries=summaries,
        )
    except Exception:
        logger.exception(
            "tool-content memory capture failed user_id={} agent_id={}",
            owner,
            request.agent_id,
        )


def cancel_security_run(*, user_id: str, run_id: str) -> bool:
    return DEFAULT_SECURITY_RUN_RUNTIME.cancel_run(user_id=user_id, run_id=run_id)


async def acancel_security_run(*, user_id: str, run_id: str) -> bool:
    return await DEFAULT_SECURITY_RUN_RUNTIME.acancel_run(user_id=user_id, run_id=run_id)


def has_live_security_run(
    *,
    user_id: str,
    session_id: str,
    runtime: SecurityRunRuntime | None = None,
) -> bool:
    active_runtime = runtime or DEFAULT_SECURITY_RUN_RUNTIME
    hub = active_runtime.get_live_hub(user_id=user_id, session_id=session_id)
    return hub is not None and not hub.done



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


async def execute_security_hitl_resume(approval_id: str) -> str:
    """Execute a queued security HITL continuation in the durable worker.

    This is intentionally separate from :func:`resume_security_run`, which is
    an API-side producer and only enqueues work.
    """
    return await DEFAULT_SECURITY_RUN_RUNTIME._resume_job(approval_id)


async def recover_security_runs() -> int:
    return await DEFAULT_SECURITY_RUN_RUNTIME.recover_resolved_runs()


async def shutdown_security_runtime() -> None:
    await DEFAULT_SECURITY_RUN_RUNTIME.shutdown()
