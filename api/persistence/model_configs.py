from __future__ import annotations

from typing import Any

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
    insert,
    select,
    text,
)
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

MODEL_CONFIGS_TABLE = "model_configs"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_app_schema())


def model_configs_table(metadata: MetaData | None = None) -> Table:
    table = Table(
        MODEL_CONFIGS_TABLE,
        metadata or _metadata(),
        Column("id", String(255), primary_key=True),
        Column("name", Text, nullable=False),
        Column("model_id", Text, nullable=False),
        Column("provider", String(64), nullable=False),
        Column("api_protocol", String(64), nullable=False),
        Column("structured_output_mode", String(32), nullable=False),
        Column("default_reasoning_effort", String(16), nullable=True),
        Column("parallel_tool_calls", Boolean, nullable=True),
        Column("live_search_enabled", Boolean, nullable=False, server_default="false"),
        Column("retries", BigInteger, nullable=False, server_default="4"),
        Column("delay_between_retries", BigInteger, nullable=False, server_default="1"),
        Column("exponential_backoff", Boolean, nullable=False, server_default="true"),
        Column("http_max_retries", BigInteger, nullable=True),
        Column("base_url", Text, nullable=False, server_default=""),
        Column("api_key", Text, nullable=False, server_default=""),
        Column("description", Text, nullable=False, server_default=""),
        Column("enabled", Boolean, nullable=False, server_default="true"),
        Column("builtin", Boolean, nullable=False, server_default="false"),
        Column("active", Boolean, nullable=False, server_default="false"),
        Column("sort_order", BigInteger, nullable=False),
        Column("created_at", BigInteger, nullable=False),
        Column("updated_at", BigInteger, nullable=False),
    )
    Index("idx_model_configs_active", table.c.active)
    Index("idx_model_configs_sort_order", table.c.sort_order)
    return table


async def ensure_model_configs_table_async() -> None:
    table = model_configs_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(_app_schema(), if_not_exists=True))
        await conn.run_sync(table.create, checkfirst=True)
        preparer = conn.dialect.identifier_preparer
        schema = preparer.quote(_app_schema())
        table_name = preparer.quote(MODEL_CONFIGS_TABLE)
        await conn.execute(
            text(
                f"ALTER TABLE {schema}.{table_name} "
                "ADD COLUMN IF NOT EXISTS default_reasoning_effort VARCHAR(16)"
            )
        )
        await conn.execute(
            text(
                f"ALTER TABLE {schema}.{table_name} "
                "ADD COLUMN IF NOT EXISTS parallel_tool_calls BOOLEAN"
            )
        )
        await conn.execute(
            text(
                f"ALTER TABLE {schema}.{table_name} "
                "ADD COLUMN IF NOT EXISTS live_search_enabled BOOLEAN NOT NULL DEFAULT false"
            )
        )
        await conn.execute(
            text(
                f"ALTER TABLE {schema}.{table_name} "
                "ADD COLUMN IF NOT EXISTS retries BIGINT NOT NULL DEFAULT 4"
            )
        )
        await conn.execute(
            text(
                f"ALTER TABLE {schema}.{table_name} "
                "ADD COLUMN IF NOT EXISTS delay_between_retries BIGINT NOT NULL DEFAULT 1"
            )
        )
        await conn.execute(
            text(
                f"ALTER TABLE {schema}.{table_name} "
                "ADD COLUMN IF NOT EXISTS exponential_backoff BOOLEAN NOT NULL DEFAULT true"
            )
        )
        await conn.execute(
            text(
                f"ALTER TABLE {schema}.{table_name} "
                "ADD COLUMN IF NOT EXISTS http_max_retries BIGINT"
            )
        )
        for index in table.indexes:
            await conn.run_sync(index.create, checkfirst=True)


async def list_model_config_rows() -> list[dict[str, Any]]:
    await ensure_model_configs_table_async()
    table = model_configs_table()
    stmt = select(table).order_by(table.c.sort_order, table.c.id)
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [dict(row) for row in rows]


async def replace_model_config_rows(rows: list[dict[str, Any]]) -> None:
    await ensure_model_configs_table_async()
    table = model_configs_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(delete(table))
        if rows:
            await conn.execute(insert(table), rows)
