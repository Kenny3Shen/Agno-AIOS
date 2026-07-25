"""Atomic API-side producer for durable Eval Suite executions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from uuid import uuid4

from api.auth.claims import actor_id, actor_role
from api.persistence.agent_evals import (
    create_suite_run_with_case_runs_and_enqueue_job_async,
)
from api.persistence.durable_jobs import JobKind
from api.services import agent_eval_case_store as case_store
from api.services.agent_eval_suite_jobs import build_eval_suite_run_payload
from api.services.model_config_service import get_eval_judge_model_id


def _case_ids(plan: Mapping[str, Any]) -> list[str]:
    raw_case_ids = plan.get("case_ids")
    if isinstance(raw_case_ids, str) or not isinstance(raw_case_ids, Sequence):
        raise ValueError("Eval suite run requires at least one selected case")
    case_ids = [str(case_id or "").strip() for case_id in raw_case_ids]
    if not case_ids or any(not case_id for case_id in case_ids):
        raise ValueError("Eval suite run requires at least one selected case")
    if len(set(case_ids)) != len(case_ids):
        raise ValueError("Eval suite run selected case ids must be unique")
    return case_ids


def _execution_manifest(
    *,
    actor: Any,
    plan: Mapping[str, Any],
    judge_model_config_id: str,
) -> dict[str, Any]:
    """Freeze every worker input that used to live in the durable payload."""
    normalized_actor_id = actor_id(actor).strip()
    if not normalized_actor_id:
        raise ValueError("Eval suite run actor id is required")
    default_timeout = plan.get("default_timeout")
    if isinstance(default_timeout, bool) or not isinstance(default_timeout, int):
        raise ValueError("Eval suite run default_timeout is required")
    case_count = len(_case_ids(plan))
    return {
        "version": case_store.SUITE_RUN_EXECUTION_MANIFEST_VERSION,
        "actor": {
            "id": normalized_actor_id,
            "role": actor_role(actor),
            "is_superuser": bool(getattr(actor, "is_superuser", False)),
        },
        "selected_tag": plan.get("selected_tag"),
        "selected_name": plan.get("selected_name"),
        "case_count": case_count,
        "default_timeout": default_timeout,
        "judge_model_config_id": str(judge_model_config_id or "").strip(),
    }


async def enqueue_suite_run(
    *,
    suite_id: str,
    actor: Any,
    plan: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> tuple[dict[str, Any], str]:
    """Persist a SuiteRun and its worker job in one database transaction.

    ``plan`` comes from :func:`agent_eval_runner.prepare_suite_run`; this
    boundary projects only its frozen durable execution fields. Private
    in-memory Case definitions therefore never reach the durable job payload.
    """
    normalized_suite_id = str(suite_id or "").strip()
    if not normalized_suite_id:
        raise ValueError("suite_id is required")
    case_ids = _case_ids(plan)
    suite = plan.get("_suite")
    cases = plan.get("_cases")
    if not isinstance(suite, Mapping):
        raise ValueError("Eval suite run plan is missing its frozen Suite")
    if isinstance(cases, str) or not isinstance(cases, Sequence):
        raise ValueError("Eval suite run plan is missing its frozen Cases")
    frozen_cases = [case for case in cases if isinstance(case, Mapping)]
    if len(frozen_cases) != len(cases):
        raise ValueError("Eval suite run plan contains an invalid frozen Case")
    suite_run_id = uuid4().hex
    judge_model_config_id = await get_eval_judge_model_id()
    execution_snapshot = case_store.build_suite_run_execution_snapshot(
        suite,
        run_manifest=_execution_manifest(
            actor=actor,
            plan=plan,
            judge_model_config_id=str(judge_model_config_id or ""),
        ),
    )
    work_items = case_store.build_suite_run_case_work_items(
        suite_run_id,
        execution_snapshot,
        frozen_cases,
    )
    work_item_case_ids = [
        str(item.get("case_id") or "").strip() for item in work_items
    ]
    if work_item_case_ids != case_ids:
        raise ValueError(
            "Eval suite run CaseRun work-item order must match the durable job selection"
        )
    payload = build_eval_suite_run_payload(suite_run_id=suite_run_id)
    values = {
        "id": suite_run_id,
        "suite_id": normalized_suite_id,
        "status": "queued",
        "started_by": actor_id(actor),
        "error_summary": "",
        "summary": dict(summary),
        # Private Suite-level execution metadata only.  Raw Case prompts and
        # reference answers are stored once on the pre-created CaseRun rows,
        # never in the durable payload or public progress summary.
        "execution_snapshot": execution_snapshot,
    }
    row, job = await create_suite_run_with_case_runs_and_enqueue_job_async(
        values,
        case_run_values=work_items,
        kind=JobKind.EVAL_SUITE_RUN,
        payload=payload,
        idempotency_key=f"eval-suite-run:{suite_run_id}",
    )
    return case_store.normalize_suite_run(row), job.id


__all__ = ["enqueue_suite_run"]
