from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from typing import Any, cast

from api.services.postgres_store import get_async_agno_postgres_db


def _row_dict(raw_row: Any) -> dict[str, Any]:
    if isinstance(raw_row, dict):
        return dict(raw_row)
    if is_dataclass(raw_row) and not isinstance(raw_row, type):
        dumped = asdict(raw_row)
        if isinstance(dumped, dict):
            return dict(dumped)
    model_dump = getattr(raw_row, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dict(dumped)
    to_dict = getattr(raw_row, "to_dict", None)
    if callable(to_dict):
        dumped = to_dict()
        if isinstance(dumped, dict):
            return dict(dumped)
    try:
        return dict(vars(raw_row))
    except TypeError:
        return {}


def _passed_from_data(data: dict[str, Any]) -> bool | None:
    for key in ("passed", "success", "is_passed"):
        value = data.get(key)
        if isinstance(value, bool):
            return value
    return None


def _score_from_data(data: dict[str, Any]) -> float | None:
    for key in ("overall_score", "score", "mean_score"):
        value = data.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            return float(value)
    return None


def _payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    for key in ("eval_data", "data"):
        value = row.get(key)
        if isinstance(value, dict):
            return cast(dict[str, Any], value)
    return {}


def _eval_type_key(value: Any) -> str:
    raw_value = getattr(value, "value", value)
    if raw_value is None:
        return ""
    text = str(raw_value).strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.lower()


def _date_key(value: Any) -> str:
    if isinstance(value, datetime):
        current = value
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        return current.astimezone(UTC).date().isoformat()
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, UTC).date().isoformat()
        except (OSError, ValueError):
            return ""
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            return value[:10]
    return ""


def normalize_agno_eval_run(raw_run: Any) -> dict[str, Any]:
    """Project Agno eval run rows toward AgentOS EvalSchema plus UI projections.

    Wire primary key is ``id`` (from Agno ``run_id``). Payload lives in
    ``eval_data`` (Agno name). ``passed`` / ``score`` are workbench projections
    derived from eval_data for list/filter UX.
    """
    row = _row_dict(raw_run)
    run_id = str(row.get("run_id") or row.get("id") or "")
    eval_data = _payload_from_row(row)
    raw_input = row.get("eval_input")
    return {
        "id": run_id,
        "name": str(row.get("name") or run_id or "Eval Run"),
        "eval_type": _eval_type_key(row.get("eval_type")),
        "agent_id": row.get("agent_id"),
        "team_id": row.get("team_id"),
        "workflow_id": row.get("workflow_id"),
        "model_id": row.get("model_id"),
        "model_provider": row.get("model_provider"),
        "evaluated_component_name": row.get("evaluated_component_name"),
        "passed": _passed_from_data(eval_data),
        "score": _score_from_data(eval_data),
        "eval_data": eval_data,
        "eval_input": raw_input if isinstance(raw_input, dict) else {},
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def _unpack_runs_result(result: Any) -> tuple[list[Any], int]:
    if isinstance(result, tuple) and len(result) == 2:
        rows, total = result
        rows_list = list(rows or [])
        try:
            return rows_list, int(total)
        except (TypeError, ValueError):
            return rows_list, len(rows_list)
    rows_list = list(result or [])
    return rows_list, len(rows_list)


def _pagination_meta(*, page: int, limit: int, total_count: int, search_time_ms: float = 0.0) -> dict[str, Any]:
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, int(limit or 1))
    total = max(0, int(total_count or 0))
    total_pages = (total + safe_limit - 1) // safe_limit if total else 0
    return {
        "page": safe_page,
        "limit": safe_limit,
        "total_pages": total_pages,
        "total_count": total,
        "search_time_ms": float(search_time_ms or 0.0),
    }


async def list_agno_eval_runs(
    limit: int = 50,
    page: int = 1,
    eval_type: list[str] | None = None,
    agent_id: str | None = None,
) -> dict[str, Any]:
    """List Agno eval runs with AgentOS-style ``data`` / ``meta`` envelope."""
    safe_limit = max(1, min(int(limit or 50), 100))
    safe_page = max(1, int(page or 1))
    db: Any = get_async_agno_postgres_db()
    result = await db.get_eval_runs(
        limit=safe_limit,
        page=safe_page,
        sort_by="created_at",
        sort_order="desc",
        agent_id=agent_id,
        eval_type=eval_type,
        deserialize=False,
    )
    rows, total = _unpack_runs_result(result)
    data = [normalize_agno_eval_run(row) for row in rows]
    return {
        "data": data,
        "meta": _pagination_meta(page=safe_page, limit=safe_limit, total_count=total),
    }


async def get_agno_eval_run(eval_run_id: str) -> dict[str, Any] | None:
    raw_run = await get_async_agno_postgres_db().get_eval_run(
        eval_run_id,
        deserialize=False,
    )
    return normalize_agno_eval_run(raw_run) if raw_run is not None else None


def build_eval_trends(runs: list[dict[str, Any]]) -> dict[str, Any]:
    by_date: dict[str, dict[str, Any]] = {}
    by_eval_type: dict[str, dict[str, Any]] = {}
    by_status = {"failed": 0, "passed": 0, "unknown": 0}

    for run in runs:
        passed = run.get("passed")
        if passed is True:
            status_key = "passed"
        elif passed is False:
            status_key = "failed"
        else:
            status_key = "unknown"
        by_status[status_key] += 1

        date_key = _date_key(run.get("created_at"))
        if date_key:
            bucket = by_date.setdefault(
                date_key,
                {"date": date_key, "total": 0, "passed": 0, "failed": 0},
            )
            bucket["total"] += 1
            if passed is True:
                bucket["passed"] += 1
            elif passed is False:
                bucket["failed"] += 1

        type_key = str(run.get("eval_type") or "unknown")
        bucket = by_eval_type.setdefault(
            type_key,
            {"eval_type": type_key, "total": 0, "passed": 0, "failed": 0},
        )
        bucket["total"] += 1
        if passed is True:
            bucket["passed"] += 1
        elif passed is False:
            bucket["failed"] += 1

    return {
        "by_date": [by_date[key] for key in sorted(by_date)],
        "by_eval_type": [by_eval_type[key] for key in sorted(by_eval_type)],
        "by_status": by_status,
    }


async def list_failed_eval_runs(limit: int = 50) -> list[dict[str, Any]]:
    result = await list_agno_eval_runs(limit=limit, page=1)
    return [item for item in result["data"] if item.get("passed") is False]
