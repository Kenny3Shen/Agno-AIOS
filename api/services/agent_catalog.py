"""Built-in Agent catalog for Chat + Workflow Studio.

Profiles share stable ``id`` keys used as Agno ``Agent.id`` / workflow executor ``ref``.
Security operations remains the default product assistant; analysis/research are
tool-focused specialists without MCP/HITL by default.
"""

from __future__ import annotations

from typing import Any

DEFAULT_AGENT_ID = "security-operations"

# Chat-selectable agents (exclude workflow-only lite fallback).
CHAT_AGENT_IDS: tuple[str, ...] = (
    "security-operations",
    "data-analysis",
    "deep-research",
)

AGENT_PROFILES: dict[str, dict[str, Any]] = {
    "security-operations": {
        "id": "security-operations",
        "name": "安全运营助手",
        "role": "安全防御运营助手",
        "description": (
            "安全运营：威胁研判、知识检索、CVE/Workflow 与 HITL 处置。"
            "默认挂载 MCP 与 Local Skills（可按意图裁剪）。"
        ),
        "category": "operations",
        "kind": "security",
        "capabilities": "skills,hitl,knowledge,mcp",
        "recommended_for": "告警研判、隔离确认、工作流编排、安全报告",
        "prompt_full": "security_operations.md",
        "prompt_lite": "security_operations_lite.md",
        "connect_mcp": True,
        "attach_skills": True,
        "builtin_tools": (),
        "default_search_knowledge": True,
        "prefer_live_search": False,
        "history_runs": 5,
        "tool_call_limit": None,
        "chat_selectable": True,
        "workflow_selectable": True,
    },
    "data-analysis": {
        "id": "data-analysis",
        "name": "数据分析助手",
        "role": "数据分析师",
        "description": (
            "数据分析：表格清洗、统计汇总、可选只读 SQL、趋势对比与可复现计算。"
            "内置计算器与受控 Python（Polars）；Knowledge 承载业务口径；不挂 MCP/安全 Skills。"
        ),
        "category": "analysis",
        "kind": "analysis",
        "capabilities": "calculator,python,file,csv,sql,knowledge",
        "recommended_for": "CSV/指标解读、可选只读 SQLTools、异常定位、对比与可视化建议",
        "prompt_full": "data_analysis.md",
        "prompt_lite": "data_analysis.md",
        "connect_mcp": False,
        "attach_skills": False,
        "builtin_tools": ("calculator", "python", "file", "csv", "sql", "reasoning"),
        "default_search_knowledge": True,
        "prefer_live_search": False,
        "history_runs": 4,
        "tool_call_limit": 24,
        "chat_selectable": True,
        "workflow_selectable": True,
    },
    "deep-research": {
        "id": "deep-research",
        "name": "深度研究助手",
        "role": "研究分析师",
        "description": (
            "深度研究：多源检索、交叉验证、结构化研究报告。"
            "内置推理、网页阅读与可选网页搜索；可配合 Live Search / 知识库；不挂 MCP。"
        ),
        "category": "research",
        "kind": "research",
        "capabilities": "reasoning,website,web_search,knowledge,live_search",
        "recommended_for": "主题调研、竞品/威胁情报综述、多源对照报告",
        "prompt_full": "deep_research.md",
        "prompt_lite": "deep_research.md",
        "connect_mcp": False,
        "attach_skills": False,
        "builtin_tools": ("reasoning", "website", "web_search", "calculator"),
        "default_search_knowledge": True,
        "prefer_live_search": True,
        "history_runs": 6,
        "tool_call_limit": 40,
        "chat_selectable": True,
        "workflow_selectable": True,
    },
    "safe-fallback": {
        "id": "safe-fallback",
        "name": "轻量分析助手",
        "role": "安全分析助手",
        "description": (
            "无工具轻量步骤：不挂 MCP/Skills，适合纯推理、文案整理、"
            "分支兜底与失败降级路径。"
        ),
        "category": "lite",
        "kind": "lite",
        "capabilities": "reasoning",
        "recommended_for": "条件分支兜底、摘要改写、无外部副作用步骤",
        "prompt_full": "safe_fallback.md",
        "prompt_lite": "safe_fallback.md",
        "connect_mcp": False,
        "attach_skills": False,
        "builtin_tools": (),
        "default_search_knowledge": False,
        "prefer_live_search": False,
        "history_runs": 2,
        "tool_call_limit": None,
        "chat_selectable": False,
        "workflow_selectable": True,
    },
}


def normalize_agent_id(raw: object | None) -> str:
    """Return a known agent id; unknown values fall back to security-operations."""
    value = str(raw or "").strip()
    if value in AGENT_PROFILES:
        return value
    return DEFAULT_AGENT_ID


def get_agent_profile(agent_id: object | None) -> dict[str, Any]:
    return AGENT_PROFILES[normalize_agent_id(agent_id)]


def list_chat_agents() -> list[dict[str, Any]]:
    """Product catalog for Chat agent Select."""
    rows: list[dict[str, Any]] = []
    for agent_id in CHAT_AGENT_IDS:
        meta = AGENT_PROFILES[agent_id]
        rows.append(
            {
                "id": str(meta["id"]),
                "name": str(meta["name"]),
                "role": str(meta["role"]),
                "description": str(meta["description"]),
                "category": str(meta.get("category") or ""),
                "capabilities": str(meta.get("capabilities") or ""),
                "recommended_for": str(meta.get("recommended_for") or ""),
                "kind": "agent",
                "prefer_live_search": bool(meta.get("prefer_live_search")),
            }
        )
    return rows


def list_workflow_executor_options() -> list[dict[str, str]]:
    """Product catalog for Workflow Studio executor Select."""
    rows: list[dict[str, str]] = []
    for ref, meta in AGENT_PROFILES.items():
        if not meta.get("workflow_selectable", True):
            continue
        rows.append(
            {
                "ref": ref,
                "kind": "agent",
                "name": str(meta["name"]),
                "description": str(meta["description"]),
                "category": str(meta.get("category") or "operations"),
                "capabilities": str(meta.get("capabilities") or ""),
                "recommended_for": str(meta.get("recommended_for") or ""),
                "role": str(meta.get("role") or ""),
            }
        )
    return rows


def profile_connects_mcp(agent_id: object | None) -> bool:
    return bool(get_agent_profile(agent_id).get("connect_mcp"))


def profile_attaches_skills(agent_id: object | None) -> bool:
    return bool(get_agent_profile(agent_id).get("attach_skills"))


def resolve_chat_run_target(raw: object | None) -> tuple[str, str]:
    """Return ``(kind, id)`` for a Chat run target.

    kind is ``"agent"`` or ``"team"``. Unknown values fall back to the default agent.
    Known Team ids retain their kind while disabled so the run runtime can
    return ``TEAM_DISABLED`` rather than silently executing the default Agent.
    """
    from api.services.team_runtime import (
        normalize_team_id,
    )

    value = str(raw or "").strip()
    team_id = normalize_team_id(value)
    if team_id:
        return ("team", team_id)
    # Unknown team-like ids fall through to default agent when not in catalog.
    # Known suffixes: -team / -route / -broadcast / -tasks (see TEAM_PROFILES).
    if value in AGENT_PROFILES and AGENT_PROFILES[value].get("chat_selectable", True):
        return ("agent", value)
    return ("agent", DEFAULT_AGENT_ID)
