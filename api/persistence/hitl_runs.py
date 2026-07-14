"""Persistence for resumable chat runs paused by a required approval."""

from __future__ import annotations

from typing import Any

from datetime import timedelta

from sqlalchemy import Column, DateTime, MetaData, Table, Text, and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

HITL_RUNS_TABLE = "hitl_paused_runs"
DEFAULT_RESUME_STALE_SECONDS = 300


def _metadata() -> MetaData:
    return MetaData(schema=get_settings().agno_app_schema)


def hitl_runs_table() -> Table:
    return Table(
        HITL_RUNS_TABLE,
        _metadata(),
        Column("approval_id", Text, primary_key=True),
        Column("run_id", Text, nullable=False, unique=True),
        Column("session_id", Text, nullable=False),
        Column("user_id", Text, nullable=False),
        Column("request_context", JSONB, nullable=False),
        Column("resume_status", Text, nullable=False, server_default="pending"),
        Column("resume_error", Text, nullable=False, server_default=""),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    )


async def ensure_hitl_runs_table_async() -> None:
    table = hitl_runs_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(get_settings().agno_app_schema, if_not_exists=True))
        await conn.run_sync(table.create, checkfirst=True)


async def save_paused_run(record: dict[str, Any]) -> None:
    await ensure_hitl_runs_table_async()
    table = hitl_runs_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(
            insert(table)
            .values(**record)
            .on_conflict_do_nothing(index_elements=[table.c.approval_id])
        )


async def get_paused_run(approval_id: str) -> dict[str, Any] | None:
    await ensure_hitl_runs_table_async()
    table = hitl_runs_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(select(table).where(table.c.approval_id == approval_id))).mappings().first()
    return dict(row) if row else None


async def set_resume_status(approval_id: str, status: str, error: str = "") -> bool:
    await ensure_hitl_runs_table_async()
    table = hitl_runs_table()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(
            update(table)
            .where(table.c.approval_id == approval_id)
            .values(resume_status=status, resume_error=error, updated_at=func.now())
        )
    return bool(result.rowcount)


async def has_paused_run(approval_id: str) -> bool:
    return await get_paused_run(approval_id) is not None


async def claim_resume(
    approval_id: str,
    *,
    stale_after_seconds: int = DEFAULT_RESUME_STALE_SECONDS,
) -> bool:
    """Atomically claim a paused run for resume.

    Succeeds when the row is ``pending``/``failed``, or ``running`` but stale
    (crash recovery). Returns False when another worker holds a fresh claim
    or the row is missing / already completed.
    """
    await ensure_hitl_runs_table_async()
    table = hitl_runs_table()
    safe_stale = max(1, int(stale_after_seconds))
    stale_before = func.now() - timedelta(seconds=safe_stale)
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(
            update(table)
            .where(
                and_(
                    table.c.approval_id == approval_id,
                    or_(
                        table.c.resume_status.in_(("pending", "failed")),
                        and_(
                            table.c.resume_status == "running",
                            table.c.updated_at < stale_before,
                        ),
                    ),
                )
            )
            .values(resume_status="running", resume_error="", updated_at=func.now())
        )
    return bool(result.rowcount)
