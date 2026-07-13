from __future__ import annotations

from typing import Any

from sqlalchemy import BigInteger, Column, MetaData, String, Table, select, text, update
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

UPLOAD_APPROVALS_TABLE = "upload_approvals"


def _metadata() -> MetaData:
    return MetaData(schema=get_settings().agno_app_schema)


def upload_approvals_table(metadata: MetaData | None = None) -> Table:
    return Table(
        UPLOAD_APPROVALS_TABLE,
        metadata or _metadata(),
        Column("id", String(36), primary_key=True),
        Column("resource_type", String(16), nullable=False),
        Column("status", String(16), nullable=False, server_default="pending"),
        Column("submitted_by", String(255), nullable=False),
        Column("submitted_by_email", String(320), nullable=False, server_default=""),
        Column("resolved_by", String(255), nullable=True),
        Column("resolved_by_email", String(320), nullable=True),
        Column("rejection_reason", String(2000), nullable=True),
        Column("payload", JSONB, nullable=False),
        Column("created_at", BigInteger, nullable=False),
        Column("resolved_at", BigInteger, nullable=True),
        Column("updated_at", BigInteger, nullable=False),
    )


async def ensure_upload_approvals_table() -> None:
    metadata = _metadata()
    table = upload_approvals_table(metadata)
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(get_settings().agno_app_schema, if_not_exists=True))
        await conn.run_sync(table.create, checkfirst=True)
        await conn.execute(text(f'ALTER TABLE {get_settings().agno_app_schema}.{UPLOAD_APPROVALS_TABLE} ADD COLUMN IF NOT EXISTS submitted_by_email VARCHAR(320) NOT NULL DEFAULT \'\''))
        await conn.execute(text(f'ALTER TABLE {get_settings().agno_app_schema}.{UPLOAD_APPROVALS_TABLE} ADD COLUMN IF NOT EXISTS resolved_by_email VARCHAR(320)'))
        await conn.execute(text(f'ALTER TABLE {get_settings().agno_app_schema}.{UPLOAD_APPROVALS_TABLE} ADD COLUMN IF NOT EXISTS rejection_reason VARCHAR(2000)'))


async def insert_upload_approval(record: dict[str, Any]) -> dict[str, Any]:
    await ensure_upload_approvals_table()
    table = upload_approvals_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(insert(table).values(record).returning(table))).mappings().one()
    return dict(row)


async def get_upload_approval(approval_id: str) -> dict[str, Any] | None:
    await ensure_upload_approvals_table()
    table = upload_approvals_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(select(table).where(table.c.id == approval_id))).mappings().first()
    return dict(row) if row else None


async def list_upload_approvals(
    status: str | None = None, *, submitted_by: str | None = None
) -> list[dict[str, Any]]:
    await ensure_upload_approvals_table()
    table = upload_approvals_table()
    stmt = select(table).order_by(table.c.created_at.desc())
    if status:
        stmt = stmt.where(table.c.status == status)
    if submitted_by is not None:
        stmt = stmt.where(table.c.submitted_by == submitted_by)
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def resolve_upload_approval(
    approval_id: str,
    *,
    status: str,
    resolved_by: str,
    resolved_by_email: str,
    rejection_reason: str | None,
    resolved_at: int,
) -> dict[str, Any] | None:
    """Finish a claimed submission and return the resolved record."""
    await ensure_upload_approvals_table()
    table = upload_approvals_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(
                update(table)
                .where(table.c.id == approval_id, table.c.status == "resolving")
                .values(
                    status=status,
                    resolved_by=resolved_by,
                    resolved_by_email=resolved_by_email,
                    rejection_reason=rejection_reason,
                    resolved_at=resolved_at,
                    updated_at=resolved_at,
                )
                .returning(table)
            )
        ).mappings().first()
    return dict(row) if row else None


async def claim_upload_approval(
    approval_id: str, *, resolved_by: str, resolved_by_email: str, updated_at: int
) -> dict[str, Any] | None:
    """Atomically claim a pending approval before executing its side effect."""
    await ensure_upload_approvals_table()
    table = upload_approvals_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(
                update(table)
                .where(table.c.id == approval_id, table.c.status == "pending")
                .values(status="resolving", resolved_by=resolved_by, resolved_by_email=resolved_by_email, updated_at=updated_at)
                .returning(table)
            )
        ).mappings().first()
    return dict(row) if row else None


async def release_upload_approval(approval_id: str, *, updated_at: int) -> None:
    """Return a failed claim to pending so an administrator can retry or reject it."""
    await ensure_upload_approvals_table()
    table = upload_approvals_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(
            update(table)
            .where(table.c.id == approval_id, table.c.status == "resolving")
            .values(status="pending", resolved_by=None, resolved_by_email=None, updated_at=updated_at)
        )
