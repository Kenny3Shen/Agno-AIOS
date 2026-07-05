from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Column,
    Identity,
    MetaData,
    Table,
    Text,
    delete,
    desc,
    func,
    select,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

MCP_TOKENS_TABLE = "mcp_tokens"


def _mcp_schema() -> str:
    return get_settings().agno_mcp_schema


def _metadata() -> MetaData:
    return MetaData(schema=_mcp_schema())


def mcp_tokens_table() -> Table:
    return Table(
        MCP_TOKENS_TABLE,
        _metadata(),
        Column("id", BigInteger, Identity(), primary_key=True),
        Column("name", Text, nullable=False),
        Column("token", Text, nullable=False, unique=True),
        Column("created_at", BigInteger, nullable=False),
        Column("expires_at", BigInteger, nullable=False),
    )


async def ensure_mcp_tables() -> None:
    tokens = mcp_tokens_table()
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(_mcp_schema(), if_not_exists=True))
        await conn.run_sync(tokens.create, checkfirst=True)


async def list_token_rows() -> list[dict[str, Any]]:
    await ensure_mcp_tables()
    table = mcp_tokens_table()
    stmt = select(table).order_by(desc(table.c.created_at))
    async with get_async_control_plane_engine().begin() as conn:
        return [dict(row) for row in (await conn.execute(stmt)).mappings().all()]


def _token_insert_values(record: dict[str, Any]) -> dict[str, Any]:
    values = {
        "name": record.get("name"),
        "token": record.get("token"),
        "created_at": record.get("created_at"),
        "expires_at": record.get("expires_at"),
    }
    if record.get("id") is not None:
        values["id"] = record.get("id")
    return values


async def upsert_token_row(record: dict[str, Any]) -> None:
    await ensure_mcp_tables()
    table = mcp_tokens_table()
    stmt = insert(table).values(_token_insert_values(record))
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.token],
        set_={
            "name": stmt.excluded.name,
            "created_at": stmt.excluded.created_at,
            "expires_at": stmt.excluded.expires_at,
        },
    )
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(stmt)


async def delete_token_row(token_id: int | None, token_value: str | None) -> bool:
    await ensure_mcp_tables()
    table = mcp_tokens_table()
    if token_id is not None:
        stmt = delete(table).where(table.c.id == token_id)
    elif token_value:
        stmt = delete(table).where(table.c.token == token_value)
    else:
        return False
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(stmt)
    return int(result.rowcount or 0) > 0


async def find_token_row(token: str) -> dict[str, Any] | None:
    await ensure_mcp_tables()
    table = mcp_tokens_table()
    stmt = select(table).where(table.c.token == token)
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(stmt)).mappings().first()
    return dict(row) if row is not None else None


async def reset_token_id_sequence() -> None:
    await ensure_mcp_tables()
    table = mcp_tokens_table()
    async with get_async_control_plane_engine().begin() as conn:
        max_id = (await conn.execute(select(func.max(table.c.id)))).scalar()
        await conn.execute(
            select(
                func.setval(
                    func.pg_get_serial_sequence(
                        f"{_mcp_schema()}.{MCP_TOKENS_TABLE}",
                        "id",
                    ),
                    max(int(max_id or 1), 1),
                    True,
                )
            )
        )

