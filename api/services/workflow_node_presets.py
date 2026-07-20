"""Built-in business node presets + validation for custom step nodes."""

from __future__ import annotations

from typing import Any

from api.services.agent_catalog import AGENT_PROFILES
from api.services.workflow_compiler import (
    WorkflowDefinitionError,
    normalize_user_input_schema,
)

# Product-aligned step presets for the security / analysis / research workflow.
BUILTIN_NODE_PRESETS: list[dict[str, Any]] = [
    {
        "id": "biz-alert-triage",
        "name": "告警研判",
        "description": "安全运营助手：摘要告警、提取 IOC、给出严重级别。",
        "color": "#1677ff",
        "source": "builtin",
        "definition": {
            "type": "step",
            "name": "告警研判",
            "executor": {"kind": "agent", "ref": "security-operations"},
            "instructions": (
                "研判输入告警：给出简要结论、IOC 列表、严重级别（critical/high/medium/low）"
                "与建议下一步。将 severity 关键字写入回复。"
            ),
            "skills": [],
            "requires_confirmation": False,
            "requires_user_input": False,
            "requires_output_review": False,
        },
    },
    {
        "id": "biz-cve-intel",
        "name": "CVE 情报",
        "description": "绑定 cve-intel-skill，补充漏洞上下文与利用风险。",
        "color": "#fa8c16",
        "source": "builtin",
        "definition": {
            "type": "step",
            "name": "CVE 情报",
            "executor": {"kind": "agent", "ref": "security-operations"},
            "instructions": (
                "针对告警或资产中的 CVE/产品版本，补充漏洞摘要、影响面、修复建议。"
                "引用可验证来源，避免臆测。"
            ),
            "skills": ["cve-intel-skill"],
            "requires_confirmation": False,
            "requires_user_input": False,
            "requires_output_review": False,
        },
    },
    {
        "id": "biz-hitl-contain",
        "name": "隔离确认 (HITL)",
        "description": "处置前人工确认；绑定 hitl-containment-skill。",
        "color": "#cf1322",
        "source": "builtin",
        "definition": {
            "type": "step",
            "name": "隔离确认",
            "executor": {"kind": "agent", "ref": "security-operations"},
            "instructions": "拟定隔离/封禁方案与影响评估，等待人工审批后再执行。",
            "skills": ["hitl-containment-skill"],
            "requires_confirmation": True,
            "confirmation_message": "确认执行隔离/封禁处置？",
            "requires_user_input": False,
            "requires_output_review": False,
        },
    },
    {
        "id": "biz-lite-summary",
        "name": "轻量摘要",
        "description": "无工具兜底：纯推理改写与分支摘要。",
        "color": "#8c8c8c",
        "source": "builtin",
        "definition": {
            "type": "step",
            "name": "轻量摘要",
            "executor": {"kind": "agent", "ref": "safe-fallback"},
            "instructions": "用简洁中文总结上一步输出，不调用外部工具，不编造事实。",
            "skills": [],
            "requires_confirmation": False,
            "requires_user_input": False,
            "requires_output_review": False,
        },
    },
    {
        "id": "biz-data-analysis",
        "name": "数据分析",
        "description": "表格/指标分析步骤（无 MCP/安全 Skills）。",
        "color": "#13c2c2",
        "source": "builtin",
        "definition": {
            "type": "step",
            "name": "数据分析",
            "executor": {"kind": "agent", "ref": "data-analysis"},
            "instructions": "对输入数据做清洗、统计与异常定位，给出可复现的结论与下一步建议。",
            "skills": [],
            "requires_confirmation": False,
            "requires_user_input": False,
            "requires_output_review": False,
        },
    },
    {
        "id": "biz-deep-research",
        "name": "深度研究",
        "description": "多源研究与结构化报告步骤。",
        "color": "#722ed1",
        "source": "builtin",
        "definition": {
            "type": "step",
            "name": "深度研究",
            "executor": {"kind": "agent", "ref": "deep-research"},
            "instructions": "围绕主题做多源检索与交叉验证，输出结构化研究报告与引用。",
            "skills": [],
            "requires_confirmation": False,
            "requires_user_input": False,
            "requires_output_review": False,
        },
    },
]


def list_builtin_node_presets() -> list[dict[str, Any]]:
    return [dict(item) for item in BUILTIN_NODE_PRESETS]


def normalize_custom_step_definition(raw: object) -> dict[str, Any]:
    """Validate a user custom-node definition (step-only)."""
    if not isinstance(raw, dict):
        raise ValueError("definition must be an object")
    node_type = str(raw.get("type") or "step").strip() or "step"
    if node_type != "step":
        raise ValueError("custom nodes currently support type=step only")
    executor = raw.get("executor")
    if not isinstance(executor, dict):
        raise ValueError("definition.executor is required")
    kind = str(executor.get("kind") or "agent").strip() or "agent"
    if kind != "agent":
        raise ValueError("definition.executor.kind must be 'agent'")
    raw_ref = str(executor.get("ref") or "").strip()
    if raw_ref not in AGENT_PROFILES:
        raise ValueError(f"unknown executor.ref: {raw_ref or '(empty)'}")
    profile = AGENT_PROFILES[raw_ref]
    if not profile.get("workflow_selectable", True):
        raise ValueError(f"executor.ref is not workflow-selectable: {raw_ref}")
    ref = raw_ref
    name = str(raw.get("name") or "").strip() or str(profile.get("name") or ref)
    instructions = str(raw.get("instructions") or "")
    skills_raw = raw.get("skills")
    skills: list[str] = []
    if isinstance(skills_raw, list):
        skills = [str(item).strip() for item in skills_raw if str(item).strip()]
    if not profile.get("attach_skills", False):
        skills = []
    capabilities = str(profile.get("capabilities") or "")
    supports_hitl = "hitl" in {part.strip() for part in capabilities.split(",") if part.strip()}
    requires_confirmation = bool(raw.get("requires_confirmation")) if supports_hitl else False
    requires_user_input = bool(raw.get("requires_user_input")) if supports_hitl else False
    requires_output_review = bool(raw.get("requires_output_review")) if supports_hitl else False
    payload: dict[str, Any] = {
        "type": "step",
        "name": name,
        "executor": {"kind": "agent", "ref": ref},
        "instructions": instructions,
        "skills": skills,
        "requires_confirmation": requires_confirmation,
        "requires_user_input": requires_user_input,
        "requires_output_review": requires_output_review,
    }
    confirmation_message = str(raw.get("confirmation_message") or "").strip()
    user_input_message = str(raw.get("user_input_message") or "").strip()
    output_review_message = str(raw.get("output_review_message") or "").strip()
    if confirmation_message:
        payload["confirmation_message"] = confirmation_message
    if user_input_message:
        payload["user_input_message"] = user_input_message
    if output_review_message:
        payload["output_review_message"] = output_review_message
    if raw.get("user_input_schema") is not None:
        try:
            schema = normalize_user_input_schema(
                raw.get("user_input_schema"), path="definition"
            )
        except WorkflowDefinitionError as exc:
            raise ValueError(str(exc)) from exc
        if schema:
            payload["user_input_schema"] = schema
    return payload


def serialize_custom_node_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "description": str(row.get("description") or ""),
        "color": str(row.get("color") or "#1677ff"),
        "source": "user",
        "definition": row.get("definition") if isinstance(row.get("definition"), dict) else {},
        "created_at": int(row.get("created_at") or 0),
        "updated_at": int(row.get("updated_at") or 0),
    }
