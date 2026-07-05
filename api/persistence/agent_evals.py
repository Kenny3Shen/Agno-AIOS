from __future__ import annotations

from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Index,
    Integer,
    MetaData,
    Table,
    and_,
    Text,
    desc,
    false,
    func,
    insert,
    or_,
    select,
    text,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.schema import CreateSchema

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine

SUITES_TABLE = "agent_eval_suites"
CASES_TABLE = "agent_eval_cases"
SUITE_RUNS_TABLE = "agent_eval_suite_runs"
CASE_RUNS_TABLE = "agent_eval_case_runs"


def _app_schema() -> str:
    return get_settings().agno_app_schema


def _metadata() -> MetaData:
    return MetaData(schema=_app_schema())


def agent_eval_suites_table() -> Table:
    table = Table(
        SUITES_TABLE,
        _metadata(),
        Column("id", Text, primary_key=True),
        Column("name", Text, nullable=False),
        Column("description", Text, nullable=False, server_default=""),
        Column("target_agent_id", Text, nullable=False, server_default="security-operations"),
        Column("enabled", Boolean, nullable=False, server_default=text("true")),
        Column("tags", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
        Column("created_by", Text, nullable=False, server_default=""),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )
    Index("idx_agent_eval_suites_updated", desc(table.c.updated_at))
    return table


def agent_eval_cases_table() -> Table:
    table = Table(
        CASES_TABLE,
        _metadata(),
        Column("id", Text, primary_key=True),
        Column("suite_id", Text, nullable=False),
        Column("name", Text, nullable=False),
        Column("description", Text, nullable=False, server_default=""),
        Column("target_agent_id", Text, nullable=False, server_default="security-operations"),
        Column("input", Text, nullable=False),
        Column("expected_output", Text, nullable=False, server_default=""),
        Column("criteria", Text, nullable=False, server_default=""),
        Column("threshold", Integer, nullable=False, server_default=text("7")),
        Column("eval_types", JSONB, nullable=False, server_default=text("'[\"accuracy\"]'::jsonb")),
        Column("expected_tool_calls", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
        Column("expected_tool_call_arguments", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("allow_additional_tool_calls", Boolean, nullable=False, server_default=text("false")),
        Column("performance_config", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("enabled", Boolean, nullable=False, server_default=text("true")),
        Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column(
            "updated_at",
            DateTime(timezone=True),
            nullable=False,
            server_default=func.now(),
            onupdate=func.now(),
        ),
    )
    Index("idx_agent_eval_cases_suite", table.c.suite_id, desc(table.c.updated_at))
    Index("idx_agent_eval_cases_enabled", table.c.enabled)
    return table


def agent_eval_suite_runs_table() -> Table:
    table = Table(
        SUITE_RUNS_TABLE,
        _metadata(),
        Column("id", Text, primary_key=True),
        Column("suite_id", Text, nullable=False),
        Column("status", Text, nullable=False),
        Column("started_by", Text, nullable=False, server_default=""),
        Column("error_summary", Text, nullable=False, server_default=""),
        Column("summary", JSONB, nullable=False, server_default=text("'{}'::jsonb")),
        Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("completed_at", DateTime(timezone=True), nullable=True),
    )
    Index("idx_agent_eval_suite_runs_suite", table.c.suite_id, desc(table.c.started_at))
    Index("idx_agent_eval_suite_runs_status", table.c.status)
    return table


def agent_eval_case_runs_table() -> Table:
    table = Table(
        CASE_RUNS_TABLE,
        _metadata(),
        Column("id", Text, primary_key=True),
        Column("suite_run_id", Text, nullable=False),
        Column("case_id", Text, nullable=False),
        Column("status", Text, nullable=False),
        Column("agent_run_id", Text, nullable=False, server_default=""),
        Column("session_id", Text, nullable=False, server_default=""),
        Column("trace_id", Text, nullable=False, server_default=""),
        Column("agno_eval_run_ids", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
        Column("error_type", Text, nullable=False, server_default=""),
        Column("error_summary", Text, nullable=False, server_default=""),
        Column("replay_of_case_run_id", Text, nullable=False, server_default=""),
        Column("started_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        Column("completed_at", DateTime(timezone=True), nullable=True),
    )
    Index("idx_agent_eval_case_runs_suite_run", table.c.suite_run_id, desc(table.c.started_at))
    Index("idx_agent_eval_case_runs_case", table.c.case_id, desc(table.c.started_at))
    Index("idx_agent_eval_case_runs_status", table.c.status)
    return table


async def ensure_agent_eval_tables_async() -> None:
    tables = (
        agent_eval_suites_table(),
        agent_eval_cases_table(),
        agent_eval_suite_runs_table(),
        agent_eval_case_runs_table(),
    )
    async with get_async_control_plane_engine().begin() as conn:
        await conn.execute(CreateSchema(_app_schema(), if_not_exists=True))
        for table in tables:
            await conn.run_sync(table.create, checkfirst=True)
            for index in table.indexes:
                await conn.run_sync(index.create, checkfirst=True)


def _row_dict(row: Any) -> dict[str, Any]:
    mapping = getattr(row, "_mapping", row)
    return dict(mapping)


def _eval_run_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in values:
        eval_run_id = str(value).strip()
        if eval_run_id and eval_run_id not in seen:
            seen.add(eval_run_id)
            normalized.append(eval_run_id)
    return normalized


async def _create_row_async(table: Table, values: dict[str, Any]) -> dict[str, Any]:
    await ensure_agent_eval_tables_async()
    async with get_async_control_plane_engine().begin() as conn:
        result = await conn.execute(insert(table).values(values).returning(table))
        row = result.mappings().one()
    return _row_dict(row)


async def _list_rows_async(
    table: Table,
    filters: list[Any],
    order_by: list[Any],
) -> list[dict[str, Any]]:
    await ensure_agent_eval_tables_async()
    stmt = select(table)
    if filters:
        stmt = stmt.where(and_(*filters))
    if order_by:
        stmt = stmt.order_by(*order_by)
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(stmt)).mappings().all()
    return [_row_dict(row) for row in rows]


async def _get_row_async(table: Table, row_id: str) -> dict[str, Any] | None:
    await ensure_agent_eval_tables_async()
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(select(table).where(table.c.id == row_id))).mappings().one_or_none()
    return _row_dict(row) if row is not None else None


async def _update_row_async(table: Table, row_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    await ensure_agent_eval_tables_async()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            await conn.execute(
                update(table)
                .where(table.c.id == row_id)
                .values(values)
                .returning(table)
            )
        ).mappings().one_or_none()
    return _row_dict(row) if row is not None else None


async def create_suite_row_async(values: dict[str, Any]) -> dict[str, Any]:
    return await _create_row_async(agent_eval_suites_table(), values)


async def list_suite_rows_async(enabled: bool | None = None) -> list[dict[str, Any]]:
    table = agent_eval_suites_table()
    filters = [table.c.enabled == enabled] if enabled is not None else []
    return await _list_rows_async(table, filters, [desc(table.c.updated_at), table.c.name])


async def get_suite_row_async(suite_id: str) -> dict[str, Any] | None:
    return await _get_row_async(agent_eval_suites_table(), suite_id)


async def update_suite_row_async(suite_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    return await _update_row_async(agent_eval_suites_table(), suite_id, values)


async def create_case_row_async(values: dict[str, Any]) -> dict[str, Any]:
    return await _create_row_async(agent_eval_cases_table(), values)


async def list_case_rows_async(
    suite_id: str | None = None,
    enabled: bool | None = None,
) -> list[dict[str, Any]]:
    table = agent_eval_cases_table()
    filters = []
    if suite_id is not None:
        filters.append(table.c.suite_id == suite_id)
    if enabled is not None:
        filters.append(table.c.enabled == enabled)
    return await _list_rows_async(table, filters, [table.c.suite_id, desc(table.c.updated_at), table.c.name])


async def get_case_row_async(case_id: str) -> dict[str, Any] | None:
    return await _get_row_async(agent_eval_cases_table(), case_id)


async def update_case_row_async(case_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    return await _update_row_async(agent_eval_cases_table(), case_id, values)


async def create_suite_run_row_async(values: dict[str, Any]) -> dict[str, Any]:
    return await _create_row_async(agent_eval_suite_runs_table(), values)


async def list_suite_run_rows_async(
    suite_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    table = agent_eval_suite_runs_table()
    filters = []
    if suite_id is not None:
        filters.append(table.c.suite_id == suite_id)
    if status is not None:
        filters.append(table.c.status == status)
    return await _list_rows_async(table, filters, [desc(table.c.started_at), table.c.id])


async def get_suite_run_row_async(suite_run_id: str) -> dict[str, Any] | None:
    return await _get_row_async(agent_eval_suite_runs_table(), suite_run_id)


async def update_suite_run_row_async(suite_run_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    return await _update_row_async(agent_eval_suite_runs_table(), suite_run_id, values)


async def create_case_run_row_async(values: dict[str, Any]) -> dict[str, Any]:
    return await _create_row_async(agent_eval_case_runs_table(), values)


async def list_case_run_rows_async(
    suite_run_id: str | None = None,
    case_id: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    table = agent_eval_case_runs_table()
    filters = []
    if suite_run_id is not None:
        filters.append(table.c.suite_run_id == suite_run_id)
    if case_id is not None:
        filters.append(table.c.case_id == case_id)
    if status is not None:
        filters.append(table.c.status == status)
    return await _list_rows_async(table, filters, [desc(table.c.started_at), table.c.id])


async def get_case_run_row_async(case_run_id: str) -> dict[str, Any] | None:
    return await _get_row_async(agent_eval_case_runs_table(), case_run_id)


def case_run_by_agno_eval_run_id_statement(eval_run_id: str) -> Any:
    table = agent_eval_case_runs_table()
    return (
        select(table)
        .where(table.c.agno_eval_run_ids.contains([eval_run_id]))
        .order_by(desc(table.c.started_at), table.c.id)
        .limit(1)
    )


def case_runs_by_agno_eval_run_ids_statement(eval_run_ids: list[str]) -> Any:
    table = agent_eval_case_runs_table()
    filters = [table.c.agno_eval_run_ids.contains([eval_run_id]) for eval_run_id in _eval_run_ids(eval_run_ids)]
    condition = or_(*filters) if filters else false()
    return (
        select(table)
        .where(condition)
        .order_by(desc(table.c.started_at), table.c.id)
    )


async def get_case_run_by_agno_eval_run_id_row_async(eval_run_id: str) -> dict[str, Any] | None:
    eval_run_key = eval_run_id.strip()
    if not eval_run_key:
        return None
    await ensure_agent_eval_tables_async()
    async with get_async_control_plane_engine().begin() as conn:
        row = (await conn.execute(case_run_by_agno_eval_run_id_statement(eval_run_key))).mappings().one_or_none()
    return _row_dict(row) if row is not None else None


async def list_case_runs_by_agno_eval_run_ids_rows_async(eval_run_ids: list[str]) -> list[dict[str, Any]]:
    eval_run_keys = _eval_run_ids(eval_run_ids)
    if not eval_run_keys:
        return []
    await ensure_agent_eval_tables_async()
    async with get_async_control_plane_engine().begin() as conn:
        rows = (await conn.execute(case_runs_by_agno_eval_run_ids_statement(eval_run_keys))).mappings().all()
    return [_row_dict(row) for row in rows]


async def update_case_run_row_async(case_run_id: str, values: dict[str, Any]) -> dict[str, Any] | None:
    return await _update_row_async(agent_eval_case_runs_table(), case_run_id, values)
