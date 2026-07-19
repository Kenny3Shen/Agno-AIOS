from __future__ import annotations

from api.utils.async_once import AsyncOnce

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Index,
    MetaData,
    Table,
    Text,
    and_,
    desc,
    func,
    insert,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current

AUDIT_LOGS_TABLE = "audit_logs"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_app_schema())


def audit_logs_table() -> Table:
    table = Table(
        AUDIT_LOGS_TABLE,
        _metadata(),
        Column("id", BigInteger, primary_key=True, autoincrement=True),
        Column("actor_user_id", Text, nullable=False),
        Column("actor_email", Text, nullable=False, server_default=""),
        Column("actor_role", Text, nullable=False),
        Column("action", Text, nullable=False),
        Column("resource_type", Text, nullable=False),
        Column("resource_id", Text, nullable=False, server_default=""),
        Column("status", Text, nullable=False, server_default="success"),
        Column("ip_address", Text, nullable=False, server_default=""),
        Column("user_agent", Text, nullable=False, server_default=""),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column(
            "created_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
        ),
    )
    Index(
        "idx_audit_logs_actor_time",
        table.c.actor_user_id,
        desc(table.c.created_at),
    )
    Index(
        "idx_audit_logs_email_time",
        table.c.actor_email,
        desc(table.c.created_at),
    )
    Index(
        "idx_audit_logs_action_time",
        table.c.action,
        desc(table.c.created_at),
    )
    Index(
        "idx_audit_logs_resource_type_time",
        table.c.resource_type,
        desc(table.c.created_at),
    )
    Index(
        "idx_audit_logs_resource_id_time",
        table.c.resource_id,
        desc(table.c.created_at),
    )
    Index(
        "idx_audit_logs_status_time",
        table.c.status,
        desc(table.c.created_at),
    )
    Index(
        "idx_audit_logs_ip_time",
        table.c.ip_address,
        desc(table.c.created_at),
    )
    Index("idx_audit_logs_created_time", desc(table.c.created_at))
    return table


_audit_logs_table_once = AsyncOnce()


async def _create_audit_logs_table_async() -> None:
    await ensure_control_plane_schema_current()


async def ensure_audit_logs_table_async() -> None:
    await _audit_logs_table_once.run(_create_audit_logs_table_async)


async def insert_audit_log_async(
    *,
    actor_user_id: str,
    actor_email: str,
    actor_role: str,
    action: str,
    resource_type: str,
    resource_id: str,
    status: str,
    ip_address: str,
    user_agent: str,
    metadata: dict[str, Any],
) -> None:
    await ensure_audit_logs_table_async()
    table = audit_logs_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(
            insert(table).values(
                actor_user_id=actor_user_id,
                actor_email=actor_email,
                actor_role=actor_role,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                status=status,
                ip_address=ip_address,
                user_agent=user_agent,
                metadata=metadata,
            )
        )


async def list_audit_logs_async(
    *,
    page: int,
    limit: int,
    actor_user_id: str | None = None,
    actor_email: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str | None = None,
    ip_address: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> tuple[list[dict[str, Any]], int]:
    await ensure_audit_logs_table_async()
    safe_page = max(1, page)
    safe_limit = min(200, max(1, limit))
    offset = (safe_page - 1) * safe_limit
    table = audit_logs_table()

    filters = []
    for column, value in (
        (table.c.actor_user_id, actor_user_id),
        (table.c.actor_email, actor_email),
        (table.c.action, action),
        (table.c.resource_type, resource_type),
        (table.c.resource_id, resource_id),
        (table.c.status, status),
        (table.c.ip_address, ip_address),
    ):
        text = (value or "").strip()
        if text:
            filters.append(column == text)
    if created_from is not None:
        filters.append(table.c.created_at >= created_from)
    if created_to is not None:
        filters.append(table.c.created_at <= created_to)

    where_clause = and_(*filters) if filters else None
    count_stmt = select(func.count()).select_from(table)
    rows_stmt = (
        select(table)
        .order_by(desc(table.c.created_at), desc(table.c.id))
        .limit(safe_limit)
        .offset(offset)
    )
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
        rows_stmt = rows_stmt.where(where_clause)

    async with get_async_control_plane_engine().begin() as conn:
        total = int((await conn.execute(count_stmt)).scalar_one())
        rows = [dict(row) for row in (await conn.execute(rows_stmt)).mappings().all()]

    return rows, total


async def failed_chat_run_ids_async(
    run_ids: set[str],
    *,
    actor_user_id: str | None = None,
) -> set[str]:
    """Return failed chat Run IDs from the audit terminal records."""
    clean_run_ids = {run_id.strip() for run_id in run_ids if run_id.strip()}
    if not clean_run_ids:
        return set()
    await ensure_audit_logs_table_async()
    table = audit_logs_table()
    filters = [
        table.c.action == "chat.run",
        table.c.resource_type == "chat_run",
        table.c.status == "error",
        table.c.resource_id.in_(clean_run_ids),
    ]
    if actor_user_id:
        filters.append(table.c.actor_user_id == actor_user_id)
    stmt = select(table.c.resource_id).distinct().where(and_(*filters))
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).scalars().all()
    return {str(run_id) for run_id in rows if run_id}


async def recent_failed_chat_run_ids_async(
    *,
    limit: int = 50,
    actor_user_id: str | None = None,
) -> list[str]:
    """Return recent failed chat run IDs (newest first) for ERROR list supplements."""
    await ensure_audit_logs_table_async()
    table = audit_logs_table()
    safe_limit = max(1, min(int(limit or 50), 200))
    filters = [
        table.c.action == "chat.run",
        table.c.resource_type == "chat_run",
        table.c.status == "error",
    ]
    if actor_user_id:
        filters.append(table.c.actor_user_id == actor_user_id)
    stmt = (
        select(table.c.resource_id)
        .where(and_(*filters))
        .order_by(desc(table.c.created_at), desc(table.c.id))
        .limit(safe_limit)
    )
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).scalars().all()
    seen: set[str] = set()
    ordered: list[str] = []
    for run_id in rows:
        value = str(run_id or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


async def repair_failed_chat_trace_statuses_async(
    traces_table: Table,
    *,
    apply: bool,
) -> dict[str, int]:
    """Reconcile persisted Trace status with failed chat audit terminals."""
    await ensure_audit_logs_table_async()
    audit_table = audit_logs_table()
    failed_ids = (
        select(audit_table.c.resource_id)
        .distinct()
        .where(
            audit_table.c.action == "chat.run",
            audit_table.c.resource_type == "chat_run",
            audit_table.c.status == "error",
            audit_table.c.resource_id != "",
        )
    )
    candidate_filter = and_(
        traces_table.c.run_id.in_(failed_ids),
        func.upper(traces_table.c.status).in_(["OK", "UNSET"]),
    )
    matched_failed_ids = select(traces_table.c.run_id).where(
        traces_table.c.run_id.in_(failed_ids)
    )
    async with get_async_control_plane_engine().begin() as conn:
        failed_count = int(
            (
                await conn.execute(
                    select(func.count()).select_from(failed_ids.subquery())
                )
            ).scalar_one()
        )
        matched_count = int(
            (
                await conn.execute(
                    select(func.count()).select_from(
                        matched_failed_ids.distinct().subquery()
                    )
                )
            ).scalar_one()
        )
        candidate_count = int(
            (
                await conn.execute(
                    select(func.count())
                    .select_from(traces_table)
                    .where(candidate_filter)
                )
            ).scalar_one()
        )
        updated_count = 0
        if apply and candidate_count:
            result = await conn.execute(
                update(traces_table).where(candidate_filter).values(status="ERROR")
            )
            updated_count = int(result.rowcount or 0)
    return {
        "failed_audit_runs": failed_count,
        "candidate_traces": candidate_count,
        "updated_traces": updated_count,
        "unmatched_audit_runs": max(0, failed_count - matched_count),
    }
