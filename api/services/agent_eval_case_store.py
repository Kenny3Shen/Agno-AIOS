from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from api.auth.claims import actor_id
from api.utils.pagination import pagination_meta
from api.persistence.agent_evals import (
    create_case_row_async,
    create_case_run_row_async,
    create_suite_row_async,
    create_suite_run_row_async,
    get_case_row_async,
    get_case_run_by_agno_eval_run_id_row_async,
    get_case_run_row_async,
    get_suite_row_async,
    list_case_rows_async,
    list_case_runs_by_agno_eval_run_ids_rows_async,
    list_case_run_rows_async,
    list_suite_rows_async,
    list_suite_run_rows_async,
    update_case_row_async,
    update_case_run_row_async,
    update_suite_row_async,
    update_suite_run_row_async,
)

SUPPORTED_EVAL_TYPES = {"accuracy", "agent_as_judge", "reliability", "performance"}


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return dict(mapping)
    return dict(vars(row))


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    return value


def _string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _dict_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _json_value(item) for key, item in value.items()}


def _eval_types(value: Any) -> list[str]:
    types = _string_list(value) or ["accuracy"]
    unsupported = sorted(set(types) - SUPPORTED_EVAL_TYPES)
    if unsupported:
        raise ValueError(f"Unsupported eval type: {', '.join(unsupported)}")
    return types


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _completed_at(status: str) -> datetime | None:
    if status in {"passed", "failed", "error", "cancelled", "completed"}:
        return datetime.now(UTC)
    return None


def _normalize_status(status: Any, default: str = "queued") -> str:
    text = _string(status, default).strip()
    return text or default


def _require_text(payload: dict[str, Any], key: str) -> str:
    value = _string(payload.get(key)).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _filter_update(payload: dict[str, Any], handlers: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, handler in handlers.items():
        if key in payload:
            values[key] = handler(payload[key])
    if not values:
        raise ValueError("No supported fields to update")
    return values


def _project_update(payload: dict[str, Any], handlers: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, handler in handlers.items():
        if key in payload:
            values[key] = handler(payload[key])
    return values


def normalize_suite(row: Any) -> dict[str, Any]:
    data = _row_dict(row)
    return {
        "id": _string(data.get("id")),
        "name": _string(data.get("name")),
        "description": _string(data.get("description")),
        "target_agent_id": _string(data.get("target_agent_id"), "security-operations"),
        "enabled": _bool(data.get("enabled"), True),
        "tags": _string_list(data.get("tags")),
        "created_by": _string(data.get("created_by")),
        "created_at": _json_value(data.get("created_at")),
        "updated_at": _json_value(data.get("updated_at")),
    }


def normalize_case(row: Any) -> dict[str, Any]:
    data = _row_dict(row)
    return {
        "id": _string(data.get("id")),
        "suite_id": _string(data.get("suite_id")),
        "name": _string(data.get("name")),
        "description": _string(data.get("description")),
        "target_agent_id": _string(data.get("target_agent_id"), "security-operations"),
        "input": _string(data.get("input")),
        "expected_output": _string(data.get("expected_output")),
        "criteria": _string(data.get("criteria")),
        "threshold": _int(data.get("threshold"), 7),
        "eval_types": _eval_types(data.get("eval_types")),
        "expected_tool_calls": _string_list(data.get("expected_tool_calls")),
        "expected_tool_call_arguments": _dict_value(data.get("expected_tool_call_arguments")),
        "allow_additional_tool_calls": _bool(data.get("allow_additional_tool_calls"), False),
        "performance_config": _dict_value(data.get("performance_config")),
        "metadata": _dict_value(data.get("metadata")),
        "enabled": _bool(data.get("enabled"), True),
        "created_at": _json_value(data.get("created_at")),
        "updated_at": _json_value(data.get("updated_at")),
    }


def normalize_suite_run(row: Any) -> dict[str, Any]:
    data = _row_dict(row)
    return {
        "id": _string(data.get("id")),
        "suite_id": _string(data.get("suite_id")),
        "status": _string(data.get("status")),
        "started_by": _string(data.get("started_by")),
        "error_summary": _string(data.get("error_summary")),
        "summary": _dict_value(data.get("summary")),
        "started_at": _json_value(data.get("started_at")),
        "completed_at": _json_value(data.get("completed_at")),
    }


def normalize_case_run(row: Any) -> dict[str, Any]:
    data = _row_dict(row)
    return {
        "id": _string(data.get("id")),
        "suite_run_id": _string(data.get("suite_run_id")),
        "case_id": _string(data.get("case_id")),
        "status": _string(data.get("status")),
        "agent_run_id": _string(data.get("agent_run_id")),
        "session_id": _string(data.get("session_id")),
        "trace_id": _string(data.get("trace_id")),
        "agno_eval_run_ids": _string_list(data.get("agno_eval_run_ids")),
        "error_type": _string(data.get("error_type")),
        "error_summary": _string(data.get("error_summary")),
        "replay_of_case_run_id": _string(data.get("replay_of_case_run_id")),
        "started_at": _json_value(data.get("started_at")),
        "completed_at": _json_value(data.get("completed_at")),
    }


async def create_suite(payload: dict[str, Any], actor: Any) -> dict[str, Any]:
    values = {
        "id": uuid4().hex,
        "name": _require_text(payload, "name"),
        "description": _string(payload.get("description")),
        "target_agent_id": _string(payload.get("target_agent_id"), "security-operations"),
        "enabled": _bool(payload.get("enabled"), True),
        "tags": _string_list(payload.get("tags")),
        "created_by": actor_id(actor),
    }
    row = await create_suite_row_async(values=values)
    return normalize_suite(row)


async def list_suites(enabled: bool | None = None) -> list[dict[str, Any]]:
    rows = await list_suite_rows_async(enabled=enabled)
    return [normalize_suite(row) for row in rows]


async def get_suite(suite_id: str) -> dict[str, Any] | None:
    row = await get_suite_row_async(suite_id)
    return normalize_suite(row) if row is not None else None


async def update_suite(suite_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    values = _filter_update(
        payload,
        {
            "name": lambda value: _string(value).strip(),
            "description": _string,
            "target_agent_id": lambda value: _string(value, "security-operations"),
            "enabled": lambda value: _bool(value, True),
            "tags": _string_list,
        },
    )
    row = await update_suite_row_async(suite_id, values)
    return normalize_suite(row) if row is not None else None


async def create_case(payload: dict[str, Any]) -> dict[str, Any]:
    values = {
        "id": uuid4().hex,
        "suite_id": _require_text(payload, "suite_id"),
        "name": _require_text(payload, "name"),
        "description": _string(payload.get("description")),
        "target_agent_id": _string(payload.get("target_agent_id"), "security-operations"),
        "input": _require_text(payload, "input"),
        "expected_output": _string(payload.get("expected_output")),
        "criteria": _string(payload.get("criteria")),
        "threshold": _int(payload.get("threshold"), 7),
        "eval_types": _eval_types(payload.get("eval_types")),
        "expected_tool_calls": _string_list(payload.get("expected_tool_calls")),
        "expected_tool_call_arguments": _dict_value(payload.get("expected_tool_call_arguments")),
        "allow_additional_tool_calls": _bool(payload.get("allow_additional_tool_calls"), False),
        "performance_config": _dict_value(payload.get("performance_config")),
        "metadata": _dict_value(payload.get("metadata")),
        "enabled": _bool(payload.get("enabled"), True),
    }
    row = await create_case_row_async(values=values)
    return normalize_case(row)


async def list_cases(suite_id: str | None = None, enabled: bool | None = None) -> list[dict[str, Any]]:
    rows = await list_case_rows_async(suite_id=suite_id, enabled=enabled)
    return [normalize_case(row) for row in rows]


async def get_case(case_id: str) -> dict[str, Any] | None:
    row = await get_case_row_async(case_id)
    return normalize_case(row) if row is not None else None


async def update_case(case_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    values = _filter_update(
        payload,
        {
            "suite_id": lambda value: _string(value).strip(),
            "name": lambda value: _string(value).strip(),
            "description": _string,
            "target_agent_id": lambda value: _string(value, "security-operations"),
            "input": _string,
            "expected_output": _string,
            "criteria": _string,
            "threshold": lambda value: _int(value, 7),
            "eval_types": _eval_types,
            "expected_tool_calls": _string_list,
            "expected_tool_call_arguments": _dict_value,
            "allow_additional_tool_calls": lambda value: _bool(value, False),
            "performance_config": _dict_value,
            "metadata": _dict_value,
            "enabled": lambda value: _bool(value, True),
        },
    )
    row = await update_case_row_async(case_id, values)
    return normalize_case(row) if row is not None else None


async def create_suite_run(suite_id: str, actor: Any) -> dict[str, Any]:
    values = {
        "id": uuid4().hex,
        "suite_id": suite_id,
        "status": "queued",
        "started_by": actor_id(actor),
        "error_summary": "",
        "summary": {},
    }
    row = await create_suite_run_row_async(values=values)
    return normalize_suite_run(row)


async def list_suite_runs(
    suite_id: str | None = None,
    status: str | None = None,
    *,
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    """Agno-style ``{data, meta}`` for suite run history."""
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 50), 100))
    rows, total = await list_suite_run_rows_async(
        suite_id=suite_id,
        status=status,
        page=safe_page,
        limit=safe_limit,
    )
    return {
        "data": [normalize_suite_run(row) for row in rows],
        "meta": pagination_meta(page=safe_page, limit=safe_limit, total_count=total),
    }


async def create_case_run(
    case_id: str,
    suite_run_id: str | None = None,
    replay_of_case_run_id: str | None = None,
) -> dict[str, Any]:
    values = {
        "id": uuid4().hex,
        "suite_run_id": suite_run_id or "",
        "case_id": case_id,
        "status": "queued",
        "agent_run_id": "",
        "session_id": "",
        "trace_id": "",
        "agno_eval_run_ids": [],
        "error_type": "",
        "error_summary": "",
        "replay_of_case_run_id": replay_of_case_run_id or "",
    }
    row = await create_case_run_row_async(values=values)
    return normalize_case_run(row)


async def get_case_run(case_run_id: str) -> dict[str, Any] | None:
    row = await get_case_run_row_async(case_run_id)
    return normalize_case_run(row) if row is not None else None


async def get_case_run_by_agno_eval_run_id(eval_run_id: str) -> dict[str, Any] | None:
    row = await get_case_run_by_agno_eval_run_id_row_async(eval_run_id)
    return normalize_case_run(row) if row is not None else None


async def list_case_runs_by_agno_eval_run_ids(eval_run_ids: list[str]) -> dict[str, dict[str, Any]]:
    requested_ids = list(dict.fromkeys(_string_list(eval_run_ids)))
    rows = await list_case_runs_by_agno_eval_run_ids_rows_async(requested_ids)
    mapped: dict[str, dict[str, Any]] = {}
    requested = set(requested_ids)
    for row in rows:
        case_run = normalize_case_run(row)
        for eval_run_id in case_run["agno_eval_run_ids"]:
            if eval_run_id in requested and eval_run_id not in mapped:
                mapped[eval_run_id] = case_run
    return mapped


async def list_case_runs(
    suite_run_id: str | None = None,
    case_id: str | None = None,
    status: str | None = None,
    *,
    page: int = 1,
    limit: int = 50,
) -> dict[str, Any]:
    """Agno-style ``{data, meta}`` for case run history."""
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 50), 100))
    rows, total = await list_case_run_rows_async(
        suite_run_id=suite_run_id,
        case_id=case_id,
        status=status,
        page=safe_page,
        limit=safe_limit,
    )
    return {
        "data": [normalize_case_run(row) for row in rows],
        "meta": pagination_meta(page=safe_page, limit=safe_limit, total_count=total),
    }


async def mark_case_run(case_run_id: str, status: str, values: dict[str, Any]) -> dict[str, Any] | None:
    update_values = _project_update(
        values,
        {
            "agent_run_id": _string,
            "session_id": _string,
            "trace_id": _string,
            "agno_eval_run_ids": _string_list,
            "error_type": _string,
            "error_summary": _string,
            "replay_of_case_run_id": _string,
        },
    )
    normalized_status = _normalize_status(status, "queued")
    update_values["status"] = normalized_status
    completed_at = _completed_at(normalized_status)
    if completed_at is not None:
        update_values["completed_at"] = completed_at
    row = await update_case_run_row_async(case_run_id, update_values)
    return normalize_case_run(row) if row is not None else None


async def mark_suite_run(
    suite_run_id: str,
    status: str,
    summary: dict[str, Any],
    error_summary: str = "",
) -> dict[str, Any] | None:
    normalized_status = _normalize_status(status, "queued")
    values: dict[str, Any] = {
        "status": normalized_status,
        "summary": _dict_value(summary),
        "error_summary": _string(error_summary),
    }
    completed_at = _completed_at(normalized_status)
    if completed_at is not None:
        values["completed_at"] = completed_at
    row = await update_suite_run_row_async(suite_run_id, values)
    return normalize_suite_run(row) if row is not None else None
