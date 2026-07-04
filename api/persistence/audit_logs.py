from __future__ import annotations

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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_control_plane_engine

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
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    )
    Index(
        "idx_audit_logs_actor_time",
        table.c.actor_user_id,
        desc(table.c.created_at),
    )
    Index(
        "idx_audit_logs_action_time",
        table.c.action,
        desc(table.c.created_at),
    )
    return table


def ensure_audit_logs_table() -> None:
    table = audit_logs_table()
    with get_control_plane_engine().begin() as conn:
        conn.execute(CreateSchema(_app_schema(), if_not_exists=True))
        table.create(conn, checkfirst=True)
        for index in table.indexes:
            index.create(conn, checkfirst=True)


def insert_audit_log(
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
    ensure_audit_logs_table()
    table = audit_logs_table()
    with get_control_plane_engine().begin() as conn:
        conn.execute(
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


def list_audit_logs(
    *,
    page: int,
    limit: int,
    actor_user_id: str | None = None,
    action: str | None = None,
    resource_type: str | None = None,
    status: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    ensure_audit_logs_table()
    safe_page = max(1, page)
    safe_limit = min(200, max(1, limit))
    offset = (safe_page - 1) * safe_limit
    table = audit_logs_table()

    filters = []
    for column, value in (
        (table.c.actor_user_id, actor_user_id),
        (table.c.action, action),
        (table.c.resource_type, resource_type),
        (table.c.status, status),
    ):
        text = (value or "").strip()
        if text:
            filters.append(column == text)

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

    with get_control_plane_engine().begin() as conn:
        total = int(conn.execute(count_stmt).scalar_one())
        rows = [dict(row) for row in conn.execute(rows_stmt).mappings().all()]

    return rows, total
