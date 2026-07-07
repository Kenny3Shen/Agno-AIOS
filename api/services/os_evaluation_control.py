from __future__ import annotations

from typing import Any

from sqlalchemy import Column, DateTime, Float, MetaData, Table, Text, desc, func, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateSchema

from api.persistence.database import get_async_control_plane_engine
from api.services.os_control_payloads import OsPayload, metric, payload, record
from api.services.postgres_store import app_schema, coerce_json_value

CONTROL_TABLES = {
    "evaluation": "os_eval_runs",
}


def _metadata(schema_name: str) -> MetaData:
    return MetaData(schema=schema_name)


def _evaluation_table() -> Table:
    return Table(
        CONTROL_TABLES["evaluation"],
        _metadata(app_schema()),
        Column("id", Text, primary_key=True),
        Column("name", Text, nullable=False),
        Column("target", Text, nullable=False, server_default=""),
        Column("status", Text, nullable=False, server_default="draft"),
        Column("score", Float),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
    )


async def _ensure_control_tables() -> None:
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(app_schema(), if_not_exists=True))
        await conn.run_sync(_evaluation_table().create, checkfirst=True)


async def _fetch_control_rows(table: Table, *, limit: int = 100) -> list[dict[str, Any]]:
    await _ensure_control_tables()
    stmt = select(table).order_by(desc(table.c.updated_at)).limit(limit)
    async with get_async_control_plane_engine().begin() as conn:
        return [dict(row) for row in (await conn.execute(stmt)).mappings().all()]


async def get_evaluation_payload(actor: Any | None = None) -> OsPayload:
    del actor
    rows = await _fetch_control_rows(_evaluation_table(), limit=100)
    records = [
        record(
            record_id=row.get("id"),
            title=str(row.get("name") or row.get("id")),
            subtitle=str(row.get("target") or ""),
            status=str(row.get("status") or "draft"),
            meta={
                "score": row.get("score"),
                **(coerce_json_value(row.get("metadata")) if isinstance(coerce_json_value(row.get("metadata")), dict) else {}),
            },
            updated_at=row.get("updated_at"),
        )
        for row in rows
    ]
    completed = sum(1 for row in rows if row.get("status") == "completed")
    draft = sum(1 for row in rows if row.get("status") == "draft")
    return payload(
        module="evaluation",
        title="Evaluation",
        description="评测运行登记与质量基线准备区。",
        metrics=[
            metric("Eval Runs", len(rows), "登记的评测运行", "blue"),
            metric("Completed", completed, "已完成评测", "green"),
            metric("Draft", draft, "草稿评测", "yellow"),
        ],
        records=records,
    )
