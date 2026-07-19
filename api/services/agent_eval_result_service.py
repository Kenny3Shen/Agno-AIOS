from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from api.services.postgres_store import get_async_agno_postgres_db
from api.utils.pagination import pagination_meta


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
    value = row.get("eval_data")
    if isinstance(value, dict):
        return cast(dict[str, Any], value)
    return {}


def _eval_type_key(value: object) -> str:
    return str(value or "").strip().lower()


def normalize_agno_eval_run(raw_run: Mapping[str, Any]) -> dict[str, Any]:
    """Project Agno eval run rows toward AgentOS EvalSchema plus UI projections.

    Wire primary key is ``id`` (from Agno ``run_id``). Payload lives in
    ``eval_data`` (Agno name). ``passed`` / ``score`` are workbench projections
    derived from eval_data for list/filter UX.
    """
    row = dict(raw_run)
    run_id = str(row.get("run_id") or "")
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
    rows, total = cast(
        tuple[list[dict[str, Any]], int],
        await db.get_eval_runs(
            limit=safe_limit,
            page=safe_page,
            sort_by="created_at",
            sort_order="desc",
            agent_id=agent_id,
            eval_type=eval_type,
            deserialize=False,
        ),
    )
    data = [normalize_agno_eval_run(row) for row in rows]
    return {
        "data": data,
        "meta": pagination_meta(page=safe_page, limit=safe_limit, total_count=total),
    }


async def get_agno_eval_run(eval_run_id: str) -> dict[str, Any] | None:
    raw_run = cast(
        dict[str, Any] | None,
        await get_async_agno_postgres_db().get_eval_run(
            eval_run_id,
            deserialize=False,
        ),
    )
    return normalize_agno_eval_run(raw_run) if raw_run is not None else None


async def list_failed_eval_runs(limit: int = 50) -> list[dict[str, Any]]:
    """Return recent failed eval runs (newest first).

    Agno list has no native ``passed=false`` filter, so we page recent runs
    until we collect ``limit`` failures or exhaust a small scan window.
    """
    safe_limit = max(1, min(int(limit or 50), 100))
    page_size = 50
    max_pages = 10
    failed: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        result = await list_agno_eval_runs(limit=page_size, page=page)
        rows = result.get("data") or []
        if not rows:
            break
        for item in rows:
            if item.get("passed") is False:
                failed.append(item)
                if len(failed) >= safe_limit:
                    return failed[:safe_limit]
        meta = result.get("meta") or {}
        total_count = int(meta.get("total_count") or 0)
        if total_count and page * page_size >= total_count:
            break
        if len(rows) < page_size:
            break
    return failed[:safe_limit]
