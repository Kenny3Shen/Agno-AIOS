from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from agno.scheduler.cron import compute_next_run, validate_cron_expr, validate_timezone

from api.services.postgres_store import get_async_agno_postgres_db

ScheduleTargetType = Literal["agent", "team", "workflow"]

TARGET_ENDPOINT_PREFIXES: dict[str, str] = {
    "agent": "agents",
    "team": "teams",
    "workflow": "workflows",
}


def _iso_from_epoch(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        dt = value if value.tzinfo else value.replace(tzinfo=UTC)
        return dt.isoformat()
    if isinstance(value, int | float):
        try:
            return datetime.fromtimestamp(value, UTC).isoformat()
        except (OSError, ValueError):
            return str(value)
    return str(value)


def build_schedule_endpoint(target_type: str, target_id: str) -> str:
    clean_type = target_type.strip().lower()
    clean_id = target_id.strip().strip("/")
    if clean_type not in TARGET_ENDPOINT_PREFIXES:
        raise ValueError("target_type must be agent, team, or workflow")
    if not clean_id or "/" in clean_id or "://" in clean_id:
        raise ValueError("target_id must be a non-empty Agno resource id")
    return f"/{TARGET_ENDPOINT_PREFIXES[clean_type]}/{clean_id}/runs"


def parse_schedule_endpoint(endpoint: str) -> tuple[str, str]:
    parts = endpoint.strip().strip("/").split("/")
    if len(parts) != 3 or parts[2] != "runs":
        return "", ""
    for target_type, prefix in TARGET_ENDPOINT_PREFIXES.items():
        if parts[0] == prefix:
            return target_type, parts[1]
    return "", ""


def schedule_to_dict(schedule: Any) -> dict[str, Any]:
    if isinstance(schedule, dict):
        data = dict(schedule)
    else:
        data = schedule.to_dict() if hasattr(schedule, "to_dict") else dict(vars(schedule))
    target_type, target_id = parse_schedule_endpoint(str(data.get("endpoint") or ""))
    return {
        "id": str(data.get("id") or ""),
        "name": str(data.get("name") or ""),
        "description": data.get("description"),
        "method": str(data.get("method") or "POST"),
        "endpoint": str(data.get("endpoint") or ""),
        "target_type": target_type,
        "target_id": target_id,
        "payload": data.get("payload") if isinstance(data.get("payload"), dict) else {},
        "cron_expr": str(data.get("cron_expr") or ""),
        "timezone": str(data.get("timezone") or "UTC"),
        "timeout_seconds": int(data.get("timeout_seconds") or 3600),
        "max_retries": int(data.get("max_retries") or 0),
        "retry_delay_seconds": int(data.get("retry_delay_seconds") or 60),
        "enabled": bool(data.get("enabled")),
        "next_run_at": data.get("next_run_at"),
        "next_run_at_iso": _iso_from_epoch(data.get("next_run_at")),
        "created_at": data.get("created_at"),
        "created_at_iso": _iso_from_epoch(data.get("created_at")),
        "updated_at": data.get("updated_at"),
        "updated_at_iso": _iso_from_epoch(data.get("updated_at")),
    }


def schedule_run_to_dict(run: Any) -> dict[str, Any]:
    if isinstance(run, dict):
        data = dict(run)
    else:
        data = run.to_dict() if hasattr(run, "to_dict") else dict(vars(run))
    return {
        "id": str(data.get("id") or ""),
        "schedule_id": str(data.get("schedule_id") or ""),
        "attempt": int(data.get("attempt") or 1),
        "triggered_at": data.get("triggered_at"),
        "triggered_at_iso": _iso_from_epoch(data.get("triggered_at")),
        "completed_at": data.get("completed_at"),
        "completed_at_iso": _iso_from_epoch(data.get("completed_at")),
        "status": str(data.get("status") or ""),
        "status_code": data.get("status_code"),
        "run_id": data.get("run_id"),
        "session_id": data.get("session_id"),
        "error": data.get("error"),
        "input": data.get("input") if isinstance(data.get("input"), dict) else None,
        "output": data.get("output") if isinstance(data.get("output"), dict) else None,
        "requirements": data.get("requirements") if isinstance(data.get("requirements"), list) else None,
        "created_at": data.get("created_at"),
        "created_at_iso": _iso_from_epoch(data.get("created_at")),
    }


async def create_schedule(
    *,
    name: str,
    target_type: str,
    target_id: str,
    cron_expr: str,
    payload: dict[str, Any] | None = None,
    description: str | None = None,
    timezone: str = "UTC",
    timeout_seconds: int = 3600,
    max_retries: int = 0,
    retry_delay_seconds: int = 60,
    enabled: bool = True,
) -> dict[str, Any]:
    clean_name = name.strip()
    clean_cron = cron_expr.strip()
    clean_timezone = timezone.strip() or "UTC"
    if not validate_cron_expr(clean_cron):
        raise ValueError(f"Invalid cron expression: {clean_cron}")
    if not validate_timezone(clean_timezone):
        raise ValueError(f"Invalid timezone: {clean_timezone}")

    db = get_async_agno_postgres_db()
    existing = await db.get_schedule_by_name(clean_name)
    if existing is not None:
        raise ValueError(f"Schedule with name '{clean_name}' already exists")

    created = await db.create_schedule(
        {
            "id": str(uuid4()),
            "name": clean_name,
            "description": (description or "").strip() or None,
            "method": "POST",
            "endpoint": build_schedule_endpoint(target_type, target_id),
            "payload": payload or {},
            "cron_expr": clean_cron,
            "timezone": clean_timezone,
            "timeout_seconds": timeout_seconds,
            "max_retries": max_retries,
            "retry_delay_seconds": retry_delay_seconds,
            "enabled": True,
            "next_run_at": compute_next_run(clean_cron, clean_timezone),
            "locked_by": None,
            "locked_at": None,
            "created_at": int(time.time()),
            "updated_at": None,
        }
    )
    if not enabled:
        disabled = await db.update_schedule(created["id"], enabled=False)
        if disabled is not None:
            created = disabled
    return schedule_to_dict(created)


async def list_schedules(
    *,
    enabled: bool | None = None,
    limit: int = 100,
    page: int = 1,
) -> list[dict[str, Any]]:
    result = await get_async_agno_postgres_db().get_schedules(
        enabled=enabled,
        limit=limit,
        page=page,
    )
    rows = result[0] if isinstance(result, tuple) else result
    return [schedule_to_dict(schedule) for schedule in rows]


async def get_schedule(schedule_id: str) -> dict[str, Any] | None:
    schedule = await get_async_agno_postgres_db().get_schedule(schedule_id)
    return schedule_to_dict(schedule) if schedule is not None else None


async def update_schedule(
    schedule_id: str,
    *,
    name: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    cron_expr: str | None = None,
    payload: dict[str, Any] | None = None,
    description: str | None = None,
    timezone: str | None = None,
    timeout_seconds: int | None = None,
    max_retries: int | None = None,
    retry_delay_seconds: int | None = None,
) -> dict[str, Any] | None:
    db = get_async_agno_postgres_db()
    current = await db.get_schedule(schedule_id)
    if current is None:
        return None
    current_data = schedule_to_dict(current)
    updates: dict[str, Any] = {}
    if name is not None:
        updates["name"] = name.strip()
    if description is not None:
        updates["description"] = description.strip() or None
    if payload is not None:
        updates["payload"] = payload
    if target_type is not None or target_id is not None:
        updates["endpoint"] = build_schedule_endpoint(
            target_type or current_data["target_type"],
            target_id or current_data["target_id"],
        )
    next_cron = cron_expr.strip() if cron_expr is not None else current_data["cron_expr"]
    next_timezone = timezone.strip() if timezone is not None else current_data["timezone"]
    if cron_expr is not None:
        if not validate_cron_expr(next_cron):
            raise ValueError(f"Invalid cron expression: {next_cron}")
        updates["cron_expr"] = next_cron
    if timezone is not None:
        if not validate_timezone(next_timezone):
            raise ValueError(f"Invalid timezone: {next_timezone}")
        updates["timezone"] = next_timezone
    if cron_expr is not None or timezone is not None:
        updates["next_run_at"] = compute_next_run(next_cron, next_timezone)
    if timeout_seconds is not None:
        updates["timeout_seconds"] = timeout_seconds
    if max_retries is not None:
        updates["max_retries"] = max_retries
    if retry_delay_seconds is not None:
        updates["retry_delay_seconds"] = retry_delay_seconds
    if not updates:
        return current_data
    updated = await db.update_schedule(schedule_id, **updates)
    return schedule_to_dict(updated) if updated is not None else None


async def set_schedule_enabled(schedule_id: str, enabled: bool) -> dict[str, Any] | None:
    db = get_async_agno_postgres_db()
    schedule = await db.get_schedule(schedule_id)
    if schedule is None:
        return None
    updates: dict[str, Any] = {"enabled": enabled}
    if enabled:
        schedule_data = schedule_to_dict(schedule)
        updates["next_run_at"] = compute_next_run(
            schedule_data["cron_expr"],
            schedule_data["timezone"],
        )
    updated = await db.update_schedule(schedule_id, **updates)
    return schedule_to_dict(updated) if updated is not None else None


async def delete_schedule(schedule_id: str) -> bool:
    return bool(await get_async_agno_postgres_db().delete_schedule(schedule_id))


async def list_schedule_runs(
    schedule_id: str,
    *,
    limit: int = 20,
    page: int = 1,
) -> list[dict[str, Any]]:
    result = await get_async_agno_postgres_db().get_schedule_runs(
        schedule_id,
        limit=limit,
        page=page,
    )
    rows = result[0] if isinstance(result, tuple) else result
    return [schedule_run_to_dict(run) for run in rows]


async def get_scheduler_payload(actor: Any | None = None) -> dict[str, Any]:
    schedules = await list_schedules(limit=100)
    enabled = sum(1 for schedule in schedules if schedule["enabled"])
    disabled = len(schedules) - enabled
    records = [
        {
            "id": schedule["id"],
            "title": schedule["name"],
            "subtitle": schedule["endpoint"],
            "status": "enabled" if schedule["enabled"] else "disabled",
            "meta": {
                "description": schedule["description"],
                "target_type": schedule["target_type"],
                "target_id": schedule["target_id"],
                "endpoint": schedule["endpoint"],
                "cron_expr": schedule["cron_expr"],
                "timezone": schedule["timezone"],
                "next_run_at": schedule["next_run_at_iso"],
                "timeout_seconds": schedule["timeout_seconds"],
                "max_retries": schedule["max_retries"],
                "retry_delay_seconds": schedule["retry_delay_seconds"],
                "payload": schedule["payload"],
            },
            "updated_at": schedule["updated_at_iso"] or schedule["created_at_iso"],
        }
        for schedule in schedules
    ]
    return {
        "module": "scheduler",
        "title": "Scheduler",
        "description": "Agno Scheduler cron jobs and run history.",
        "status": "ready",
        "metrics": [
            {
                "label": "Schedules",
                "value": len(schedules),
                "hint": "Agno schedule rows",
                "tone": "blue",
            },
            {
                "label": "Enabled",
                "value": enabled,
                "hint": "Enabled schedules",
                "tone": "green" if enabled else "yellow",
            },
            {
                "label": "Disabled",
                "value": disabled,
                "hint": "Disabled schedules",
                "tone": "yellow",
            },
        ],
        "records": records,
        "schedules": schedules,
        "generated_at": _iso_from_epoch(datetime.now(UTC)),
    }
