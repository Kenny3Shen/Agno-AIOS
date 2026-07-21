"""Agno Team (beta) for multi-agent coordination in Chat.

Feature flag: ``TAIS_ENABLE_AGNO_TEAM=1`` (default off for product safety).

Chat uses team ids as ``agent_id`` values (e.g. ``research-analysis-team``).
HITL/MCP are intentionally not mounted on team members in this beta.
"""

from __future__ import annotations

import os
from copy import deepcopy
from pathlib import Path
from typing import Any, cast

from agno.agent import Agent
from agno.session import SessionSummaryManager
from agno.team import Team
from agno.team.mode import TeamMode
from anyio import Path as AsyncPath
from loguru import logger

from api.services.agent_catalog import get_agent_profile
from api.services.agent_tools import (
    build_tools_for_profile,
    profile_uses_analysis_sandbox,
    stage_media_into_analysis_dir,
)
from api.services.guardrails import apply_guardrails_kwargs
from api.services.chat_settings_service import get_chat_settings_async
from api.services.model_config_service import get_model_for_run
from api.services.model_factory import build_agno_model
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.knowledge_service import build_knowledge_retriever

PROMPT_DIR = Path(__file__).resolve().parents[1] / "agent" / "prompts"

# Chat-selectable team catalog (stable ids).
TEAM_PROFILES: dict[str, dict[str, Any]] = {
    "research-analysis-team": {
        "id": "research-analysis-team",
        "name": "研究分析团队",
        "role": "协调深度研究与数据分析",
        "description": (
            "Agno Team（beta）：协调「深度研究」与「数据分析」成员，"
            "产出带来源与可核验数字的综合报告。"
        ),
        "category": "team",
        "kind": "team",
        "capabilities": "team,coordinate,research,analysis",
        "recommended_for": "需要多角色协作的调研与量化分析",
        "mode": TeamMode.coordinate,
        "members": ("deep-research", "data-analysis"),
        "chat_selectable": True,
        "prefer_live_search": True,
    },
    "research-analysis-route": {
        "id": "research-analysis-route",
        "name": "研究分析路由",
        "role": "路由到单一专员",
        "description": (
            "Agno Team（beta，route）：负责人将任务路由到深度研究或数据分析之一，"
            "直接返回专员结果。"
        ),
        "category": "team",
        "kind": "team",
        "capabilities": "team,route,research,analysis",
        "recommended_for": "明确只需调研或只需计算的任务",
        "mode": TeamMode.route,
        "members": ("deep-research", "data-analysis"),
        "chat_selectable": True,
        "prefer_live_search": True,
    },
    "research-analysis-broadcast": {
        "id": "research-analysis-broadcast",
        "name": "研究分析会诊",
        "role": "并行征询全部专员",
        "description": (
            "Agno Team（beta，broadcast）：同一问题并行交给深度研究与数据分析，"
            "负责人汇总一致与分歧后给出结论（高 stakes / 需多视角）。"
        ),
        "category": "team",
        "kind": "team",
        "capabilities": "team,broadcast,research,analysis",
        "recommended_for": "需要独立多视角对照的高风险判断",
        "mode": TeamMode.broadcast,
        "members": ("deep-research", "data-analysis"),
        "chat_selectable": True,
        "prefer_live_search": True,
    },
    "research-analysis-tasks": {
        "id": "research-analysis-tasks",
        "name": "研究分析任务组",
        "role": "拆分、并行执行并核验研究任务",
        "description": (
            "Agno Team（beta，tasks）：将复杂问题拆成可见任务，"
            "并行委派调研与数据分析，再依据依赖关系汇总结论。"
        ),
        "category": "team",
        "kind": "team",
        "capabilities": "team,tasks,parallel,research,analysis",
        "recommended_for": "需要清晰分工、实时进度与可复核交付物的复杂研究任务",
        "mode": TeamMode.tasks,
        "members": ("deep-research", "data-analysis"),
        "chat_selectable": True,
        "prefer_live_search": True,
    },
}

def team_feature_enabled() -> bool:
    raw = (os.getenv("TAIS_ENABLE_AGNO_TEAM") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def is_team_id(raw: object | None) -> bool:
    value = str(raw or "").strip()
    return value in TEAM_PROFILES


def normalize_team_id(raw: object | None) -> str | None:
    value = str(raw or "").strip()
    return value if value in TEAM_PROFILES else None


def get_team_profile(team_id: object | None) -> dict[str, Any] | None:
    key = normalize_team_id(team_id)
    if not key:
        return None
    return TEAM_PROFILES[key]


def list_chat_teams(*, include_disabled: bool = False) -> list[dict[str, Any]]:
    """Teams exposed to Chat selector when feature flag is on (or include_disabled)."""
    if not include_disabled and not team_feature_enabled():
        return []
    rows: list[dict[str, Any]] = []
    for team_id, meta in TEAM_PROFILES.items():
        if not meta.get("chat_selectable", True):
            continue
        mode = meta.get("mode")
        mode_value = getattr(mode, "value", mode)
        members = []
        for member_id in tuple(meta.get("members") or ()):
            member = get_agent_profile(member_id)
            members.append(
                {
                    "id": str(member.get("id") or member_id),
                    "name": str(member.get("name") or member_id),
                    "role": str(member.get("role") or ""),
                }
            )
        rows.append(
            {
                "id": str(meta["id"]),
                "name": str(meta["name"]),
                "role": str(meta.get("role") or ""),
                "description": str(meta.get("description") or ""),
                "category": str(meta.get("category") or "team"),
                "capabilities": str(meta.get("capabilities") or ""),
                "recommended_for": str(meta.get("recommended_for") or ""),
                "kind": "team",
                "mode": str(mode_value or ""),
                "members": members,
                "prefer_live_search": bool(meta.get("prefer_live_search")),
            }
        )
    return rows


async def _load_prompt(name: str) -> str:
    if not name:
        return ""
    path = PROMPT_DIR / name
    try:
        return await AsyncPath(path).read_text(encoding="utf-8")
    except OSError:
        return ""


async def _member_from_profile(
    agent_id: str,
    *,
    model: Any,
    instructions_extra: str = "",
    search_knowledge: bool = False,
    knowledge: Any | None = None,
    knowledge_filters: dict[str, Any] | None = None,
    memory_enabled: bool = False,
    enable_tools: bool = True,
    store_raw_tool_io: bool = False,
    db: Any | None = None,
) -> Agent:
    profile = get_agent_profile(agent_id)
    prompt_name = str(profile.get("prompt_full") or "")
    instructions: list[str] = []
    prompt = await _load_prompt(prompt_name)
    if prompt:
        instructions.append(prompt)
    else:
        instructions.append(str(profile.get("description") or ""))
    if instructions_extra:
        instructions.append(instructions_extra)
    tools = (
        build_tools_for_profile(profile)
        if enable_tools and profile.get("builtin_tools")
        else []
    )
    # Members do not get input guardrails — Team leader pre_hooks cover user input.
    return Agent(
        id=str(profile["id"]),
        name=str(profile["name"]),
        role=str(profile.get("role") or ""),
        description=str(profile.get("description") or ""),
        instructions=instructions,
        model=model,
        tools=tools,
        knowledge=knowledge if search_knowledge else None,
        knowledge_retriever=(
            build_knowledge_retriever(knowledge) if search_knowledge and knowledge is not None else None
        ),
        knowledge_filters=knowledge_filters if search_knowledge else None,
        search_knowledge=bool(search_knowledge and knowledge is not None),
        add_search_knowledge_instructions=bool(search_knowledge and knowledge is not None),
        db=db,
        # Member multi-turn: Agno injects member history when enabled (Team also
        # adds team history separately via add_team_history_to_members).
        add_history_to_context=True,
        num_history_runs=int(profile.get("history_runs") or 3),
        update_memory_on_run=False,
        add_memories_to_context=False,
        # Member tool payloads can contain CSV, SQL, or website data. Persist
        # them only when the operator explicitly enables raw tool IO in Chat.
        store_tool_messages=store_raw_tool_io,
        markdown=True,
        tool_call_limit=profile.get("tool_call_limit"),
    )


async def build_team(
    team_id: str,
    *,
    model_id: str | None = None,
    reasoning_effort: str | None = None,
    live_search: bool | None = None,
    search_knowledge: bool = False,
    knowledge: Any | None = None,
    knowledge_filters: dict[str, Any] | None = None,
    memory_enabled: bool = False,
    enable_tools: bool = True,
    store_raw_tool_io: bool = False,
    media_files: Any = None,
) -> Team:
    profile = get_team_profile(team_id)
    if profile is None:
        raise ValueError(f"Unknown team id: {team_id}")

    config = await get_model_for_run(model_id)
    if live_search is not None:
        config = {**config, "live_search_enabled": bool(live_search)}
    elif profile.get("prefer_live_search"):
        config = {**config, "live_search_enabled": True}
    if reasoning_effort is None:
        model = build_agno_model(config)
    else:
        model = build_agno_model(config, reasoning_effort=reasoning_effort)

    db = get_async_agno_postgres_db()
    member_ids = tuple(profile.get("members") or ())
    if enable_tools and media_files:
        for mid in member_ids:
            if profile_uses_analysis_sandbox(get_agent_profile(mid)):
                stage_media_into_analysis_dir(media_files)
                break
    members: list[Agent] = []
    for mid in member_ids:
        extra = ""
        if mid == "deep-research":
            extra = "你是团队中的调研专员：优先检索与交叉验证，输出带来源的发现。"
        elif mid == "data-analysis":
            extra = "你是团队中的数据分析专员：对数字与表格做可复现核算，指出异常。"
        # Broadcast runs members concurrently; give each a model copy so provider
        # clients / mutable request state never collide on one instance.
        member_model = deepcopy(model)
        members.append(
            await _member_from_profile(
                mid,
                model=member_model,
                instructions_extra=extra,
                search_knowledge=search_knowledge and enable_tools,
                knowledge=knowledge,
                knowledge_filters=knowledge_filters,
                memory_enabled=memory_enabled,
                enable_tools=enable_tools,
                store_raw_tool_io=store_raw_tool_io,
                db=db,
            )
        )

    mode = profile.get("mode") or TeamMode.coordinate
    if not isinstance(mode, TeamMode):
        mode = TeamMode.coordinate

    if mode == TeamMode.route:
        leader_instructions = [
            "你是路由负责人：把任务交给最合适的单一专员，直接返回其结果。",
            "- 公开资料/综述/交叉验证 → deep-research",
            "- 计算/表格/SQL/指标 → data-analysis",
            "不要综合多个成员；route 模式只委派一人。",
            "不要假装调用了 MCP 或安全 Skills。",
        ]
    elif mode == TeamMode.tasks:
        leader_instructions = [
            "你是任务编排负责人：把复杂请求拆成可验收的团队任务，并在最终回答中综合结果。",
            "先创建边界清晰、自包含的任务，明确负责人、完成条件与依赖关系。",
            "公开资料检索、事实核验和来源整理 → deep-research；计算、表格、SQL 和数字复核 → data-analysis。",
            "两个专员的任务彼此独立时，使用 execute_tasks_parallel 并行执行；"
            "只有确实依赖前序结果时才声明 dependencies。",
            "每名专员同一时间最多执行一项任务，避免混合不同任务的结论。",
            "所有任务完成后，再比较证据与数字并输出统一结论；不要只拼接成员原文。",
            "最终回答必须区分事实与推断，列出关键来源、复核方法与未解决问题。",
            "不要假装调用了 MCP 或安全 Skills；需要处置告警时建议用户改用安全运营助手。",
        ]
    elif mode == TeamMode.broadcast:
        leader_instructions = [
            "你是会诊负责人：同一问题已/将并行交给全部专员独立评估。",
            "汇总一致点与分歧，标明各方证据强度，再给出结论与置信度。",
            "数字必须可复核；关键主张带来源。",
            "不要假装调用了 MCP 或安全 Skills。",
        ]
    else:
        leader_instructions = [
            "你是协调负责人（coordinate）：按任务选择并先后委派成员，再综合。",
            "- 公开资料/综述 → deep-research",
            "- 计算/表格/SQL/指标 → data-analysis",
            "- 复杂任务可多轮委派并综合双方结果",
            "最终回答必须：区分事实与推断；数字可复核；列出关键来源。",
            "不要假装调用了 MCP 或安全 Skills；需要处置告警时建议用户改用安全运营助手。",
        ]

    chat_settings = await get_chat_settings_async()
    history_runs = max(1, int(chat_settings.num_history_runs or 4))
    use_summaries = bool(chat_settings.session_summaries_enabled)
    agentic = bool(chat_settings.enable_agentic_memory) and bool(memory_enabled)
    mode_floor = 60 if mode == TeamMode.tasks else 48
    # Team leaders need a higher floor than single-agent defaults; Settings can raise it.
    if chat_settings.default_tool_call_limit is not None:
        leader_tool_limit = max(mode_floor, int(chat_settings.default_tool_call_limit))
    else:
        leader_tool_limit = mode_floor

    team = Team(
        **apply_guardrails_kwargs(
            {
                "members": cast(Any, members),
                "id": str(profile["id"]),
                "name": str(profile["name"]),
                "role": str(profile.get("role") or ""),
                "description": str(profile.get("description") or ""),
                "mode": mode,
                "model": model,
                "db": db,
                "markdown": bool(chat_settings.markdown),
                "instructions": leader_instructions,
                "expected_output": (
                    "结构化 Markdown：先给结论，再列证据/数字与来源；"
                    "route 模式直接呈现专员结果即可。"
                ),
                # Coordinate: leader synthesizes; route: member response may surface.
                "respond_directly": mode == TeamMode.route,
                # Route returns the selected member's answer directly, so preserve the
                # user's original wording instead of paying for a leader rewrite.
                "determine_input_for_members": mode != TeamMode.route,
                "max_iterations": 10 if mode == TeamMode.tasks else 8,
                "tool_call_limit": leader_tool_limit,
                "get_member_information_tool": True,
                "share_member_interactions": mode
                in {TeamMode.coordinate, TeamMode.broadcast, TeamMode.tasks},
                "show_members_responses": False,
                "stream_member_events": True,
                "store_member_responses": True,
                "store_tool_messages": store_raw_tool_io,
                "add_datetime_to_context": bool(chat_settings.add_datetime_to_context),
                "add_history_to_context": history_runs > 0,
                "num_history_runs": history_runs,
                "max_tool_calls_from_history": chat_settings.max_tool_calls_from_history,
                "add_team_history_to_members": True,
                "num_team_history_runs": min(2, history_runs),
                "add_name_to_context": True,
                "add_member_tools_to_context": False,
                "update_memory_on_run": bool(memory_enabled) and not agentic,
                "add_memories_to_context": bool(memory_enabled),
                "enable_agentic_memory": agentic,
                "session_summary_manager": (
                    SessionSummaryManager(model=model) if use_summaries else None
                ),
                "enable_session_summaries": use_summaries,
                "add_session_summary_to_context": use_summaries,
                "knowledge": knowledge if search_knowledge and enable_tools else None,
                "knowledge_retriever": (
                    build_knowledge_retriever(knowledge)
                    if search_knowledge and enable_tools and knowledge is not None
                    else None
                ),
                "knowledge_filters": (
                    knowledge_filters if search_knowledge and enable_tools else None
                ),
                "search_knowledge": bool(
                    search_knowledge and enable_tools and knowledge is not None
                ),
                "add_search_knowledge_instructions": bool(
                    search_knowledge and enable_tools and knowledge is not None
                ),
            }
        )
    )
    member_list = team.members if isinstance(team.members, list) else []
    logger.info(
        "Built Agno Team id={} mode={} members={}",
        team.id,
        mode,
        [getattr(m, "id", None) for m in member_list],
    )
    return team
