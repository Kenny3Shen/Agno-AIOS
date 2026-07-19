from __future__ import annotations

import time
from collections.abc import Mapping
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
    cast,
    delete,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.ext.asyncio import AsyncConnection
from loguru import logger

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence import durable_jobs as durable_job_store
from api.persistence.durable_jobs import JobKind
from api.persistence.migrations import ensure_control_plane_schema_current
from api.utils.async_once import AsyncOnce

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


_workflows_table_once = AsyncOnce()
WORKFLOW_DEFINITION_MIGRATION_BATCH_SIZE = 100


async def _migrate_definition_columns_async(
    table: Table,
    *,
    definition_columns: tuple[str, ...],
) -> int:
    from api.services.workflow_definition_migration import (
        canonicalize_workflow_definition,
    )

    migrated_count = 0
    last_id: str | None = None
    while True:
        columns = [table.c.id, *(table.c[column] for column in definition_columns)]
        stmt = (
            select(*columns)
            .order_by(table.c.id)
            .limit(WORKFLOW_DEFINITION_MIGRATION_BATCH_SIZE)
        )
        if last_id is not None:
            stmt = stmt.where(table.c.id > last_id)
        async with get_async_control_plane_engine().begin() as conn:
            rows = [dict(row) for row in (await conn.execute(stmt)).mappings().all()]
            if not rows:
                break
            for row in rows:
                values: dict[str, Any] = {}
                for column in definition_columns:
                    original = row.get(column)
                    normalized = canonicalize_workflow_definition(original)
                    if normalized is not None and normalized != original:
                        values[column] = normalized
                if values:
                    await conn.execute(
                        update(table)
                        .where(table.c.id == row["id"])
                        .values(**values)
                    )
                    migrated_count += 1
        last_id = str(rows[-1].get("id") or "")
        if not last_id:
            break
    return migrated_count


async def _migrate_workflow_definition_aliases_async() -> None:
    await ensure_workflow_versions_table_async()
    workflow_count = await _migrate_definition_columns_async(
        workflows_table(),
        definition_columns=("definition", "published_definition"),
    )
    version_count = await _migrate_definition_columns_async(
        workflow_versions_table(),
        definition_columns=("definition",),
    )
    if workflow_count or version_count:
        logger.info(
            "canonicalized workflow definitions workflows={} versions={}",
            workflow_count,
            version_count,
        )


async def _create_workflows_table_async() -> None:
    await ensure_control_plane_schema_current()
    await _migrate_workflow_definition_aliases_async()


async def ensure_workflows_table_async() -> None:
    await _workflows_table_once.run(_create_workflows_table_async)


async def insert_workflow(record: dict[str, Any]) -> dict[str, Any]:
    await ensure_workflows_table_async()
    table = workflows_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (await conn.execute(insert(table).values(record).returning(table)))
            .mappings()
            .one()
        )
    return dict(row)


async def get_workflow(workflow_id: str) -> dict[str, Any] | None:
    await ensure_workflows_table_async()
    table = workflows_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (await conn.execute(select(table).where(table.c.id == workflow_id)))
            .mappings()
            .first()
        )
    return dict(row) if row else None


async def list_workflows(
    *,
    owner_user_id: str | None = None,
    page: int = 1,
    limit: int = 20,
    q: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    await ensure_workflows_table_async()
    table = workflows_table()
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 20), 100))
    filters = []
    if owner_user_id is not None:
        filters.append(table.c.owner_user_id == owner_user_id)
    needle = (q or "").strip()
    if needle:
        pattern = f"%{needle}%"
        filters.append(
            or_(
                table.c.name.ilike(pattern),
                table.c.description.ilike(pattern),
                table.c.id.ilike(pattern),
            )
        )
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


async def _locked_cron_triggers(
    conn: AsyncConnection,
    *,
    workflow_id: str,
    expected_last_run_at: float,
) -> dict[str, Any] | None:
    """Lock one workflow and return a mutable trigger document on a CAS match."""
    table = workflows_table()
    row = (
        (
            await conn.execute(
                select(table).where(table.c.id == workflow_id).with_for_update()
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        return None
    triggers_raw = row.get("triggers")
    triggers: dict[str, Any] = (
        {str(k): v for k, v in triggers_raw.items()}
        if isinstance(triggers_raw, dict)
        else {}
    )
    cron_raw = triggers.get("cron")
    cron: dict[str, Any] = (
        {str(k): v for k, v in cron_raw.items()}
        if isinstance(cron_raw, dict)
        else {}
    )
    current = float(cron.get("last_run_at") or 0)
    expected = float(expected_last_run_at or 0)
    # Another scheduler advanced last_run_at past our snapshot → lose claim.
    if current > expected + 0.01:
        return None
    if expected > 0 and abs(current - expected) > 0.01:
        return None
    triggers["cron"] = cron
    return triggers


async def _advance_locked_cron_last_run(
    conn: AsyncConnection,
    *,
    workflow_id: str,
    triggers: dict[str, Any],
    claim_ts: float,
) -> bool:
    """Persist a cron claim after the caller has completed its coupled write."""
    table = workflows_table()
    cron_raw = triggers.get("cron")
    cron: dict[str, Any] = (
        {str(k): v for k, v in cron_raw.items()}
        if isinstance(cron_raw, dict)
        else {}
    )
    cron["last_run_at"] = float(claim_ts)
    triggers["cron"] = cron
    result = await conn.execute(
        update(table)
        .where(table.c.id == workflow_id)
        .values(triggers=triggers, updated_at=int(claim_ts))
    )
    return bool(result.rowcount)


async def claim_cron_last_run(
    workflow_id: str,
    *,
    expected_last_run_at: float,
    claim_ts: float,
) -> bool:
    """CAS claim on triggers.cron.last_run_at (row lock) for multi-instance safety."""
    await ensure_workflows_table_async()
    async with get_async_control_plane_engine().begin() as conn:
        triggers = await _locked_cron_triggers(
            conn,
            workflow_id=workflow_id,
            expected_last_run_at=expected_last_run_at,
        )
        if triggers is None:
            return False
        return await _advance_locked_cron_last_run(
            conn,
            workflow_id=workflow_id,
            triggers=triggers,
            claim_ts=claim_ts,
        )


async def claim_cron_run_and_enqueue_job(
    workflow_id: str,
    *,
    expected_last_run_at: float,
    claim_ts: float,
    kind: JobKind | str,
    payload: Mapping[str, Any],
    idempotency_key: str,
    max_attempts: int = 5,
    priority: int = 0,
) -> bool:
    """Atomically claim a cron occurrence and enqueue its durable dispatch.

    The workflow row remains locked while the idempotent job insert and
    ``last_run_at`` update share one PostgreSQL transaction.  If queueing or
    the final update fails, the transaction rolls back and the occurrence
    remains due for the next scheduler tick.  Concurrent schedulers serialize
    on the workflow row; the durable unique key is a second idempotency guard.
    """
    await ensure_workflows_table_async()
    async with get_async_control_plane_engine().begin() as conn:
        triggers = await _locked_cron_triggers(
            conn,
            workflow_id=workflow_id,
            expected_last_run_at=expected_last_run_at,
        )
        if triggers is None:
            return False
        await durable_job_store.enqueue_job_in_transaction(
            conn,
            kind=kind,
            payload=payload,
            idempotency_key=idempotency_key,
            max_attempts=max_attempts,
            priority=priority,
        )
        return await _advance_locked_cron_last_run(
            conn,
            workflow_id=workflow_id,
            triggers=triggers,
            claim_ts=claim_ts,
        )


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


_workflow_versions_table_once = AsyncOnce()


async def _create_workflow_versions_table_async() -> None:
    await ensure_control_plane_schema_current()


async def ensure_workflow_versions_table_async() -> None:
    await _workflow_versions_table_once.run(_create_workflow_versions_table_async)


async def insert_workflow_version(record: dict[str, Any]) -> dict[str, Any]:
    await ensure_workflow_versions_table_async()
    table = workflow_versions_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (await conn.execute(insert(table).values(record).returning(table)))
            .mappings()
            .one()
        )
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


async def get_workflow_version(workflow_id: str, version: int) -> dict[str, Any] | None:
    await ensure_workflow_versions_table_async()
    table = workflow_versions_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    select(table).where(
                        table.c.workflow_id == workflow_id,
                        table.c.version == version,
                    )
                )
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None




async def list_workflows_referencing_skill_text(
    *,
    skill_name: str,
    owner_user_id: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Prefilter workflows whose definition JSON text mentions ``skill_name``.

    Callers must still walk the definition tree — this is only a bounded
    candidate filter (ILIKE on ``definition`` cast to text).
    """
    await ensure_workflows_table_async()
    table = workflows_table()
    needle = (skill_name or "").strip()
    if not needle:
        return []
    safe_limit = max(1, min(int(limit or 100), 200))
    # Coarse candidate filter; tree walk confirms real skill bindings.
    pattern = f"%{needle}%"
    filters = [cast(table.c.definition, String).ilike(pattern)]
    if owner_user_id is not None:
        filters.append(table.c.owner_user_id == owner_user_id)
    stmt = select(table).order_by(table.c.updated_at.desc()).limit(safe_limit)
    for clause in filters:
        stmt = stmt.where(clause)
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


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
