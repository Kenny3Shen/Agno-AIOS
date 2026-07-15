from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Index,
    MetaData,
    String,
    Table,
    Text,
    delete,
    func,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

WORKFLOWS_TABLE = "workflows"


def _schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_schema())


def workflows_table(metadata: MetaData | None = None) -> Table:
    table = Table(
        WORKFLOWS_TABLE,
        metadata or _metadata(),
        Column("id", String(36), primary_key=True),
        Column("name", Text, nullable=False),
        Column("description", Text, nullable=False, server_default=""),
        Column("owner_user_id", String(255), nullable=False),
        Column("definition", JSONB, nullable=False),
        Column("triggers", JSONB, nullable=False, server_default="{}"),
        Column("enabled", Boolean, nullable=False, server_default="true"),
        Column("version", BigInteger, nullable=False, server_default="1"),
        Column("published_definition", JSONB, nullable=True),
        Column("published_version", BigInteger, nullable=True),
        Column("published_at", BigInteger, nullable=True),
        Column("created_at", BigInteger, nullable=False),
        Column("updated_at", BigInteger, nullable=False),
    )
    Index("idx_workflows_owner", table.c.owner_user_id)
    Index("idx_workflows_updated", table.c.updated_at)
    return table


async def ensure_workflows_table_async() -> None:
    table = workflows_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(_schema(), if_not_exists=True))
        await conn.run_sync(table.create, checkfirst=True)
    # Best-effort schema evolution for PR4 triggers JSONB.
    schema = _schema()
    ddl = (
        f'ALTER TABLE "{schema}"."{WORKFLOWS_TABLE}" '
        "ADD COLUMN IF NOT EXISTS triggers JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    try:
        async with get_async_control_plane_engine().begin() as conn:
            await conn.execute(text(ddl))
    except Exception:
        pass
    for extra_ddl in (
        f'ALTER TABLE "{schema}"."{WORKFLOWS_TABLE}" '
        "ADD COLUMN IF NOT EXISTS published_definition JSONB",
        f'ALTER TABLE "{schema}"."{WORKFLOWS_TABLE}" '
        "ADD COLUMN IF NOT EXISTS published_version BIGINT",
        f'ALTER TABLE "{schema}"."{WORKFLOWS_TABLE}" '
        "ADD COLUMN IF NOT EXISTS published_at BIGINT",
    ):
        try:
            async with get_async_control_plane_engine().begin() as conn:
                await conn.execute(text(extra_ddl))
        except Exception:
            pass


async def insert_workflow(record: dict[str, Any]) -> dict[str, Any]:
    await ensure_workflows_table_async()
    table = workflows_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(insert(table).values(record).returning(table))
        ).mappings().one()
    return dict(row)


async def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    await ensure_workflows_table_async()
    table = workflows_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(select(table).where(table.c.id == workflow_id))
        ).mappings().first()
    return dict(row) if row else None


async def list_workflows(
    *,
    owner_user_id: str | None = None,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    await ensure_workflows_table_async()
    table = workflows_table()
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 20), 100))
    filters = []
    if owner_user_id is not None:
        filters.append(table.c.owner_user_id == owner_user_id)
    count_stmt = select(func.count()).select_from(table)
    list_stmt = select(table).order_by(table.c.updated_at.desc())
    for clause in filters:
        count_stmt = count_stmt.where(clause)
        list_stmt = list_stmt.where(clause)
    list_stmt = list_stmt.limit(safe_limit).offset((safe_page - 1) * safe_limit)
    async with get_async_control_plane_engine().begin() as conn:
        total = int((await conn.execute(count_stmt)).scalar_one())
        rows = (await conn.execute(list_stmt)).mappings().all()
    return [dict(row) for row in rows], total


async def update_workflow(
    workflow_id: str,
    *,
    owner_user_id: str | None = None,
    values: dict[str, Any],
) -> dict[str, Any] | None:
    await ensure_workflows_table_async()
    table = workflows_table()
    stmt = update(table).where(table.c.id == workflow_id)
    if owner_user_id is not None:
        stmt = stmt.where(table.c.owner_user_id == owner_user_id)
    stmt = stmt.values(**values).returning(table)
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(stmt)).mappings().first()
    return dict(row) if row else None



async def claim_cron_last_run(
    workflow_id: str,
    *,
    expected_last_run_at: float,
    claim_ts: float,
) -> bool:
    """CAS claim on triggers.cron.last_run_at (row lock) for multi-instance safety."""
    await ensure_workflows_table_async()
    table = workflows_table()
    expected = float(expected_last_run_at or 0)
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(
                select(table).where(table.c.id == workflow_id).with_for_update()
            )
        ).mappings().first()
        if row is None:
            return False
        triggers_raw = row.get("triggers")
        triggers: dict[str, Any] = (
            {str(k): v for k, v in triggers_raw.items()}
            if isinstance(triggers_raw, dict)
            else {}
        )
        cron_raw = triggers.get("cron")
        cron: dict[str, Any] = (
            {str(k): v for k, v in cron_raw.items()} if isinstance(cron_raw, dict) else {}
        )
        current = float(cron.get("last_run_at") or 0)
        # Another worker advanced last_run_at past our snapshot → lose claim.
        if current > expected + 0.01:
            return False
        if expected > 0 and abs(current - expected) > 0.01:
            return False
        cron["last_run_at"] = float(claim_ts)
        triggers["cron"] = cron
        result = await conn.execute(
            update(table)
            .where(table.c.id == workflow_id)
            .values(triggers=triggers, updated_at=int(claim_ts))
        )
        return bool(result.rowcount)


async def delete_workflow(
    workflow_id: str,
    *,
    owner_user_id: str | None = None,
) -> bool:
    await ensure_workflows_table_async()
    table = workflows_table()
    stmt = delete(table).where(table.c.id == workflow_id)
    if owner_user_id is not None:
        stmt = stmt.where(table.c.owner_user_id == owner_user_id)
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(stmt)
    return bool(result.rowcount)


def new_workflow_id() -> str:
    return str(uuid4())


def now_ts() -> int:
    return int(time.time())


WORKFLOW_VERSIONS_TABLE = "workflow_versions"


def workflow_versions_table(metadata: MetaData | None = None) -> Table:
    table = Table(
        WORKFLOW_VERSIONS_TABLE,
        metadata or _metadata(),
        Column("id", String(36), primary_key=True),
        Column("workflow_id", String(36), nullable=False, index=True),
        Column("version", BigInteger, nullable=False),
        Column("name", Text, nullable=False),
        Column("description", Text, nullable=False, server_default=""),
        Column("definition", JSONB, nullable=False),
        Column("triggers", JSONB, nullable=False, server_default="{}"),
        Column("created_at", BigInteger, nullable=False),
        Column("created_by", String(255), nullable=False, server_default=""),
    )
    Index("idx_workflow_versions_wf", table.c.workflow_id, table.c.version)
    return table


async def ensure_workflow_versions_table_async() -> None:
    table = workflow_versions_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(_schema(), if_not_exists=True))
        await conn.run_sync(table.create, checkfirst=True)


async def insert_workflow_version(record: dict[str, Any]) -> dict[str, Any]:
    await ensure_workflow_versions_table_async()
    table = workflow_versions_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(insert(table).values(record).returning(table))
        ).mappings().one()
    return dict(row)


async def list_workflow_versions(
    workflow_id: str,
    *,
    page: int = 1,
    limit: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    await ensure_workflow_versions_table_async()
    table = workflow_versions_table()
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 20), 100))
    count_stmt = (
        select(func.count())
        .select_from(table)
        .where(table.c.workflow_id == workflow_id)
    )
    list_stmt = (
        select(table)
        .where(table.c.workflow_id == workflow_id)
        .order_by(table.c.version.desc())
        .limit(safe_limit)
        .offset((safe_page - 1) * safe_limit)
    )
    async with get_async_control_plane_engine().begin() as conn:
        total = int((await conn.execute(count_stmt)).scalar_one())
        rows = (await conn.execute(list_stmt)).mappings().all()
    return [dict(row) for row in rows], total


async def get_workflow_version(
    workflow_id: str, version: int
) -> dict[str, Any] | None:
    await ensure_workflow_versions_table_async()
    table = workflow_versions_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(
                select(table).where(
                    table.c.workflow_id == workflow_id,
                    table.c.version == version,
                )
            )
        ).mappings().first()
    return dict(row) if row else None


async def list_workflows_for_cron(*, limit: int = 200) -> list[dict[str, Any]]:
    """Return enabled workflows that may have cron triggers (filter in service)."""
    await ensure_workflows_table_async()
    table = workflows_table()
    safe_limit = max(1, min(int(limit or 200), 500))
    stmt = (
        select(table)
        .where(table.c.enabled.is_(True))
        .order_by(table.c.updated_at.desc())
        .limit(safe_limit)
    )
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]
