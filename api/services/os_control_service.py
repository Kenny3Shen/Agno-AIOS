from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4
from typing import Any

from psycopg import sql

from api.mcp.config import (
    SERVICE_IDS,
    normalize_hiagents,
    read_mcp_config,
    services_from_config,
)
from api.auth.permissions import actor_id, has_permission
from api.services.llm_service import get_all_sessions
from api.services.postgres_store import (
    agno_schema,
    app_schema,
    coerce_json_value,
    ensure_agno_postgres_tables,
    knowledge_schema,
    postgres_connect,
)
from api.services.skill_service import (
    is_skill_enabled,
    iter_skill_dirs,
    list_skill_scripts,
    parse_skill_metadata,
)
from api.services.scheduler_service import get_scheduler_payload as get_agno_scheduler_payload

OsMetric = dict[str, Any]
OsRecord = dict[str, Any]
OsPayload = dict[str, Any]

CONTROL_TABLES = {
    "evaluation": "os_eval_runs",
    "approvals": "os_approvals",
}


def _now() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.isoformat()
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, UTC).isoformat()
        except (OSError, ValueError):
            return str(value)
    return str(value)


def _compact(value: Any, limit: int = 96) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _metric(label: str, value: Any, hint: str = "", tone: str = "blue") -> OsMetric:
    return {"label": label, "value": value, "hint": hint, "tone": tone}


def _record(
    *,
    record_id: Any,
    title: str,
    subtitle: str = "",
    status: str = "ready",
    meta: dict[str, Any] | None = None,
    updated_at: Any = "",
) -> OsRecord:
    return {
        "id": str(record_id or title),
        "title": title,
        "subtitle": subtitle,
        "status": status,
        "meta": meta or {},
        "updated_at": _iso(updated_at),
    }


def _payload(
    *,
    module: str,
    title: str,
    description: str,
    metrics: list[OsMetric],
    records: list[OsRecord],
    status: str = "ready",
) -> OsPayload:
    return {
        "module": module,
        "title": title,
        "description": description,
        "status": status,
        "metrics": metrics,
        "records": records,
        "generated_at": _iso(_now()),
    }


def _count(schema_name: str, table_name: str) -> int:
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT count(*) AS count FROM {}").format(
                        sql.Identifier(schema_name, table_name)
                    )
                )
                row = cursor.fetchone()
    except Exception:
        return 0
    return int(row.get("count") or 0) if row else 0


def _count_where(
    schema_name: str,
    table_name: str,
    where: sql.SQL | sql.Composed | None = None,
    params: tuple[Any, ...] = (),
) -> int:
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                query = sql.SQL("SELECT count(*) AS count FROM {}").format(
                    sql.Identifier(schema_name, table_name)
                )
                if where is not None:
                    query += sql.SQL(" WHERE ") + where
                cursor.execute(query, params)
                row = cursor.fetchone()
    except Exception:
        return 0
    return int(row.get("count") or 0) if row else 0


def _fetch_rows(
    schema_name: str,
    table_name: str,
    *,
    limit: int = 100,
    order_by: str | None = None,
    descending: bool = True,
    where: sql.SQL | sql.Composed | None = None,
    params: tuple[Any, ...] = (),
) -> list[dict[str, Any]]:
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                query = sql.SQL("SELECT * FROM {}").format(
                    sql.Identifier(schema_name, table_name)
                )
                if where is not None:
                    query += sql.SQL(" WHERE ") + where
                if order_by:
                    direction = sql.SQL("DESC") if descending else sql.SQL("ASC")
                    query += sql.SQL(" ORDER BY {} {}").format(
                        sql.Identifier(order_by),
                        direction,
                    )
                query += sql.SQL(" LIMIT %s")
                cursor.execute(query, (*params, limit))
                return list(cursor.fetchall())
    except Exception:
        return []


def _scalar_float(
    query: sql.SQL | sql.Composed,
    params: tuple[Any, ...] = (),
    default: float = 0.0,
) -> float:
    try:
        with postgres_connect() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
    except Exception:
        return default
    if not row:
        return default
    value = next(iter(row.values()), default)
    try:
        return float(value or default)
    except (TypeError, ValueError):
        return default


def _owner_user_id(actor: Any | None, any_permission: str) -> str | None:
    if actor is not None and has_permission(actor, any_permission):
        return None
    return actor_id(actor) if actor is not None else ""


def _user_where(actor: Any | None, any_permission: str) -> tuple[sql.SQL | None, tuple[Any, ...]]:
    owner_user_id = _owner_user_id(actor, any_permission)
    if owner_user_id is None:
        return None, ()
    return sql.SQL("user_id = %s"), (owner_user_id,)


def _span_count_for_actor(actor: Any | None) -> int:
    owner_user_id = _owner_user_id(actor, "trace:read:any")
    if owner_user_id is None:
        return _count(agno_schema(), "agno_spans")
    return int(
        _scalar_float(
            sql.SQL(
                """
                SELECT count(*)
                FROM {} AS spans
                WHERE spans.trace_id IN (
                    SELECT traces.trace_id
                    FROM {} AS traces
                    WHERE traces.user_id = %s
                )
                """
            ).format(
                sql.Identifier(agno_schema(), "agno_spans"),
                sql.Identifier(agno_schema(), "agno_traces"),
            ),
            (owner_user_id,),
        )
    )


def _ensure_control_tables() -> None:
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(
                    sql.Identifier(app_schema())
                )
            )
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        target TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'draft',
                        score DOUBLE PRECISION,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb
                    )
                    """
                ).format(sql.Identifier(app_schema(), CONTROL_TABLES["evaluation"]))
            )
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        requester TEXT NOT NULL DEFAULT '',
                        action TEXT NOT NULL DEFAULT '',
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb
                    )
                    """
                ).format(sql.Identifier(app_schema(), CONTROL_TABLES["approvals"]))
            )
            cursor.execute(
                sql.SQL(
                    """
                    DROP TABLE IF EXISTS {}
                    """
                ).format(sql.Identifier(app_schema(), "os_schedules"))
            )


def submit_approval_request(
    *,
    title: str,
    requester: str,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    _ensure_control_tables()
    request_id = f"approval-{uuid4()}"
    with postgres_connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    """
                    INSERT INTO {} (id, title, requester, action, status, metadata)
                    VALUES (%s, %s, %s, %s, 'pending', %s::jsonb)
                    RETURNING *
                    """
                ).format(sql.Identifier(app_schema(), CONTROL_TABLES["approvals"])),
                (
                    request_id,
                    title.strip() or action,
                    requester,
                    action,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            row = cursor.fetchone()
    return dict(row or {"id": request_id, "status": "pending"})


def _runs_count(runs: Any) -> int:
    value = coerce_json_value(runs)
    return len(value) if isinstance(value, list) else 0


def get_sessions_payload(actor: Any | None = None) -> OsPayload:
    ensure_agno_postgres_tables()
    sessions = get_all_sessions(
        include_archived=True,
        owner_user_id=_owner_user_id(actor, "session:read:any"),
    )
    active_cutoff = _now() - timedelta(days=1)
    active_count = 0
    records: list[OsRecord] = []

    for session in sessions[:100]:
        updated_at = session.get("updated_at")
        updated_dt = updated_at if isinstance(updated_at, datetime) else None
        if updated_dt and updated_dt.tzinfo is None:
            updated_dt = updated_dt.replace(tzinfo=UTC)
        if updated_dt and updated_dt >= active_cutoff:
            active_count += 1
        archived = bool(session.get("archived"))
        records.append(
            _record(
                record_id=session.get("session_id"),
                title=_compact(session.get("preview") or "新对话", 64),
                subtitle=str(session.get("session_id") or ""),
                status="archived" if archived else "active" if updated_dt and updated_dt >= active_cutoff else "idle",
                meta={
                    "created": _iso(session.get("created_at")),
                    "archived": archived,
                },
                updated_at=updated_at,
            )
        )

    return _payload(
        module="sessions",
        title="Sessions",
        description="Agent 会话库存与上下文历史。",
        metrics=[
            _metric("Sessions", len(sessions), "Agno session rows", "blue"),
            _metric("Active 24h", active_count, "最近 24 小时更新", "green"),
            _metric("Archived", sum(1 for session in sessions if session.get("archived")), "Chat 侧栏软归档", "yellow"),
            _metric("Shown", len(records), "当前返回记录", "yellow"),
        ],
        records=records,
    )


def get_studio_payload(actor: Any | None = None) -> OsPayload:
    data = read_mcp_config()
    services = services_from_config(data)
    hiagents = normalize_hiagents(data.get("hiagent", []))
    skill_dirs = iter_skill_dirs()

    skill_records = []
    enabled_skills = 0
    for skill_dir in skill_dirs:
        name, description = parse_skill_metadata(skill_dir)
        enabled = is_skill_enabled(skill_dir, name)
        if enabled:
            enabled_skills += 1
        skill_records.append(
            _record(
                record_id=f"skill:{name}",
                title=name,
                subtitle=_compact(description, 120),
                status="enabled" if enabled else "disabled",
                meta={"scripts": len(list_skill_scripts(skill_dir)), "type": "skill"},
            )
        )

    records: list[OsRecord] = [
        _record(
            record_id="agent:security-operations",
            title="安全运营助手",
            subtitle="威胁情报分析、剧本执行、知识检索与运行观测。",
            status="online",
            meta={"type": "agent", "runtime": "Agno Agent"},
        ),
        _record(
            record_id="team:security-data-fabric",
            title="Security Data Fabric",
            subtitle="CVE、资产、Collect、Knowledge 共同构成安全数据底座。",
            status="ready",
            meta={"type": "team", "mode": "coordinate"},
        ),
    ]
    for service_id in SERVICE_IDS:
        records.append(
            _record(
                record_id=f"mcp:{service_id}",
                title=f"MCP {service_id}",
                subtitle="FastMCP mounted service",
                status="enabled" if services.get(service_id) else "disabled",
                meta={"type": "mcp"},
            )
        )
    for entry in hiagents:
        records.append(
            _record(
                record_id=f"hiagent:{entry['url']}",
                title=entry["name"],
                subtitle=_compact(entry.get("description") or entry["url"], 120),
                status="enabled" if entry.get("enabled") else "disabled",
                meta={"type": "hi-agent", "url": entry["url"]},
            )
        )
    records.extend(skill_records)

    return _payload(
        module="studio",
        title="Studio",
        description="Agent、Team、MCP、Hi-Agent 与 Skills 组件注册视图。",
        metrics=[
            _metric("Agents", 1, "当前安全运营 Agent", "green"),
            _metric("MCP", f"{sum(1 for enabled in services.values() if enabled)}/{len(services)}", "启用服务", "yellow"),
            _metric("Skills", f"{enabled_skills}/{len(skill_dirs)}", "启用技能", "blue"),
            _metric("Hi-Agent", len(hiagents), "外部 Agent 接入", "red"),
        ],
        records=records,
    )


def get_memory_payload(actor: Any | None = None) -> OsPayload:
    ensure_agno_postgres_tables()
    memory_where, memory_params = _user_where(actor, "memory:read:any")
    rows = _fetch_rows(
        agno_schema(),
        "agno_memories",
        limit=100,
        order_by="updated_at",
        where=memory_where,
        params=memory_params,
    )
    users = {str(row.get("user_id") or row.get("agent_id") or "default") for row in rows}
    records = []
    for row in rows:
        memory = coerce_json_value(row.get("memory") or row.get("memories") or row.get("content"))
        if isinstance(memory, dict):
            title = _compact(memory.get("memory") or memory.get("content") or memory.get("summary") or row.get("id"), 80)
        else:
            title = _compact(memory or row.get("id"), 80)
        records.append(
            _record(
                record_id=row.get("id") or row.get("memory_id") or title,
                title=title or "Memory",
                subtitle=str(row.get("user_id") or row.get("agent_id") or "default"),
                status=str(row.get("status") or "stored"),
                meta={
                    "topic": row.get("topic") or row.get("name") or "",
                    "source": row.get("source") or "agno",
                },
                updated_at=row.get("updated_at") or row.get("created_at"),
            )
            )

    return _payload(
        module="memory",
        title="Memory",
        description="Agno 用户记忆库存与增长监测。",
        metrics=[
            _metric("Memories", _count_where(agno_schema(), "agno_memories", memory_where, memory_params), "PostgresDb memory rows", "blue"),
            _metric("Users", len(users), "本页涉及 user_id", "green"),
            _metric("Mode", "Auto", "update_memory_on_run", "yellow"),
        ],
        records=records,
    )


def get_metrics_payload(actor: Any | None = None) -> OsPayload:
    ensure_agno_postgres_tables()
    trace_where, trace_params = _user_where(actor, "trace:read:any")
    session_where, session_params = _user_where(actor, "session:read:any")
    memory_where, memory_params = _user_where(actor, "memory:read:any")
    trace_count = _count_where(agno_schema(), "agno_traces", trace_where, trace_params)
    span_count = _span_count_for_actor(actor)
    session_count = _count_where(agno_schema(), "agno_sessions", session_where, session_params)
    memory_count = _count_where(agno_schema(), "agno_memories", memory_where, memory_params)
    avg_duration = _scalar_float(
        sql.SQL("SELECT avg(duration_ms) FROM {}{}").format(
            sql.Identifier(agno_schema(), "agno_traces"),
            sql.SQL(" WHERE ") + trace_where if trace_where is not None else sql.SQL(""),
        ),
        trace_params,
    )
    error_count = int(
        _scalar_float(
            sql.SQL("SELECT count(*) FROM {} WHERE status = 'ERROR'{}").format(
                sql.Identifier(agno_schema(), "agno_traces"),
                sql.SQL(" AND ") + trace_where if trace_where is not None else sql.SQL(""),
            ),
            trace_params,
        )
    )

    rows = _fetch_rows(
        agno_schema(),
        "agno_traces",
        limit=20,
        order_by="start_time",
        where=trace_where,
        params=trace_params,
    )
    records = [
        _record(
            record_id=row.get("trace_id"),
            title=_compact(row.get("name") or row.get("trace_id"), 80),
            subtitle=str(row.get("session_id") or row.get("run_id") or ""),
            status=str(row.get("status") or "UNSET"),
            meta={
                "duration_ms": row.get("duration_ms"),
                "spans": row.get("total_spans") or row.get("span_count") or "",
            },
            updated_at=row.get("start_time") or row.get("created_at"),
        )
        for row in rows
    ]

    return _payload(
        module="metrics",
        title="Metrics",
        description="Agent 运行、Trace、Span、Session 与 Memory 聚合指标。",
        metrics=[
            _metric("Sessions", session_count, "Agno sessions", "blue"),
            _metric("Traces", trace_count, "Agno traces", "green"),
            _metric("Spans", span_count, "Agno spans", "yellow"),
            _metric("Errors", error_count, "ERROR traces", "red"),
            _metric("Avg Latency", f"{avg_duration:.1f} ms" if avg_duration else "-", "Trace 平均耗时", "blue"),
            _metric("Memories", memory_count, "Agno memories", "green"),
        ],
        records=records,
    )


def get_evaluation_payload(actor: Any | None = None) -> OsPayload:
    _ensure_control_tables()
    rows = _fetch_rows(app_schema(), CONTROL_TABLES["evaluation"], limit=100, order_by="updated_at")
    records = [
        _record(
            record_id=row.get("id"),
            title=str(row.get("name") or row.get("id")),
            subtitle=str(row.get("target") or ""),
            status=str(row.get("status") or "draft"),
            meta={"score": row.get("score"), **(coerce_json_value(row.get("metadata")) if isinstance(coerce_json_value(row.get("metadata")), dict) else {})},
            updated_at=row.get("updated_at"),
        )
        for row in rows
    ]
    completed = sum(1 for row in rows if row.get("status") == "completed")
    draft = sum(1 for row in rows if row.get("status") == "draft")
    return _payload(
        module="evaluation",
        title="Evaluation",
        description="评测运行登记与质量基线准备区。",
        metrics=[
            _metric("Eval Runs", len(rows), "登记的评测运行", "blue"),
            _metric("Completed", completed, "已完成评测", "green"),
            _metric("Draft", draft, "草稿评测", "yellow"),
        ],
        records=records,
    )


def get_approvals_payload(actor: Any | None = None) -> OsPayload:
    _ensure_control_tables()
    rows = _fetch_rows(app_schema(), CONTROL_TABLES["approvals"], limit=100, order_by="updated_at")
    records = [
        _record(
            record_id=row.get("id"),
            title=str(row.get("title") or row.get("id")),
            subtitle=str(row.get("action") or row.get("requester") or ""),
            status=str(row.get("status") or "pending"),
            meta={
                "requester": row.get("requester"),
                **(
                    coerce_json_value(row.get("metadata"))
                    if isinstance(coerce_json_value(row.get("metadata")), dict)
                    else {}
                ),
            },
            updated_at=row.get("updated_at"),
        )
        for row in rows
    ]
    pending = sum(1 for row in rows if row.get("status") == "pending")
    return _payload(
        module="approvals",
        title="Approvals",
        description="敏感工具调用和人工审批请求。",
        metrics=[
            _metric("Requests", len(rows), "审批请求", "blue"),
            _metric("Pending", pending, "等待处理", "red" if pending else "green"),
            _metric("Resolved", len(rows) - pending, "已处理", "green"),
        ],
        records=records,
    )


def get_scheduler_payload(actor: Any | None = None) -> OsPayload:
    return get_agno_scheduler_payload(actor=actor)


def get_knowledge_payload(actor: Any | None = None) -> OsPayload:
    docs = _count(knowledge_schema(), "agno_knowledge")
    chunks = _count(knowledge_schema(), "security_knowledge_vectors")
    records = [
        _record(
            record_id="knowledge:pgvector",
            title="PgVector Knowledge",
            subtitle="security_knowledge_vectors",
            status="ready" if chunks else "empty",
            meta={"chunks": chunks, "schema": knowledge_schema()},
        ),
        _record(
            record_id="knowledge:contents",
            title="Knowledge Contents",
            subtitle="agno_knowledge",
            status="ready" if docs else "empty",
            meta={"documents": docs, "schema": knowledge_schema()},
        ),
    ]
    return _payload(
        module="knowledge",
        title="Knowledge",
        description="知识库内容表与向量表轻量状态。",
        metrics=[
            _metric("Documents", docs, "content rows", "blue"),
            _metric("Chunks", chunks, "vector rows", "green"),
        ],
        records=records,
    )


MODULE_HANDLERS = {
    "sessions": get_sessions_payload,
    "studio": get_studio_payload,
    "memory": get_memory_payload,
    "metrics": get_metrics_payload,
    "evaluation": get_evaluation_payload,
    "approvals": get_approvals_payload,
    "scheduler": get_scheduler_payload,
    "knowledge": get_knowledge_payload,
}


def get_control_payload(module: str, actor: Any | None = None) -> OsPayload:
    try:
        handler = MODULE_HANDLERS[module]
    except KeyError as exc:
        raise ValueError(f"Unsupported control module: {module}") from exc
    return handler(actor=actor)
