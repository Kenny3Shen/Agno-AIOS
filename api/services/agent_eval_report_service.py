"""Privacy-preserving, machine-readable exports for completed eval suite runs.

Agno's suite CLI emits a JSON artifact for CI.  The workbench retains a
compatible summary and per-case evidence, but deliberately does not persist raw
harmful prompts or model completions in that summary.  This module turns the
stored evidence into a stable export without widening that exposure.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from api.services.safety_eval_metrics import sanitize_safety_gate

REPORT_FORMAT = "tais.eval-suite-report.v1"
_RELIABILITY_EVIDENCE_FIELDS = (
    "failed_tool_calls",
    "passed_tool_calls",
    "additional_tool_calls",
    "missing_tool_calls",
    "failed_argument_checks",
    "passed_argument_checks",
)
_MAX_RELIABILITY_EVIDENCE_ITEMS = 50
_MAX_RELIABILITY_EVIDENCE_ITEM_CHARS = 500


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _count(value: Any) -> int:
    """Normalize persisted count-like values without inventing negative counts."""
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _optional_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(float(value)) else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _eval_target(value: Any) -> dict[str, str] | None:
    """Export only the stable, non-sensitive identity of the evaluated target."""
    target = _mapping(value)
    kind = _text(target.get("kind"))
    target_id = _text(target.get("id"))
    if kind not in {"agent", "team"} or not target_id:
        return None
    return {"kind": kind, "id": target_id}


def _reliability_evidence(value: Any) -> dict[str, list[str]] | None:
    """Export only bounded ReliabilityEval tool-name diagnostics.

    The workbench never exports raw Case inputs, model output, or tool
    arguments. These result fields are sufficiently useful for CI triage while
    retaining that privacy boundary.
    """
    raw = _mapping(value)
    if not raw:
        return None
    evidence: dict[str, list[str]] = {}
    for field in _RELIABILITY_EVIDENCE_FIELDS:
        values = raw.get(field)
        if not isinstance(values, (list, tuple, set)):
            continue
        raw_items = [item for item in values if isinstance(item, str)]
        if isinstance(values, set):
            raw_items.sort()
        items: list[str] = []
        for value in raw_items:
            item = value.strip()
            if not item:
                continue
            if len(item) > _MAX_RELIABILITY_EVIDENCE_ITEM_CHARS:
                item = f"{item[: _MAX_RELIABILITY_EVIDENCE_ITEM_CHARS - 1]}…"
            items.append(item)
            if len(items) >= _MAX_RELIABILITY_EVIDENCE_ITEMS:
                break
        if items:
            evidence[field] = items
    return evidence or None


def _performance_aggregate(value: Any) -> dict[str, float] | None:
    """Export only bounded aggregate metrics, never individual measurements."""
    raw = _mapping(value)
    aggregate: dict[str, float] = {}
    for field in ("avg", "median", "p95"):
        metric = _optional_number(raw.get(field))
        if metric is None or metric < 0:
            return None
        aggregate[field] = float(metric)
    return aggregate


def _performance_evidence(value: Any) -> dict[str, Any] | None:
    """Sanitize a persisted PerformanceEval summary for CI export.

    The Suite summary intentionally retains just configuration and aggregate
    numeric metrics.  Do not copy raw samples, arbitrary evaluator payloads,
    prompts, or outputs into the report even if a historic row contains them.
    """
    raw = _mapping(value)
    warmup_runs = raw.get("warmup_runs")
    num_iterations = raw.get("num_iterations")
    if (
        isinstance(warmup_runs, bool)
        or not isinstance(warmup_runs, int)
        or not 0 <= warmup_runs <= 100
        or isinstance(num_iterations, bool)
        or not isinstance(num_iterations, int)
        or not 1 <= num_iterations <= 100
    ):
        return None

    result: dict[str, Any] = {
        "warmup_runs": warmup_runs,
        "num_iterations": num_iterations,
    }
    runtime = _performance_aggregate(raw.get("runtime_seconds"))
    if runtime is not None:
        result["runtime_seconds"] = runtime
    memory = _performance_aggregate(raw.get("memory_mib"))
    if memory is not None:
        result["memory_mib"] = memory
    return result if len(result) > 2 else None


def _case_result_counts(case_rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Derive conservative aggregate counts when legacy summaries lack them."""
    counts = {"passed": 0, "failed": 0, "errored": 0, "skipped": 0}
    for row in case_rows:
        status = _text(row.get("status")).lower()
        if _optional_bool(row.get("skipped")) is True or status == "skipped":
            counts["skipped"] += 1
        elif _optional_bool(row.get("passed")) is True or status == "passed":
            counts["passed"] += 1
        elif status in {"error", "errored", "cancelled"}:
            counts["errored"] += 1
        else:
            counts["failed"] += 1
    return counts


def _suite_report_status(
    *,
    run_status: str,
    total: int,
    passed: int,
    failed: int,
    errored: int,
    skipped: int,
    safety_gate_status: str = "",
) -> str:
    """Match Agno's CI rule: only a non-empty all-pass suite is ``PASS``.

    Requiring the new runner's terminal ``passed`` state keeps a partially
    persisted or otherwise failed workbench run from green-lighting CI based
    on incomplete aggregate counts.
    """
    all_cases_passed = (
        total > 0 and passed == total and failed == 0 and errored == 0 and skipped == 0
    )
    if safety_gate_status == "failed":
        return "FAIL"
    if run_status == "passed" and all_cases_passed:
        return "PASS"
    return "FAIL"


def _case_report_row(value: Any) -> dict[str, Any] | None:
    """Map persisted CaseResult-lite evidence to a stable export row.

    Inputs and model outputs are intentionally absent.  They can contain
    harmful material and are not required for CI aggregate comparisons.
    """
    row = _mapping(value)
    if not row:
        return None
    name = _text(row.get("name"))
    case_id = _text(row.get("case_id"))
    if not name and not case_id:
        return None
    status = _text(row.get("status"))
    skipped = _optional_bool(row.get("skipped")) is True
    passed = _optional_bool(row.get("passed"))
    if passed is None:
        passed = status == "passed"
    duration_seconds = _optional_number(row.get("duration_seconds"))
    reliability_evidence = _reliability_evidence(row.get("reliability_evidence"))
    performance_evidence = _performance_evidence(row.get("performance"))
    report_row = {
        "name": name or case_id,
        "case_id": case_id or None,
        "case_run_id": _text(row.get("case_run_id")) or None,
        "session_id": _text(row.get("session_id")) or None,
        "duration_seconds": duration_seconds,
        "timeout_seconds": _optional_number(row.get("timeout_seconds")),
        "accuracy_passed": _optional_bool(row.get("accuracy_passed")),
        "accuracy_reason": _text(row.get("accuracy_reason")) or None,
        "accuracy_score": _optional_number(row.get("accuracy_score")),
        "judge_passed": _optional_bool(row.get("judge_passed")),
        "judge_reason": _text(row.get("judge_reason")) or None,
        "judge_score": _optional_number(row.get("judge_score")),
        "reliability_passed": _optional_bool(row.get("reliability_passed")),
        "timed_out": _optional_bool(row.get("timed_out")) is True,
        "skipped": skipped,
        "passed": passed,
        "error": _text(row.get("error")) or None,
        "status": status
        or ("skipped" if skipped else "passed" if passed else "failed"),
        "judge_id": _text(row.get("judge_id")) or None,
        "eval_profile": _text(row.get("eval_profile")) or None,
    }
    if reliability_evidence is not None:
        report_row["reliability_evidence"] = reliability_evidence
    if performance_evidence is not None:
        report_row["performance"] = performance_evidence
    return report_row


def _safety_summary(value: Any) -> dict[str, Any] | None:
    safety = _mapping(value)
    if not safety:
        return None
    allowed = (
        "pack_id",
        "pack_version",
        "judge_id",
        "eval_profile",
        "asr",
        "refusal_rate",
        "over_refusal_rate",
        "guardrail_trip_rate",
        "n_harmful",
        "n_benign",
        "n_unsafe",
        "n_refuse",
        "n_over_refuse",
        "n_guardrail_blocked",
        "n_error",
        "n_partial",
        "n_total",
    )
    sanitized = {key: safety[key] for key in allowed if key in safety}
    sample_hash = _text(safety.get("pack_cases_sha256")).lower()
    if len(sample_hash) == 64 and all(
        char in "0123456789abcdef" for char in sample_hash
    ):
        sanitized["pack_cases_sha256"] = sample_hash
    for field in ("pack_cases_count", "pack_sample_seed"):
        raw = safety.get(field)
        if isinstance(raw, int) and not isinstance(raw, bool):
            sanitized[field] = raw
    source_kind = _text(safety.get("pack_source_kind")).lower()
    if source_kind in {"csv", "hf", "local"}:
        sanitized["pack_source_kind"] = source_kind
    if gate := sanitize_safety_gate(safety.get("gate")):
        sanitized["gate"] = gate
    return sanitized


def build_suite_run_report(
    suite_run: Mapping[str, Any],
    *,
    case_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a CI-friendly report for one persisted suite run.

    The top-level ``summary`` / ``cases`` layout mirrors Agno's JSON report so
    consumers can use familiar fields.  ``format`` and ``privacy`` make the
    T.A.I.S-specific guarantees explicit instead of implying a raw Agno dump.
    """
    suite_run_id = _text(suite_run.get("id"))
    suite_id = _text(suite_run.get("suite_id"))
    if not suite_run_id or not suite_id:
        raise ValueError("Eval suite run is missing id or suite_id")

    stored_summary = _mapping(suite_run.get("summary"))
    # A SuiteRun summary is an aggregate/progress cache only. Per-Case
    # results are read from CaseRun's write-once checkpoint, so reporting a
    # recovered Suite never depends on an outdated embedded ``summary.cases``
    # document.
    case_rows = [
        item for item in (_case_report_row(value) for value in case_results) if item
    ]
    derived_counts = _case_result_counts(case_rows)
    passed = derived_counts["passed"]
    failed = derived_counts["failed"]
    errored = derived_counts["errored"]
    skipped = derived_counts["skipped"]
    total = len(case_rows)
    run_status = _text(suite_run.get("status")).lower()
    safety = _safety_summary(stored_summary.get("safety"))
    gate_status = ""
    if isinstance(safety, Mapping):
        gate = safety.get("gate")
        if isinstance(gate, Mapping):
            gate_status = _text(gate.get("status")).lower()
    status = _suite_report_status(
        run_status=run_status,
        total=total,
        passed=passed,
        failed=failed,
        errored=errored,
        skipped=skipped,
        safety_gate_status=gate_status,
    )

    summary: dict[str, Any] = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errored": errored,
        "skipped": skipped,
        "status": status,
    }
    selected_tag = _text(stored_summary.get("selected_tag"))
    if selected_tag:
        summary["selected_tag"] = selected_tag
    selected_name = _text(stored_summary.get("selected_name"))
    if selected_name:
        summary["selected_name"] = selected_name
    if "selected_cases" in stored_summary:
        summary["selected_cases"] = _count(stored_summary.get("selected_cases"))
    if "default_timeout" in stored_summary:
        summary["default_timeout"] = _count(stored_summary.get("default_timeout"))
    if target := _eval_target(stored_summary.get("target")):
        summary["target"] = target
    if safety:
        summary["safety"] = safety

    return {
        "format": REPORT_FORMAT,
        "suite_run": {
            "id": suite_run_id,
            "suite_id": suite_id,
            "status": run_status or "unknown",
            "started_at": suite_run.get("started_at"),
            "completed_at": suite_run.get("completed_at"),
        },
        "summary": summary,
        "cases": case_rows,
        "case_results_available": bool(case_rows),
        "privacy": {
            "inputs_included": False,
            "outputs_included": False,
            "note": "Raw case inputs and model outputs are omitted from this export.",
        },
    }
