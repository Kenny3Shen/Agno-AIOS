from __future__ import annotations

from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    ForeignKey,
    Identity,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    delete,
    desc,
    func,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

MCP_TOKENS_TABLE = "mcp_tokens"
MCP_SERVERS_TABLE = "mcp_servers"
MCP_COMPONENT_OVERRIDES_TABLE = "mcp_component_overrides"


def _mcp_schema() -> str:
    return get_settings().agno_mcp_schema


def _metadata() -> MetaData:
    return MetaData(schema=_mcp_schema())


def mcp_tokens_table(metadata: MetaData | None = None) -> Table:
    return Table(
        MCP_TOKENS_TABLE,
        metadata or _metadata(),
        Column("id", BigInteger, Identity(), primary_key=True),
        Column("name", Text, nullable=False),
        Column("token", Text, nullable=False, unique=True),
        Column("created_at", BigInteger, nullable=False),
        Column("expires_at", BigInteger, nullable=False),
    )


def mcp_servers_table(metadata: MetaData | None = None) -> Table:
    return Table(
        MCP_SERVERS_TABLE,
        metadata or _metadata(),
        Column("id", BigInteger, Identity(), primary_key=True),
        Column("name", String(255), nullable=False, unique=True),
        Column("namespace", String(128), nullable=False, unique=True),
        Column("description", Text, nullable=False, server_default=""),
        Column("server_type", String(32), nullable=False),
        Column("transport", String(32), nullable=False),
        Column("enabled", Boolean, nullable=False, server_default="true"),
        Column("visibility", String(16), nullable=False, server_default="private"),
        Column("owner_user_id", String(255), nullable=False, server_default=""),
        Column("config", JSONB, nullable=False, server_default="{}"),
        Column("created_at", BigInteger, nullable=False),
        Column("updated_at", BigInteger, nullable=False),
    )


def mcp_component_overrides_table(metadata: MetaData | None = None) -> Table:
    return Table(
        MCP_COMPONENT_OVERRIDES_TABLE,
        metadata or _metadata(),
        Column("id", BigInteger, Identity(), primary_key=True),
        Column(
            "server_id",
            BigInteger,
            ForeignKey(f"{_mcp_schema()}.{MCP_SERVERS_TABLE}.id", ondelete="CASCADE"),
            nullable=False,
        ),
        Column("component_type", String(16), nullable=False),
        Column("component_name", String(255), nullable=False),
        Column("enabled", Boolean, nullable=False),
        Column("updated_at", BigInteger, nullable=False),
        UniqueConstraint(
            "server_id",
            "component_type",
            "component_name",
            name="uq_mcp_component_override",
        ),
    )


async def ensure_mcp_tables() -> None:
    metadata = _metadata()
    tables = (
        mcp_tokens_table(metadata),
        mcp_servers_table(metadata),
        mcp_component_overrides_table(metadata),
    )
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(_mcp_schema(), if_not_exists=True))
        for table in tables:
            await conn.run_sync(table.create, checkfirst=True)


async def list_server_rows() -> list[dict[str, Any]]:
    await ensure_mcp_tables()
    table = mcp_servers_table()
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(select(table).order_by(table.c.id))).mappings().all()
    return [dict(row) for row in rows]


async def get_server_row(server_id: int) -> dict[str, Any] | None:
    await ensure_mcp_tables()
    table = mcp_servers_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(select(table).where(table.c.id == server_id))).mappings().first()
    return dict(row) if row else None


async def get_server_row_by_name(name: str) -> dict[str, Any] | None:
    await ensure_mcp_tables()
    table = mcp_servers_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(select(table).where(table.c.name == name))
        ).mappings().first()
    return dict(row) if row else None


async def server_name_exists(name: str) -> bool:
    await ensure_mcp_tables()
    table = mcp_servers_table()
    async with get_async_control_plane_engine().begin() as conn:
        found = (
            await conn.execute(select(table.c.id).where(table.c.name == name).limit(1))
        ).first()
    return found is not None


async def upsert_server_row(record: dict[str, Any]) -> dict[str, Any]:
    await ensure_mcp_tables()
    table = mcp_servers_table()
    values = {key: record[key] for key in (
        "name", "namespace", "description", "server_type", "transport", "enabled",
        "visibility", "owner_user_id", "config", "created_at", "updated_at",
    ) if key in record}
    stmt = insert(table).values(values).on_conflict_do_update(
        index_elements=[table.c.name],
        set_={key: value for key, value in values.items() if key not in {"name", "created_at"}},
    ).returning(table)
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(stmt)).mappings().one()
    return dict(row)


async def insert_server_row(record: dict[str, Any]) -> dict[str, Any]:
    await ensure_mcp_tables()
    table = mcp_servers_table()
    values = {
        key: record[key]
        for key in (
            "name", "namespace", "description", "server_type", "transport", "enabled",
            "visibility", "owner_user_id", "config", "created_at", "updated_at",
        )
    }
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(insert(table).values(values).returning(table))).mappings().one()
    return dict(row)


async def update_server_row(server_id: int, values: dict[str, Any]) -> dict[str, Any] | None:
    await ensure_mcp_tables()
    table = mcp_servers_table()
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(update(table).where(table.c.id == server_id).values(**values).returning(table))).mappings().first()
    return dict(row) if row else None


async def delete_server_row(server_id: int) -> bool:
    await ensure_mcp_tables()
    table = mcp_servers_table()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(delete(table).where(table.c.id == server_id, table.c.server_type == "external"))
    return int(result.rowcount or 0) > 0


async def list_component_override_rows() -> list[dict[str, Any]]:
    await ensure_mcp_tables()
    table = mcp_component_overrides_table()
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(select(table))).mappings().all()
    return [dict(row) for row in rows]


async def upsert_component_override_row(record: dict[str, Any]) -> None:
    await ensure_mcp_tables()
    table = mcp_component_overrides_table()
    stmt = insert(table).values(record).on_conflict_do_update(
        constraint="uq_mcp_component_override",
        set_={"enabled": record["enabled"], "updated_at": record["updated_at"]},
    )
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(stmt)


async def list_token_rows() -> list[dict[str, Any]]:
    await ensure_mcp_tables()
    table = mcp_tokens_table()
    stmt = select(table).order_by(desc(table.c.created_at))
    async with get_async_control_plane_engine().begin() as conn:
        return [dict(row) for row in (await conn.execute(stmt)).mappings().all()]


def _token_insert_values(record: dict[str, Any]) -> dict[str, Any]:
    values = {key: record.get(key) for key in ("name", "token", "created_at", "expires_at")}
    if record.get("id") is not None:
        values["id"] = record["id"]
    return values


async def upsert_token_row(record: dict[str, Any]) -> None:
    await ensure_mcp_tables()
    table = mcp_tokens_table()
    stmt = insert(table).values(_token_insert_values(record))
    stmt = stmt.on_conflict_do_update(
        index_elements=[table.c.token],
        set_={"name": stmt.excluded.name, "created_at": stmt.excluded.created_at, "expires_at": stmt.excluded.expires_at},
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
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(select(table).where(table.c.token == token))).mappings().first()
    return dict(row) if row else None


async def reset_token_id_sequence() -> None:
    await ensure_mcp_tables()
    table = mcp_tokens_table()
    async with get_async_control_plane_engine().begin() as conn:
        max_id = (await conn.execute(select(func.max(table.c.id)))).scalar()
        await conn.execute(select(func.setval(func.pg_get_serial_sequence(f"{_mcp_schema()}.{MCP_TOKENS_TABLE}", "id"), max(int(max_id or 1), 1), True)))
