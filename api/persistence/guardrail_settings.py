"""Global Agno input-guardrail settings (control plane)."""

from __future__ import annotations

from time import time
from typing import Any, Mapping

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    MetaData,
    String,
    Table,
    insert,
    select,
    update,
)

from api.config import get_settings
from api.persistence.database import get_async_control_plane_engine
from api.persistence.migrations import ensure_control_plane_schema_current
from api.utils.async_once import AsyncOnce

GUARDRAIL_SETTINGS_TABLE = "guardrail_settings"
GLOBAL_GUARDRAIL_SETTINGS_ID = "global"

DEFAULT_GUARDRAIL_SETTINGS: dict[str, Any] = {
    "enabled": True,
    "pii_enabled": True,
    "pii_mask": False,
    "pii_check_email": False,
    "pii_check_phone": True,
    "prompt_injection_enabled": True,
}


def _app_schema() -> str:
    return get_settings().agno_app_schema


def guardrail_settings_table(metadata: MetaData | None = None) -> Table:
    return Table(
        GUARDRAIL_SETTINGS_TABLE,
        metadata or MetaData(schema=_app_schema()),
        Column("id", String(32), primary_key=True),
        Column("enabled", Boolean, nullable=False, server_default="true"),
        Column("pii_enabled", Boolean, nullable=False, server_default="true"),
        Column("pii_mask", Boolean, nullable=False, server_default="false"),
        Column("pii_check_email", Boolean, nullable=False, server_default="false"),
        Column("pii_check_phone", Boolean, nullable=False, server_default="true"),
        Column(
            "prompt_injection_enabled",
            Boolean,
            nullable=False,
            server_default="true",
        ),
        Column("updated_at", BigInteger, nullable=False),
    )


_table_once = AsyncOnce()


async def _create_table_async() -> None:
    await ensure_control_plane_schema_current()


async def ensure_guardrail_settings_table_async() -> None:
    await _table_once.run(_create_table_async)


def _env_defaults() -> dict[str, Any]:
    settings = get_settings()
    return {
        "enabled": bool(settings.guardrails_enabled),
        "pii_enabled": bool(settings.guardrails_pii_enabled),
        "pii_mask": bool(settings.guardrails_pii_mask),
        "pii_check_email": bool(settings.guardrails_pii_check_email),
        "pii_check_phone": bool(settings.guardrails_pii_check_phone),
        "prompt_injection_enabled": bool(settings.guardrails_prompt_injection_enabled),
    }


def _row_payload(row: Mapping[str, Any] | None = None) -> dict[str, Any]:
    defaults = _env_defaults()
    if row is None:
        return dict(defaults)
    payload = dict(defaults)
    for key in DEFAULT_GUARDRAIL_SETTINGS:
        if key in row and row[key] is not None:
            payload[key] = bool(row[key])
    return payload


async def get_guardrail_settings_row() -> dict[str, Any]:
    await ensure_guardrail_settings_table_async()
    table = guardrail_settings_table()
    defaults = _env_defaults()
    async with get_async_control_plane_engine().begin() as conn:
        row = (
            (
                await conn.execute(
                    select(table).where(table.c.id == GLOBAL_GUARDRAIL_SETTINGS_ID)
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            now = int(time())
            await conn.execute(
                insert(table).values(
                    id=GLOBAL_GUARDRAIL_SETTINGS_ID,
                    updated_at=now,
                    **defaults,
                )
            )
            return dict(defaults)
        return _row_payload(row)


async def update_guardrail_settings_row(values: Mapping[str, Any]) -> dict[str, Any]:
    await ensure_guardrail_settings_table_async()
    table = guardrail_settings_table()
    current = await get_guardrail_settings_row()
    next_values = dict(current)
    for key in DEFAULT_GUARDRAIL_SETTINGS:
        if key in values and values[key] is not None:
            next_values[key] = bool(values[key])
    now = int(time())
    async with get_async_control_plane_engine().begin() as conn:
        existing = (
            (
                await conn.execute(
                    select(table.c.id).where(table.c.id == GLOBAL_GUARDRAIL_SETTINGS_ID)
                )
            )
            .mappings()
            .first()
        )
        if existing is None:
            await conn.execute(
                insert(table).values(
                    id=GLOBAL_GUARDRAIL_SETTINGS_ID,
                    updated_at=now,
                    **next_values,
                )
            )
        else:
            await conn.execute(
                update(table)
                .where(table.c.id == GLOBAL_GUARDRAIL_SETTINGS_ID)
                .values(updated_at=now, **next_values)
            )
    return next_values
