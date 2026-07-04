from __future__ import annotations

from typing import Any

from api.services.os_control_service import (
    fetch_due_schedule_jobs,
    mark_schedule_dispatched,
    update_schedule_after_dispatch,
)
from api.tasks.celery_app import celery_app


@celery_app.task(name="api.tasks.scheduler.run_scheduled_job")
def run_scheduled_job(schedule_id: str) -> dict[str, Any]:
    """Dispatch point for Scheduler jobs.

    Workflow and Agent-triggered Skill execution will attach their concrete
    runners here; the persisted schedule row already carries target metadata.
    """
    mark_schedule_dispatched(schedule_id, task_id=getattr(run_scheduled_job.request, "id", ""))
    return {
        "schedule_id": schedule_id,
        "status": "dispatched",
    }


@celery_app.task(name="api.tasks.scheduler.dispatch_due_schedules")
def dispatch_due_schedules() -> dict[str, Any]:
    dispatched = []
    for row in fetch_due_schedule_jobs():
        schedule_id = str(row.get("id") or "")
        if not schedule_id:
            continue
        task = run_scheduled_job.apply_async(args=[schedule_id])
        update_schedule_after_dispatch(schedule_id)
        dispatched.append({"schedule_id": schedule_id, "task_id": task.id})
    return {
        "status": "ok",
        "dispatched": dispatched,
    }
