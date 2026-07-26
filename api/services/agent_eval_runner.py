from __future__ import annotations

import asyncio
import math
import os
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from inspect import isawaitable
from types import SimpleNamespace
from typing import Any

from agno.eval.accuracy import AccuracyEval
from agno.eval.agent_as_judge import AgentAsJudgeEval
from agno.eval.performance import PerformanceEval
from agno.eval.reliability import ReliabilityEval
from loguru import logger

from api.auth.claims import actor_id, actor_role
from api.persistence.durable_jobs import JobLeaseLostError
from api.services import agent_eval_case_store as case_store
from api.services.guardrails import is_input_check_error
from api.services.model_config_service import get_eval_judge_model_id, get_model_for_run
from api.services.model_factory import build_agno_model
from api.services.postgres_store import get_async_agno_postgres_db
from api.services.eval_targets import EvalTarget, parse_eval_target, target_from_suite
from api.services.safety_eval_metrics import (
    compute_safety_summary,
    derive_safety_label,
    evaluate_safety_gate,
)
from api.services.safety_eval_pack_service import pack_identity_from_suite
from api.services.safety_eval_rubrics import (
    eval_profile_from_metadata,
    resolve_case_judge_criteria,
)
from api.services.security_run_runtime import (
    DEFAULT_SECURITY_RUN_RUNTIME,
    SecurityRunRequest,
    SecurityRunRuntime,
)

# Agno's arun_cases executes Cases sequentially. Keep that deterministic,
# side-effect-safe behavior by default; an operator may explicitly opt into
# bounded parallelism through TAIS_EVAL_SUITE_CONCURRENCY for isolated suites.
_DEFAULT_SUITE_CONCURRENCY = 1
_MAX_SUITE_CONCURRENCY = 8
# Agno's Suite ``run_cases`` defaults to a 120-second *per-Case* timeout.
# Bound caller-provided values so an accidental API request cannot leave a
# worker executing an eval forever.
_DEFAULT_SUITE_TIMEOUT_SECONDS = 120
_MAX_SUITE_TIMEOUT_SECONDS = 3_600
# Agno's AccuracyEval examples use ``avg_score >= 8`` as the pass condition.
# ``agent_eval_cases.threshold`` deliberately remains reserved for
# AgentAsJudgeEval's numeric threshold (see safety-eval.md §6.5.6).
_DEFAULT_ACCURACY_PASS_THRESHOLD = 8.0
_SAFE_PACK_SOURCE_KINDS = frozenset({"csv", "hf", "local"})
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
_SUPPORTED_EVAL_TYPES = frozenset(
    {"accuracy", "agent_as_judge", "reliability", "performance"}
)
_LLM_EVALUATOR_TYPES = frozenset({"accuracy", "agent_as_judge"})

SuiteRunCancellationEvent = asyncio.Event | None


@dataclass(frozen=True)
class AgentEvalRunnerDependencies:
    security_runtime: SecurityRunRuntime = DEFAULT_SECURITY_RUN_RUNTIME
    get_eval_db: Callable[[], Any] = get_async_agno_postgres_db
    accuracy_eval_cls: Any = AccuracyEval
    judge_eval_cls: Any = AgentAsJudgeEval
    reliability_eval_cls: Any = ReliabilityEval
    performance_eval_cls: Any = PerformanceEval
    get_eval_judge_model_id: Callable[[], Any] = get_eval_judge_model_id
    get_model_for_run: Callable[..., Any] = get_model_for_run
    build_agno_model: Callable[..., Any] = build_agno_model


async def _maybe_await(value: Any) -> Any:
    if isawaitable(value):
        return await value
    return value


def _case_session_id(case_run_id: str, *, lease_epoch: int | None = None) -> str:
    """Return an isolated Case session, including the durable fence when set."""
    if lease_epoch is not None and lease_epoch > 0:
        return f"eval_{case_run_id}_{lease_epoch}"
    return f"eval_{case_run_id}"


def _eval_types(case: dict[str, Any]) -> set[str]:
    values = case.get("eval_types")
    if not isinstance(values, list):
        raise ValueError("eval_types must be a non-empty list")
    normalized = {str(value).strip() for value in values if str(value).strip()}
    if not normalized:
        raise ValueError("eval_types must be a non-empty list")
    unsupported = sorted(normalized - _SUPPORTED_EVAL_TYPES)
    if unsupported:
        raise ValueError(f"Unsupported eval type: {', '.join(unsupported)}")
    return normalized


def _run_identifier(value: Any) -> str | None:
    """Return a concrete Agno run identifier without stringifying arbitrary objects."""
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _eval_id(eval_instance: Any, result: Any | None = None) -> str | None:
    """Extract the persisted Agno run id from an evaluator/result pair.

    Accuracy, Reliability, and Performance expose ``eval_id`` on the evaluator.
    ``AgentAsJudgeEval`` instead creates a run id for each ``arun`` invocation
    and returns it as ``AgentAsJudgeResult.run_id``. Prefer the returned value
    so every evaluator can be associated with the CaseRun that launched it.
    """
    for candidate in (
        getattr(result, "run_id", None),
        result.get("run_id") if isinstance(result, Mapping) else None,
        getattr(result, "eval_id", None),
        result.get("eval_id") if isinstance(result, Mapping) else None,
        getattr(eval_instance, "eval_id", None),
        getattr(eval_instance, "run_id", None),
    ):
        if run_id := _run_identifier(candidate):
            return run_id
    return None


def _response_value(response: Any, name: str) -> str:
    value = getattr(response, name, "")
    if value is None:
        return ""
    return str(value)


class EvalSubjectRunNotCompletedError(RuntimeError):
    """Raised when the target did not produce a gradeable Agno run output."""


def _subject_response_status(response: Any) -> str:
    """Normalize Agno ``RunStatus`` (or its string form) for a Case gate."""
    raw_status = getattr(response, "status", None)
    value = getattr(raw_status, "value", raw_status)
    if value is None:
        return ""
    return str(value).strip().casefold()


def _require_completed_subject_response(response: Any) -> None:
    """Reject cancelled, paused, failed, and malformed subject outputs.

    Agno's suite runner only passes a completed ``RunOutput``/``TeamRunOutput``
    to the judge and reliability checks. Evaluating placeholder content from a
    cancelled or paused run can otherwise turn an incomplete subject execution
    into a false passing Case.
    """
    status = _subject_response_status(response)
    if status == "completed":
        return
    label = status or "missing"
    raise EvalSubjectRunNotCompletedError(
        f"Eval subject run did not complete (status: {label})"
    )


def _case_metadata(case: Mapping[str, Any]) -> dict[str, Any]:
    meta = case.get("metadata")
    return dict(meta) if isinstance(meta, Mapping) else {}


def _is_safety_suite(suite: Mapping[str, Any]) -> bool:
    """Keep product-level aggregate gates scoped to explicitly safety Suites."""
    tags = suite.get("tags")
    if not isinstance(tags, list):
        return False
    return any(
        str(tag).strip().casefold() == "safety"
        or str(tag).strip().casefold().startswith("pack:")
        for tag in tags
    )


def _identity_part(value: Any) -> str:
    """Normalize an identity component without treating a missing value as equal."""
    return str(value or "").strip().casefold()


def _selector_identity(summary: Mapping[str, Any]) -> tuple[str, str]:
    """Return the Agno tag/name scope that produced a Suite result."""
    return (
        str(summary.get("selected_tag") or "").strip(),
        str(summary.get("selected_name") or "").strip(),
    )


def _pack_cases_sha256(value: Any) -> str:
    """Accept only a canonical SHA-256 sample fingerprint."""
    text = str(value or "").strip().lower()
    if len(text) != 64 or not all(
        character in "0123456789abcdef" for character in text
    ):
        return ""
    return text


def _consistent_pack_sample_identity(
    cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return only sample metadata shared by every selected Case.

    A Suite may contain manually added, legacy, or stale-version Cases.  Do
    not attach a source sample identity unless every Case that contributed to
    the run names the same imported artifact; that makes automatic baselines
    fail closed rather than compare different samples under one pack version.
    """
    if not cases:
        return {}

    metadata_rows = [_case_metadata(case) for case in cases]
    hashes = [
        _pack_cases_sha256(metadata.get("pack_cases_sha256"))
        for metadata in metadata_rows
    ]
    if not all(hashes) or len(set(hashes)) != 1:
        return {}

    identity: dict[str, Any] = {"pack_cases_sha256": hashes[0]}
    for field in ("pack_cases_count", "pack_sample_seed"):
        values = [metadata.get(field) for metadata in metadata_rows]
        if (
            values
            and all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in values
            )
            and len(set(values)) == 1
        ):
            identity[field] = values[0]

    source_kinds = [
        str(metadata.get("pack_source_kind") or "").strip().lower()
        for metadata in metadata_rows
    ]
    if (
        source_kinds
        and all(kind in _SAFE_PACK_SOURCE_KINDS for kind in source_kinds)
        and len(set(source_kinds)) == 1
    ):
        identity["pack_source_kind"] = source_kinds[0]
    return identity


def _compatible_safety_baseline(
    *,
    current_safety: Mapping[str, Any],
    current_summary: Mapping[str, Any],
    current_suite_run_id: str,
    historical_runs: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, str]:
    """Select the newest safe comparison baseline from persisted Suite runs.

    Metrics are comparable only when their dataset and decision surface are
    identical.  Refuse to infer a baseline for legacy/manual suites lacking a
    pack version, or after a judge/profile/selector change.  The persistence
    list is newest-first, so the first compatible terminal run is the most
    recent valid baseline.
    """
    identity_keys = (
        "pack_id",
        "pack_version",
        "pack_cases_sha256",
        "judge_id",
        "eval_profile",
    )
    current_identity = {
        key: (
            _pack_cases_sha256(current_safety.get(key))
            if key == "pack_cases_sha256"
            else _identity_part(current_safety.get(key))
        )
        for key in identity_keys
    }
    if any(not value for value in current_identity.values()):
        return None, ""
    current_selector = _selector_identity(current_summary)

    for run in historical_runs:
        run_id = str(run.get("id") or "").strip()
        if not run_id or run_id == current_suite_run_id:
            continue
        if str(run.get("status") or "").strip().lower() not in {
            "passed",
            "failed",
            "completed",
        }:
            continue
        historic_summary = run.get("summary")
        if not isinstance(historic_summary, Mapping):
            continue
        if _selector_identity(historic_summary) != current_selector:
            continue
        historic_safety = historic_summary.get("safety")
        if not isinstance(historic_safety, Mapping):
            continue
        if all(
            (
                _pack_cases_sha256(historic_safety.get(key))
                if key == "pack_cases_sha256"
                else _identity_part(historic_safety.get(key))
            )
            == current_identity[key]
            for key in identity_keys
        ):
            return historic_safety, run_id
    return None, ""


async def _load_compatible_safety_baseline(
    *,
    suite_id: str,
    current_suite_run_id: str,
    current_safety: Mapping[str, Any],
    current_summary: Mapping[str, Any],
) -> tuple[Mapping[str, Any] | None, str]:
    """Load a bounded history page without allowing history failures to fail an eval."""
    try:
        history = await case_store.list_suite_runs(suite_id, page=1, limit=100)
    except Exception:
        logger.warning(
            "Unable to load prior safety eval runs for baseline comparison: {}",
            suite_id,
        )
        return None, ""
    raw_runs = history.get("data") if isinstance(history, Mapping) else None
    runs = (
        [run for run in raw_runs if isinstance(run, Mapping)]
        if isinstance(raw_runs, list)
        else []
    )
    return _compatible_safety_baseline(
        current_safety=current_safety,
        current_summary=current_summary,
        current_suite_run_id=current_suite_run_id,
        historical_runs=runs,
    )


def _result_value(result: Any, name: str) -> Any:
    if isinstance(result, Mapping):
        return result.get(name)
    return getattr(result, name, None)


def _judge_score(value: Any) -> int | None:
    """Return an Agno numeric-judge score only when it is a valid 1--10 int."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and 1 <= value <= 10:
        return value
    if isinstance(value, float) and value.is_integer() and 1 <= value <= 10:
        return int(value)
    return None


def _accuracy_score(value: Any) -> float | None:
    """Return a finite Agno AccuracyEval score within its documented 1--10 range."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    if not math.isfinite(score) or not 1.0 <= score <= 10.0:
        return None
    return score


def _performance_metric(value: Any) -> float | None:
    """Accept only finite, non-negative aggregate benchmark metrics.

    Performance evidence is copied into Suite summaries and exported for CI.
    Unlike raw individual samples, the three aggregate values below contain no
    model content or tool data and have a stable small shape.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    metric = float(value)
    if not math.isfinite(metric) or metric < 0:
        return None
    return round(metric, 6)


def _performance_aggregate(
    result: Any,
    *,
    average_field: str,
    median_field: str,
    p95_field: str,
) -> dict[str, float] | None:
    """Project one Agno PerformanceResult dimension into bounded aggregates."""
    average = _performance_metric(_result_value(result, average_field))
    median = _performance_metric(_result_value(result, median_field))
    p95 = _performance_metric(_result_value(result, p95_field))
    if average is None or median is None or p95 is None:
        return None
    return {"avg": average, "median": median, "p95": p95}


def _performance_evidence(
    result: Any,
    performance_config: Mapping[str, int | bool],
) -> dict[str, Any] | None:
    """Build the privacy-safe performance evidence attached to a Case result.

    Agno returns individual samples as well as aggregate fields. Individual
    samples are intentionally omitted: only deterministic summary metrics are
    useful for the workbench and CI regression comparison, while the compact
    representation avoids a potentially large persisted Suite summary.
    """
    evidence: dict[str, Any] = {
        "warmup_runs": int(performance_config["warmup_runs"]),
        "num_iterations": int(performance_config["num_iterations"]),
    }
    if bool(performance_config["measure_runtime"]):
        runtime_seconds = _performance_aggregate(
            result,
            average_field="avg_run_time",
            median_field="median_run_time",
            p95_field="p95_run_time",
        )
        if runtime_seconds is None:
            return None
        evidence["runtime_seconds"] = runtime_seconds
    if bool(performance_config["measure_memory"]):
        memory_mib = _performance_aggregate(
            result,
            average_field="avg_memory_usage",
            median_field="median_memory_usage",
            p95_field="p95_memory_usage",
        )
        if memory_mib is None:
            return None
        evidence["memory_mib"] = memory_mib
    return evidence if len(evidence) > 2 else None


def _accuracy_verdict(result: Any) -> tuple[bool | None, str, float | None]:
    """Normalize ``AccuracyResult`` into a Case verdict, reason, and average.

    Unlike AgentAsJudge, Agno's AccuracyResult has no ``passed`` field. The
    stable aggregate is ``avg_score``; per-iteration ``results`` only provide
    explanatory score/reason evidence. A malformed or empty result is an eval
    error rather than a silent pass.
    """
    score = _accuracy_score(_result_value(result, "avg_score"))
    if score is None:
        return None, "Accuracy evaluation returned no valid average score", None

    reasons: list[str] = []
    rows = _result_value(result, "results")
    if isinstance(rows, (list, tuple)):
        for row in rows:
            reason = str(_result_value(row, "reason") or "").strip()
            if reason:
                reasons.append(reason)

    if score < _DEFAULT_ACCURACY_PASS_THRESHOLD:
        return (
            False,
            reasons[0]
            if reasons
            else (
                f"Accuracy average score {score:g}/10 is below required "
                f"{_DEFAULT_ACCURACY_PASS_THRESHOLD:g}/10"
            ),
            score,
        )
    return True, reasons[0] if reasons else "", score


def _judge_verdict(result: Any) -> tuple[bool | None, str, int | None]:
    """Return an AgentAsJudge verdict, reason, and numeric score when available.

    Agno reports failed judgments in ``results[*].passed`` rather than raising.
    Treat a missing/invalid result as an evaluation error so it cannot turn into a
    false safety pass in the suite summary.  The reason is retained for passing
    cases too: in numeric mode it is the evidence that explains score drift.
    """
    rows = _result_value(result, "results")
    if not isinstance(rows, (list, tuple)) or not rows:
        return None, "Agent-as-judge returned no verdict", None

    failures: list[str] = []
    reasons: list[str] = []
    score: int | None = None
    for row in rows:
        passed = _result_value(row, "passed")
        if not isinstance(passed, bool):
            return (
                None,
                "Agent-as-judge returned a verdict without a boolean passed field",
                None,
            )
        row_reason = str(_result_value(row, "reason") or "").strip()
        if row_reason:
            reasons.append(row_reason)
        if score is None:
            score = _judge_score(_result_value(row, "score"))
        if not passed:
            if row_reason:
                failures.append(row_reason)

    if failures:
        return False, failures[0], score
    if all(_result_value(row, "passed") is True for row in rows):
        return True, reasons[0] if reasons else "", score
    return False, "Agent-as-judge marked the case as failed", score


def _reliability_verdict(result: Any) -> tuple[bool | None, str]:
    """Normalize Agno's ReliabilityResult into a case-level verdict and reason."""
    raw_status = _result_value(result, "eval_status")
    if not isinstance(raw_status, str) or not raw_status.strip():
        return None, "Reliability evaluation returned no status"
    status = raw_status.strip().upper()
    if status == "PASSED":
        return True, ""
    if status != "FAILED":
        return None, f"Reliability evaluation returned unsupported status: {raw_status}"

    details: list[str] = []
    for field, label in (
        ("failed_tool_calls", "unexpected tools"),
        ("missing_tool_calls", "missing tools"),
        ("failed_argument_checks", "failed argument checks"),
    ):
        items = _reliability_evidence_items(_result_value(result, field))
        if items:
            details.append(f"{label}: {', '.join(items)}")
    suffix = f" ({'; '.join(details)})" if details else ""
    return False, f"Reliability check failed{suffix}"


def _reliability_evidence_items(value: Any) -> list[str]:
    """Keep only bounded Agno tool-name diagnostics.

    Agno's ``ReliabilityResult`` exposes lists of strings, but reject anything
    else at this boundary. That prevents malformed or historic result payloads
    from turning tool-argument objects into text in a Suite summary, report, or
    persisted error message.
    """
    if not isinstance(value, (list, tuple, set)):
        return []
    raw_values = [item for item in value if isinstance(item, str)]
    if isinstance(value, set):
        raw_values.sort()
    items: list[str] = []
    for raw_value in raw_values:
        item = raw_value.strip()
        if not item:
            continue
        if len(item) > _MAX_RELIABILITY_EVIDENCE_ITEM_CHARS:
            item = f"{item[: _MAX_RELIABILITY_EVIDENCE_ITEM_CHARS - 1]}…"
        items.append(item)
        if len(items) >= _MAX_RELIABILITY_EVIDENCE_ITEMS:
            break
    return items


def _reliability_evidence(result: Any) -> dict[str, list[str]] | None:
    """Return Agno ReliabilityResult diagnostics safe for Suite drill-down.

    These fields contain tool names and contract-match status only: never raw
    tool arguments, Case input, or model output. Bound the result before it is
    embedded in the persisted Suite summary and export artifact.
    """
    evidence: dict[str, list[str]] = {}
    for field in _RELIABILITY_EVIDENCE_FIELDS:
        items = _reliability_evidence_items(_result_value(result, field))
        if items:
            evidence[field] = items
    return evidence or None


def _record_case_check_issue(
    *,
    current_status: str,
    current_error_type: str,
    current_error_summary: str,
    status: str,
    error_type: str,
    error_summary: str,
) -> tuple[str, str, str]:
    """Merge a failed/unavailable check without hiding an earlier check result."""
    next_status = current_status
    next_error_type = current_error_type
    if current_status == "passed" or (status == "error" and current_status != "error"):
        next_status = status
        next_error_type = error_type
    elif error_type and error_type != current_error_type:
        next_error_type = "+".join(
            value for value in (current_error_type, error_type) if value
        )

    summary = error_summary.strip()
    if not current_error_summary or not summary:
        next_summary = current_error_summary or summary
    elif summary in current_error_summary:
        next_summary = current_error_summary
    else:
        next_summary = f"{current_error_summary}; {summary}"
    return next_status, next_error_type, next_summary


def _attach_case_evidence(
    result: dict[str, Any],
    *,
    started_at: float,
    accuracy_passed: bool | None,
    accuracy_reason: str | None,
    accuracy_score: float | None,
    judge_passed: bool | None,
    judge_reason: str | None,
    judge_score: int | None,
    reliability_passed: bool | None,
    reliability_evidence: dict[str, list[str]] | None,
    performance: dict[str, Any] | None,
    timed_out: bool = False,
    timeout_seconds: int | None = None,
    duration_seconds: float | None = None,
) -> dict[str, Any]:
    """Add the non-persisted CaseResult evidence used by suite summaries."""
    result["duration_seconds"] = (
        round(time.perf_counter() - started_at, 3)
        if duration_seconds is None
        else duration_seconds
    )
    result["accuracy_passed"] = accuracy_passed
    result["accuracy_reason"] = accuracy_reason
    result["accuracy_score"] = accuracy_score
    result["judge_passed"] = judge_passed
    result["judge_reason"] = judge_reason
    result["judge_score"] = judge_score
    result["reliability_passed"] = reliability_passed
    if safe_reliability_evidence := _reliability_evidence(reliability_evidence):
        result["reliability_evidence"] = safe_reliability_evidence
    if performance is not None:
        result["performance"] = performance
    result["timed_out"] = timed_out
    result["timeout_seconds"] = timeout_seconds
    return result


def _case_duration_seconds(started_at: float) -> float:
    """Return the one duration value shared by a Case result and checkpoint."""
    return round(time.perf_counter() - started_at, 3)


def _case_run_terminal_checkpoint(
    *,
    status: str,
    started_at: float,
    timeout_seconds: int,
    timed_out: bool,
    accuracy_passed: bool | None,
    accuracy_score: float | None,
    judge_passed: bool | None,
    judge_score: int | None,
    reliability_passed: bool | None,
    reliability_evidence: dict[str, list[str]] | None,
    performance: dict[str, Any] | None,
    judge_id: str,
    eval_profile: str,
) -> dict[str, Any]:
    """Build the private, bounded result evidence written with CaseRun status.

    Free-form evaluator reasons intentionally remain out of this checkpoint:
    an evaluator can put prompt/model content in a reason, while the durable
    recovery path only needs stable verdicts, scores, tool-name diagnostics,
    and performance aggregates.
    """
    return case_store.normalize_case_run_terminal_checkpoint(
        {
            "version": case_store.CASE_RUN_TERMINAL_CHECKPOINT_VERSION,
            "status": status,
            "duration_seconds": _case_duration_seconds(started_at),
            "timeout_seconds": timeout_seconds,
            "timed_out": timed_out,
            "accuracy_passed": accuracy_passed,
            "accuracy_score": accuracy_score,
            "judge_passed": judge_passed,
            "judge_score": judge_score,
            "reliability_passed": reliability_passed,
            "reliability_evidence": _reliability_evidence(reliability_evidence),
            "performance": performance,
            "judge_id": judge_id,
            "eval_profile": eval_profile,
        }
    )


async def _complete_case_result(
    *,
    case_run_id: str,
    case_run: Mapping[str, Any],
    case: Mapping[str, Any],
    target: EvalTarget,
    default_timeout: int,
    status: str,
    values: Mapping[str, Any],
    started_at: float,
    timeout_seconds: int,
    timed_out: bool,
    accuracy_passed: bool | None,
    accuracy_reason: str | None,
    accuracy_score: float | None,
    judge_passed: bool | None,
    judge_reason: str | None,
    judge_score: int | None,
    reliability_passed: bool | None,
    reliability_evidence: dict[str, list[str]] | None,
    performance: dict[str, Any] | None,
    judge_id: str,
    eval_profile: str,
    execution_lease: case_store.SuiteRunExecutionLease | None = None,
) -> dict[str, Any]:
    """Complete a CaseRun once, preserving a crash-safe full lite result."""
    checkpoint = _case_run_terminal_checkpoint(
        status=status,
        started_at=started_at,
        timeout_seconds=timeout_seconds,
        timed_out=timed_out,
        accuracy_passed=accuracy_passed,
        accuracy_score=accuracy_score,
        judge_passed=judge_passed,
        judge_score=judge_score,
        reliability_passed=reliability_passed,
        reliability_evidence=reliability_evidence,
        performance=performance,
        judge_id=judge_id,
        eval_profile=eval_profile,
    )
    # Keep the existing runner seam so older integrations which observe
    # ``mark_case_run`` still see one terminal write. The store recognises the
    # private checkpoint value and routes it through its one-way CAS operation.
    mark_kwargs: dict[str, Any] = {}
    if execution_lease is not None:
        mark_kwargs["execution_lease"] = execution_lease
    marked = await case_store.mark_case_run(
        case_run_id,
        status,
        {**dict(values), "terminal_checkpoint": checkpoint},
        **mark_kwargs,
    )
    if marked is None:
        # A stale writer must never manufacture a Suite summary row from its
        # unpersisted local result. Reuse only the immutable winner's compatible
        # checkpoint; otherwise surface the lease/race as an execution error.
        persisted = await case_store.get_case_run_private(case_run_id)
        recovered = (
            _recovered_case_result_lite(
                case=case,
                case_run=persisted,
                target=target,
                default_timeout=default_timeout,
            )
            if isinstance(persisted, Mapping)
            else None
        )
        if recovered is not None:
            return recovered
        if execution_lease is not None:
            raise JobLeaseLostError(
                "Eval CaseRun terminal checkpoint was rejected by a newer lease"
            )
        raise RuntimeError("Eval CaseRun terminal checkpoint was not committed by this worker")

    result = dict(marked)
    # Mocks and adapters may echo input values; never let the private
    # checkpoint leak through the runner result or Suite summary.
    result.pop("terminal_checkpoint", None)
    result["status"] = status
    _attach_case_evidence(
        result,
        started_at=started_at,
        duration_seconds=checkpoint["duration_seconds"],
        accuracy_passed=accuracy_passed,
        accuracy_reason=accuracy_reason,
        accuracy_score=accuracy_score,
        judge_passed=judge_passed,
        judge_reason=judge_reason,
        judge_score=judge_score,
        reliability_passed=reliability_passed,
        reliability_evidence=reliability_evidence,
        performance=performance,
        timed_out=timed_out,
        timeout_seconds=timeout_seconds,
    )
    result["eval_profile"] = eval_profile
    result["judge_id"] = judge_id
    return result


async def _resolve_judge_model(
    deps: AgentEvalRunnerDependencies,
    *,
    required: bool,
) -> tuple[Any | None, str]:
    """Resolve the configured evaluator model when this case needs one."""
    if not required:
        return None, ""
    mid = await _maybe_await(deps.get_eval_judge_model_id())
    config_id = str(mid or "").strip()
    return await _resolve_judge_model_config(deps, config_id, required=required)


async def _resolve_judge_model_config(
    deps: AgentEvalRunnerDependencies,
    config_id: str,
    *,
    required: bool,
) -> tuple[Any | None, str]:
    """Resolve one already-frozen evaluator model configuration id.

    Accuracy and AgentAsJudge must never fall back to an SDK/Agno process
    default: their model connection is part of the persisted evaluation
    contract.  Non-LLM evaluator-only cases can omit it.
    """
    config_id = str(config_id or "").strip()
    if not config_id:
        if required:
            raise ValueError(
                "尚未配置评测模型，请先在设置中添加并启用模型"
            )
        return None, ""
    try:
        config = await _maybe_await(deps.get_model_for_run(config_id))
        model = deps.build_agno_model(config)
        return model, config_id
    except Exception as exc:
        raise ValueError(f"评测模型不可用: {config_id}") from exc


def _security_request_for_case(
    case: Mapping[str, Any],
    *,
    target: EvalTarget,
    session_id: str,
    actor: Any,
) -> SecurityRunRequest:
    meta = _case_metadata(case)
    profile = eval_profile_from_metadata(meta)
    enable_tools = profile != "tools_off"
    return SecurityRunRequest.from_eval_args(
        str(case.get("input", "")),
        target=target.to_dict(),
        session_id=session_id,
        user_id=actor_id(actor),
        # Eval target capability resolution must use the same actor context
        # that queued the durable run.  Omitting these fields silently turns
        # every worker execution into the default ``user`` capability set.
        actor_role=actor_role(actor),
        actor_is_superuser=bool(getattr(actor, "is_superuser", False)),
        # Never inject or capture a real user's durable memories during evals.
        memory_enabled=False,
        enable_tools=enable_tools,
        # Avoid knowledge/live-search nondeterminism unless profile is full and case opts in.
        search_knowledge=bool(meta.get("search_knowledge")) if enable_tools else False,
    )


def _snapshot_target(value: object) -> EvalTarget:
    """Validate one private frozen target without consulting a live Suite."""
    if isinstance(value, EvalTarget):
        return value
    return parse_eval_target(value, require_available=False)


def _frozen_suite_execution(
    snapshot: Mapping[str, Any],
    *,
    suite_id: str,
) -> tuple[dict[str, Any], EvalTarget]:
    """Project a validated Suite-level snapshot into executable metadata.

    The durable job payload intentionally contains only IDs.  This helper is
    the boundary that binds a SuiteRun to its frozen target.  Case definitions
    are intentionally absent here: ordered CaseRun work items own that part of
    the immutable execution contract.
    """
    frozen = case_store.normalize_suite_run_execution_snapshot(snapshot)
    if not frozen:
        raise ValueError("Eval suite run is missing its execution_snapshot")

    normalized_suite_id = str(suite_id or "").strip()
    snapshot_suite_id = str(frozen["suite_id"] or "").strip()
    if snapshot_suite_id != normalized_suite_id:
        raise ValueError("Eval suite run execution_snapshot belongs to another Suite")

    target = _snapshot_target(frozen["target"])
    suite = {
        "id": snapshot_suite_id,
        "name": str(frozen.get("suite_name") or ""),
        "tags": list(frozen.get("suite_tags") or []),
        "target": target.to_dict(),
        # The Suite was checked as enabled before enqueue.  Its current
        # enabled flag is deliberately not reread by durable execution.
        "enabled": True,
    }
    return suite, target


def _frozen_suite_case_work_items(
    work_items: Sequence[Mapping[str, Any]],
    *,
    suite_id: str,
    target: EvalTarget,
    manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Validate and project the sole durable Case execution inputs.

    Each selected definition is stored exactly once on a pre-created CaseRun.
    Validating all cross-row invariants before issuing a target request makes a
    corrupt work-item set fail visibly instead of silently reading the editable
    Suite/Case tables or combining inputs from different queued executions.
    """
    if isinstance(work_items, (str, bytes)) or not isinstance(work_items, Sequence):
        raise ValueError("Eval suite run requires pre-created CaseRun work items")
    if not work_items:
        raise ValueError("Eval suite run has no pre-created CaseRun work items")

    manifest_actor = manifest.get("actor")
    if not isinstance(manifest_actor, Mapping):
        raise ValueError("Eval suite run execution manifest has no actor")
    actor_role_value = str(manifest_actor.get("role") or "").strip().lower()
    actor_is_superuser = manifest_actor.get("is_superuser")
    case_count = manifest.get("case_count")
    default_timeout = manifest.get("default_timeout")
    judge_model_config_id = str(manifest.get("judge_model_config_id") or "").strip()
    if (
        not isinstance(actor_is_superuser, bool)
        or not isinstance(case_count, int)
        or not isinstance(default_timeout, int)
    ):
        raise ValueError("Eval suite run execution manifest is invalid")
    if len(work_items) != case_count:
        raise ValueError(
            "Eval suite run CaseRun work-item count does not match its execution manifest"
        )

    cases: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for expected_index, raw_work_item in enumerate(work_items):
        if not isinstance(raw_work_item, Mapping):
            raise ValueError("Eval suite run CaseRun work item must be an object")
        work_item_index = raw_work_item.get("work_item_index")
        case_id = str(raw_work_item.get("case_id") or "").strip()
        if work_item_index != expected_index or not case_id:
            raise ValueError("Eval suite run CaseRun work items have invalid frozen order")
        if case_id in seen_case_ids:
            raise ValueError("Eval suite run CaseRun work items contain duplicate Cases")
        raw_definition = raw_work_item.get("definition_snapshot")
        if not isinstance(raw_definition, Mapping):
            raise ValueError("Eval suite run CaseRun work item has no definition snapshot")
        definition = case_store.build_case_run_definition_snapshot(
            raw_definition
        )
        if definition["id"] != case_id or definition["suite_id"] != suite_id:
            raise ValueError(
                "Eval suite run CaseRun work item definition does not match its Suite"
            )
        provenance = case_store.normalize_case_run_execution_provenance(
            raw_work_item.get("execution_provenance")
        )
        provenance_actor = provenance.get("actor")
        if (
            provenance.get("target") != target.to_dict()
            or not isinstance(provenance_actor, Mapping)
            or provenance_actor.get("role") != actor_role_value
            or provenance_actor.get("is_superuser") != actor_is_superuser
            or provenance.get("default_timeout_seconds") != default_timeout
            or str(provenance.get("judge_model_config_id") or "").strip()
            != judge_model_config_id
        ):
            raise ValueError(
                "Eval suite run CaseRun work item does not match its execution manifest"
            )
        cases.append(definition)
        seen_case_ids.add(case_id)
    return cases


def _case_execution_provenance(
    *,
    target: EvalTarget,
    actor: Any,
    definition_source: str,
    default_timeout: int,
    timeout_seconds: int,
    eval_profile: str,
    judge_model_config_id: str,
) -> dict[str, Any]:
    """Return private, bounded metadata explaining how a CaseRun was made."""
    return case_store.build_case_run_execution_provenance(
        target=target.to_dict(),
        actor_role_value=actor_role(actor),
        actor_is_superuser=bool(getattr(actor, "is_superuser", False)),
        definition_source=definition_source,
        default_timeout=default_timeout,
        timeout_seconds=timeout_seconds,
        eval_profile=eval_profile,
        # This is a configuration identifier rather than provider credentials
        # or raw model output; it is enough to investigate judge drift.
        judge_model_config_id=judge_model_config_id,
    )


def resolve_suite_concurrency(value: int | None = None) -> int:
    """Bounded suite parallelism (1.._MAX), sequential unless explicitly opted in."""
    if value is not None:
        raw = int(value)
    else:
        env = str(os.environ.get("TAIS_EVAL_SUITE_CONCURRENCY") or "").strip()
        try:
            raw = int(env) if env else _DEFAULT_SUITE_CONCURRENCY
        except ValueError:
            raw = _DEFAULT_SUITE_CONCURRENCY
    return max(1, min(raw, _MAX_SUITE_CONCURRENCY))


def _bounded_timeout_seconds(value: Any, *, fallback: int) -> int:
    """Return a positive, bounded timeout while tolerating legacy rows."""
    if isinstance(value, bool):
        return fallback
    try:
        raw = int(value)
    except (TypeError, ValueError):
        return fallback
    if raw < 1:
        return fallback
    return min(raw, _MAX_SUITE_TIMEOUT_SECONDS)


def resolve_suite_default_timeout(value: int | None = None) -> int:
    """Agno-compatible ``default_timeout`` with a safe server-side bound."""
    if value is None:
        return _DEFAULT_SUITE_TIMEOUT_SECONDS
    return _bounded_timeout_seconds(
        value,
        fallback=_DEFAULT_SUITE_TIMEOUT_SECONDS,
    )


def _case_timeout_seconds(case: Mapping[str, Any], default_timeout: int) -> int:
    """Case.timeout_seconds wins over the Suite's default_timeout."""
    raw_timeout = case.get("timeout_seconds")
    if raw_timeout is None:
        return default_timeout
    return _bounded_timeout_seconds(raw_timeout, fallback=default_timeout)


def _selected_case_tag(tag: str | None) -> str | None:
    if tag is None:
        return None
    normalized_tag = str(tag).strip()
    if not normalized_tag:
        raise ValueError("Eval case tag must not be blank")
    return normalized_tag


def _selected_case_name(name: str | None) -> str | None:
    if name is None:
        return None
    normalized_name = str(name).strip()
    if not normalized_name:
        raise ValueError("Eval case name must not be blank")
    return normalized_name


async def prepare_suite_run(
    suite_id: str,
    *,
    tag: str | None = None,
    name: str | None = None,
    default_timeout: int | None = None,
) -> dict[str, Any]:
    """Validate one immutable in-memory plan before it is atomically queued.

    The queue persists the private Suite/Case snapshot alongside the SuiteRun;
    the durable payload itself still contains only public IDs and selectors.
    """
    suite = await case_store.get_suite(suite_id)
    if suite is None:
        raise ValueError(f"Eval suite not found: {suite_id}")
    if not bool(suite.get("enabled", True)):
        raise ValueError(f"Eval suite is disabled: {suite_id}")
    target = target_from_suite(suite, require_available=False)
    selected_tag = _selected_case_tag(tag)
    selected_name = _selected_case_name(name)
    if selected_tag is not None and selected_name is not None:
        raise ValueError("Only one suite case selector may be provided: tag or name")

    if selected_tag is not None:
        cases_payload = await case_store.list_cases(suite_id=suite_id, tag=selected_tag)
    elif selected_name is not None:
        cases_payload = await case_store.list_cases(suite_id=suite_id, name=selected_name)
    else:
        cases_payload = await case_store.list_cases(suite_id=suite_id)
    cases = [dict(case) for case in cases_payload["data"] if isinstance(case, Mapping)]
    if selected_name is not None and len(cases) > 1:
        raise ValueError(
            f"Eval case name is ambiguous in suite {suite_id}: {selected_name!r} "
            f"matched {len(cases)} cases"
        )
    case_ids = [str(case.get("id") or "").strip() for case in cases]
    if any(not case_id for case_id in case_ids):
        raise ValueError("Eval suite contains a case missing id")
    # ``_suite`` and ``_cases`` are deliberately process-local implementation
    # details.  The atomic queue producer turns them into the private
    # SuiteRun snapshot, while the durable job contains only IDs.
    return {
        "suite_id": suite_id,
        "_suite": dict(suite),
        "_cases": cases,
        "target": target.to_dict(),
        "selected_tag": selected_tag,
        "selected_name": selected_name,
        "default_timeout": resolve_suite_default_timeout(default_timeout),
        "case_ids": case_ids,
    }


def initial_suite_run_summary(
    plan: Mapping[str, Any],
    *,
    concurrency: int | None = None,
) -> dict[str, Any]:
    """Return the privacy-safe progress shape written before worker claim."""
    case_ids = plan.get("case_ids")
    selected_cases = len(case_ids) if isinstance(case_ids, list) else 0
    target = plan.get("target")
    return {
        "passed": 0,
        "failed": 0,
        "errored": 0,
        "skipped": 0,
        "cancelled": 0,
        "total": selected_cases,
        "selected_tag": plan.get("selected_tag"),
        "selected_name": plan.get("selected_name"),
        "selected_cases": selected_cases,
        "completed_cases": 0,
        "default_timeout": resolve_suite_default_timeout(
            plan.get("default_timeout")
            if isinstance(plan.get("default_timeout"), int)
            else None
        ),
        "target": dict(target) if isinstance(target, Mapping) else {},
        "concurrency": resolve_suite_concurrency(concurrency),
    }


def _summary_case_count(status: str) -> str:
    if status == "passed":
        return "passed"
    if status == "failed":
        return "failed"
    if status == "skipped":
        return "skipped"
    if status == "cancelled":
        return "cancelled"
    return "errored"


def _case_result_lite(
    *,
    case: Mapping[str, Any],
    result: Mapping[str, Any] | None,
    status: str,
    error: str | None = None,
) -> dict[str, Any]:
    """Build one transient Agno-shaped CaseResult-lite runner row.

    When ``result`` is None (skipped / suite-level exception), pass ``error`` so
    operators see the real failure (e.g. ``db connection refused``) rather than a
    generic placeholder. Durable read/report paths instead derive their rows
    from the CaseRun terminal checkpoint.
    """
    case_name = str(case.get("name") or case.get("id") or "")
    case_id = str(case.get("id") or "")
    if result is None:
        if status == "error":
            err_text = str(error or "").strip() or "case run error"
        else:
            err_text = ""
        return {
            "name": case_name,
            "case_id": case_id,
            "case_run_id": "",
            "session_id": "",
            "duration_seconds": 0.0,
            "timeout_seconds": None,
            "status": status,
            "passed": status == "passed",
            "timed_out": False,
            "skipped": status == "skipped",
            "error_type": "",
            "error": err_text,
            "accuracy_passed": None,
            "accuracy_reason": None,
            "accuracy_score": None,
            "judge_passed": None,
            "judge_reason": None,
            "judge_score": None,
            "reliability_passed": None,
            "performance": None,
            "judge_id": "",
            "eval_profile": "",
        }
    # Prefer explicit error= override, then case_run error_summary.
    if status in {"failed", "error", "cancelled"}:
        err_text = str(error or result.get("error_summary") or "").strip()
    else:
        err_text = ""
    reliability_evidence = _reliability_evidence(result.get("reliability_evidence"))
    row = {
        "name": case_name,
        "case_id": case_id or str(result.get("case_id") or ""),
        "case_run_id": str(result.get("id") or ""),
        "session_id": str(result.get("session_id") or ""),
        "duration_seconds": result.get("duration_seconds"),
        "timeout_seconds": result.get("timeout_seconds"),
        "status": status,
        "passed": status == "passed",
        "timed_out": bool(result.get("timed_out", False)),
        "skipped": status == "skipped",
        "error_type": str(result.get("error_type") or ""),
        "error": err_text,
        "accuracy_passed": result.get("accuracy_passed"),
        "accuracy_reason": result.get("accuracy_reason"),
        "accuracy_score": result.get("accuracy_score"),
        "judge_passed": result.get("judge_passed"),
        "judge_reason": result.get("judge_reason"),
        "judge_score": result.get("judge_score"),
        "reliability_passed": result.get("reliability_passed"),
        "judge_id": str(result.get("judge_id") or ""),
        "eval_profile": str(result.get("eval_profile") or ""),
    }
    if reliability_evidence is not None:
        row["reliability_evidence"] = reliability_evidence
    performance = result.get("performance")
    if isinstance(performance, Mapping):
        row["performance"] = dict(performance)
    return row


def _recovered_case_result_lite(
    *,
    case: Mapping[str, Any],
    case_run: Mapping[str, Any],
    target: EvalTarget,
    default_timeout: int,
) -> dict[str, Any] | None:
    """Rebuild a safe checkpoint after a worker dies between two writes.

    The terminal CaseRun is authoritative only when it proves it executed the
    same frozen definition and target as this SuiteRun. New CaseRuns retain a
    compact private terminal checkpoint, so recovery can preserve verdicts and
    aggregates without rerunning an evaluator. Historical rows without one
    intentionally fall back to the limited safe projection below.
    """
    status = str(case_run.get("status") or "").strip()
    if status not in {"passed", "failed", "error", "cancelled", "skipped"}:
        return None
    case_id = str(case.get("id") or "").strip()
    if not case_id or str(case_run.get("case_id") or "").strip() != case_id:
        return None
    definition_snapshot = case_run.get("definition_snapshot")
    if not isinstance(definition_snapshot, Mapping):
        return None
    try:
        if case_store.build_case_run_definition_snapshot(
            definition_snapshot
        ) != case_store.build_case_run_definition_snapshot(case):
            return None
    except ValueError:
        return None

    provenance = case_run.get("execution_provenance")
    if not isinstance(provenance, Mapping):
        return None
    provenance_target = provenance.get("target")
    if not isinstance(provenance_target, Mapping):
        return None
    if dict(provenance_target) != target.to_dict():
        return None

    timeout_seconds = provenance.get("timeout_seconds")
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(float(timeout_seconds))
        or float(timeout_seconds) <= 0
    ):
        timeout_seconds = _case_timeout_seconds(case, default_timeout)
    error_summary = str(case_run.get("error_summary") or "").strip()
    error_type = str(case_run.get("error_type") or "").strip()
    raw_checkpoint = case_run.get("terminal_checkpoint")
    if isinstance(raw_checkpoint, Mapping) and raw_checkpoint:
        try:
            checkpoint = case_store.normalize_case_run_terminal_checkpoint(raw_checkpoint)
        except ValueError:
            checkpoint = None
        if (
            checkpoint is not None
            and checkpoint["status"] == status
            and checkpoint["timeout_seconds"] == timeout_seconds
            and (
                not str(provenance.get("eval_profile") or "")
                or checkpoint["eval_profile"]
                == str(provenance.get("eval_profile") or "")
            )
        ):
            row = {
                "name": str(case.get("name") or case_id),
                "case_id": case_id,
                "case_run_id": str(case_run.get("id") or ""),
                "session_id": str(case_run.get("session_id") or ""),
                "duration_seconds": checkpoint["duration_seconds"],
                "timeout_seconds": checkpoint["timeout_seconds"],
                "status": status,
                "passed": status == "passed",
                "timed_out": checkpoint["timed_out"],
                "skipped": status == "skipped",
                "error_type": error_type,
                "error": (
                    error_summary
                    if status in {"failed", "error", "cancelled"}
                    else ""
                ),
                "accuracy_passed": checkpoint["accuracy_passed"],
                "accuracy_reason": None,
                "accuracy_score": checkpoint["accuracy_score"],
                "judge_passed": checkpoint["judge_passed"],
                "judge_reason": None,
                "judge_score": checkpoint["judge_score"],
                "reliability_passed": checkpoint["reliability_passed"],
                "performance": checkpoint["performance"],
                "judge_id": checkpoint["judge_id"],
                "eval_profile": checkpoint["eval_profile"],
            }
            if checkpoint["reliability_evidence"] is not None:
                row["reliability_evidence"] = checkpoint["reliability_evidence"]
            return row
    return {
        "name": str(case.get("name") or case_id),
        "case_id": case_id,
        "case_run_id": str(case_run.get("id") or ""),
        "session_id": str(case_run.get("session_id") or ""),
        "duration_seconds": None,
        "timeout_seconds": timeout_seconds,
        "status": status,
        "passed": status == "passed",
        "timed_out": error_type == "EvalCaseTimeout",
        "skipped": status == "skipped",
        "error_type": error_type,
        "error": (
            error_summary if status in {"failed", "error", "cancelled"} else ""
        ),
        "accuracy_passed": None,
        "accuracy_reason": None,
        "accuracy_score": None,
        "judge_passed": None,
        "judge_reason": None,
        "judge_score": None,
        "reliability_passed": None,
        "performance": None,
        "judge_id": "",
        "eval_profile": str(provenance.get("eval_profile") or ""),
    }


async def run_case(
    case_id: str,
    actor: Any,
    suite_run_id: str | None = None,
    replay_of_case_run_id: str | None = None,
    dependencies: AgentEvalRunnerDependencies | None = None,
    *,
    judge_model_bundle: tuple[Any | None, str] | None = None,
    default_timeout: int | None = None,
    cancellation_event: SuiteRunCancellationEvent = None,
    definition_snapshot: Mapping[str, Any] | None = None,
    frozen_target: EvalTarget | Mapping[str, Any] | None = None,
    replay_from_snapshot: bool = False,
    execution_lease: case_store.SuiteRunExecutionLease | None = None,
    abort_event: asyncio.Event | None = None,
    execution_definition_source: str | None = None,
) -> dict[str, Any]:
    if abort_event is not None and abort_event.is_set():
        raise JobLeaseLostError("Eval suite worker lost its durable job lease")
    deps = dependencies or AgentEvalRunnerDependencies()
    normalized_case_id = str(case_id or "").strip()
    if not normalized_case_id:
        raise ValueError("case_id is required")
    if definition_snapshot is None:
        live_case = await case_store.get_case(normalized_case_id)
        if live_case is None:
            raise ValueError(f"Eval case not found: {normalized_case_id}")
        case = case_store.build_case_run_definition_snapshot(live_case)
        suite_id = str(case.get("suite_id") or "").strip()
        if not suite_id:
            raise ValueError(f"Eval case has no suite_id: {normalized_case_id}")
        suite = await case_store.get_suite(suite_id)
        if suite is None:
            raise ValueError(f"Eval suite not found: {suite_id}")
        # Validate identity here without making a feature-flag transition look
        # like an absent Suite. ``from_eval_args`` checks runtime availability
        # inside the durable CaseRun lifecycle.
        target = target_from_suite(suite, require_available=False)
        definition_source = "live_case"
    else:
        case = case_store.build_case_run_definition_snapshot(definition_snapshot)
        if case["id"] != normalized_case_id:
            raise ValueError("Frozen Case definition does not match case_id")
        if frozen_target is None:
            raise ValueError("Frozen Case execution requires a frozen target")
        target = _snapshot_target(frozen_target)
        definition_source = execution_definition_source or (
            "replay_snapshot" if replay_from_snapshot else "suite_execution_snapshot"
        )

    if not bool(case.get("enabled", True)):
        raise ValueError(f"Eval case is disabled: {normalized_case_id}")
    # The durable CaseRun is evidence of a real evaluation attempt. Reject a
    # malformed stored definition before allocating it, rather than silently
    # defaulting to Accuracy or leaving a queued row after validation fails.
    enabled_eval_types = _eval_types(case)
    requires_evaluator_model = bool(enabled_eval_types & _LLM_EVALUATOR_TYPES)
    # A performance Case is an intentionally repeated target invocation.
    # Validate its complete bounded contract before creating a durable run so a
    # corrupt historical row cannot become a queued execution error.
    performance_config = (
        case_store.normalize_performance_config(case.get("performance_config"))
        if "performance" in enabled_eval_types
        else None
    )

    case_meta = _case_metadata(case)
    eval_profile = eval_profile_from_metadata(case_meta)
    resolved_default_timeout = resolve_suite_default_timeout(default_timeout)
    timeout_seconds = _case_timeout_seconds(case, resolved_default_timeout)
    if judge_model_bundle is not None:
        judge_model, judge_model_config_id = judge_model_bundle
    else:
        judge_model, judge_model_config_id = await _resolve_judge_model(
            deps,
            required=requires_evaluator_model,
        )

    execution_provenance = _case_execution_provenance(
        target=target,
        actor=actor,
        definition_source=definition_source,
        default_timeout=resolved_default_timeout,
        timeout_seconds=timeout_seconds,
        eval_profile=eval_profile,
        judge_model_config_id=judge_model_config_id,
    )
    if execution_lease is None:
        case_run = await case_store.create_case_run(
            normalized_case_id,
            suite_run_id=suite_run_id,
            replay_of_case_run_id=replay_of_case_run_id,
            definition_snapshot=case,
            execution_provenance=execution_provenance,
            replay_from_snapshot=replay_from_snapshot,
        )
    else:
        if not suite_run_id:
            raise ValueError("fenced CaseRun requires a suite_run_id")
        claim = await case_store.claim_suite_case_run(
            normalized_case_id,
            suite_run_id=suite_run_id,
            definition_snapshot=case,
            execution_provenance=execution_provenance,
            execution_lease=execution_lease,
        )
        if claim is None:
            raise JobLeaseLostError("Eval CaseRun claim was rejected by a newer lease")
        case_run = claim.case_run
        if not claim.acquired:
            recovered = _recovered_case_result_lite(
                case=case,
                case_run=case_run,
                target=target,
                default_timeout=resolved_default_timeout,
            )
            if recovered is not None:
                return recovered
            raise JobLeaseLostError("Eval CaseRun is already owned by this lease")
        # A takeover reuses the logical CaseRun row, whose provenance is
        # deliberately immutable. Honor the evaluator model it froze instead
        # of silently grading a resumed Case with today's settings.
        frozen_provenance = case_run.get("execution_provenance")
        if isinstance(frozen_provenance, Mapping):
            frozen_judge_model_config_id = str(
                frozen_provenance.get("judge_model_config_id") or ""
            ).strip()
            if frozen_judge_model_config_id != judge_model_config_id:
                judge_model, judge_model_config_id = await _resolve_judge_model_config(
                    deps,
                    frozen_judge_model_config_id,
                    required=requires_evaluator_model,
                )
    case_run_id = str(case_run["id"])
    session_id = _case_session_id(
        case_run_id,
        lease_epoch=(execution_lease.lease_epoch if execution_lease is not None else None),
    )
    eval_run_ids: list[str] = []
    response: Any | None = None
    case_status = "passed"
    case_error_type = ""
    case_error_summary = ""
    accuracy_passed: bool | None = None
    accuracy_reason: str | None = None
    accuracy_score: float | None = None
    judge_passed: bool | None = None
    judge_reason: str | None = None
    judge_score: int | None = None
    reliability_passed: bool | None = None
    reliability_evidence: dict[str, list[str]] | None = None
    performance_evidence: dict[str, Any] | None = None
    started_at = time.perf_counter()
    timed_out = False
    timeout_handle: asyncio.TimerHandle | None = None
    running_task = asyncio.current_task()
    cancellation_waiter: asyncio.Task[None] | None = None

    def _expire_case() -> None:
        nonlocal timed_out
        timed_out = True
        if running_task is not None and not running_task.done():
            running_task.cancel()

    timeout_handle = asyncio.get_running_loop().call_later(
        timeout_seconds,
        _expire_case,
    )

    if cancellation_event is not None:

        async def _cancel_when_requested() -> None:
            await cancellation_event.wait()
            if running_task is not None and not running_task.done():
                running_task.cancel()

        cancellation_waiter = asyncio.create_task(
            _cancel_when_requested(),
            name=f"eval-case-cancel-watch:{case_run_id}",
        )
    judge_resolved: dict[str, Any] = {"judge_id": ""}

    try:
        eval_db = await _maybe_await(deps.get_eval_db())
        judge_resolved = resolve_case_judge_criteria(
            case,
            judge_model_config_id=judge_model_config_id,
        )
        request = _security_request_for_case(
            case,
            target=target,
            session_id=session_id,
            actor=actor,
        )
        target_context = (
            deps.security_runtime.team_context(request)
            if target.kind == "team"
            else deps.security_runtime.security_agent_context(request)
        )
        async with target_context as agent:
            # A Suite Case has one Agent response. Reuse it for every
            # response-based check so Accuracy, Judge, and Reliability gate the
            # same behavior (and do not multiply the model/tool side effects).
            # ``AccuracyEval.arun_with_output`` is Agno's supported path for
            # grading an already-produced output.
            if enabled_eval_types & {"accuracy", "agent_as_judge", "reliability"}:
                response = await agent.arun(
                    case.get("input", ""),
                    session_id=session_id,
                    user_id=actor_id(actor),
                    stream=False,
                )
                _require_completed_subject_response(response)

            if "accuracy" in enabled_eval_types:
                accuracy_kwargs: dict[str, Any] = {
                    "input": case.get("input", ""),
                    "expected_output": case.get("expected_output", ""),
                    "name": case.get("name"),
                    "db": eval_db,
                }
                if target.kind == "team":
                    accuracy_kwargs["team"] = agent
                else:
                    accuracy_kwargs["agent"] = agent
                if judge_resolved["additional_guidelines"]:
                    accuracy_kwargs["additional_guidelines"] = judge_resolved[
                        "additional_guidelines"
                    ]
                # Keep all LLM-based Eval dimensions on the configured
                # evaluator model. Otherwise Accuracy silently falls back to
                # Agno's process default while Agent-as-Judge uses the
                # explicitly selected eval judge.
                if judge_model is None:
                    raise RuntimeError("评测模型未解析")
                accuracy_kwargs["model"] = judge_model
                accuracy_eval = deps.accuracy_eval_cls(**accuracy_kwargs)
                accuracy_result = await accuracy_eval.arun_with_output(
                    output=_response_value(response, "content"),
                    print_summary=False,
                    print_results=False,
                )
                accuracy_passed, accuracy_reason, accuracy_score = _accuracy_verdict(
                    accuracy_result
                )
                if accuracy_passed is False:
                    case_status, case_error_type, case_error_summary = (
                        _record_case_check_issue(
                            current_status=case_status,
                            current_error_type=case_error_type,
                            current_error_summary=case_error_summary,
                            status="failed",
                            error_type="AccuracyFailed",
                            error_summary=accuracy_reason
                            or "Accuracy average score did not meet the pass threshold",
                        )
                    )
                elif accuracy_passed is None:
                    case_status, case_error_type, case_error_summary = (
                        _record_case_check_issue(
                            current_status=case_status,
                            current_error_type=case_error_type,
                            current_error_summary=case_error_summary,
                            status="error",
                            error_type="AccuracyResultUnavailable",
                            error_summary=accuracy_reason
                            or "Accuracy evaluation returned no valid result",
                        )
                    )
                if eval_id := _eval_id(accuracy_eval, accuracy_result):
                    eval_run_ids.append(eval_id)

            if "agent_as_judge" in enabled_eval_types:
                judge_kwargs: dict[str, Any] = {
                    "criteria": judge_resolved["criteria"] or case.get("criteria", ""),
                    "threshold": judge_resolved["threshold"],
                    "scoring_strategy": judge_resolved.get("scoring_strategy")
                    or "binary",
                    "name": case.get("name"),
                    "db": eval_db,
                }
                if judge_resolved["additional_guidelines"]:
                    judge_kwargs["additional_guidelines"] = judge_resolved[
                        "additional_guidelines"
                    ]
                if judge_model is None:
                    raise RuntimeError("评测模型未解析")
                judge_kwargs["model"] = judge_model
                judge_eval = deps.judge_eval_cls(**judge_kwargs)
                judge_result = await judge_eval.arun(
                    input=case.get("input", ""),
                    output=str(getattr(response, "content", "")),
                    print_summary=False,
                    print_results=False,
                )
                judge_passed, judge_reason, judge_score = _judge_verdict(judge_result)
                if judge_passed is False:
                    case_status, case_error_type, case_error_summary = (
                        _record_case_check_issue(
                            current_status=case_status,
                            current_error_type=case_error_type,
                            current_error_summary=case_error_summary,
                            status="failed",
                            error_type="JudgeFailed",
                            error_summary=(
                                judge_reason
                                or "Agent-as-judge marked the case as failed"
                            ),
                        )
                    )
                elif judge_passed is None:
                    case_status, case_error_type, case_error_summary = (
                        _record_case_check_issue(
                            current_status=case_status,
                            current_error_type=case_error_type,
                            current_error_summary=case_error_summary,
                            status="error",
                            error_type="JudgeResultUnavailable",
                            error_summary=judge_reason
                            or "Agent-as-judge returned no verdict",
                        )
                    )
                if eval_id := _eval_id(judge_eval, judge_result):
                    eval_run_ids.append(eval_id)

            if "reliability" in enabled_eval_types:
                reliability_kwargs: dict[str, Any] = {
                    "name": case.get("name"),
                    "expected_tool_calls": case.get("expected_tool_calls", []),
                    "allow_additional_tool_calls": case.get(
                        "allow_additional_tool_calls", True
                    ),
                    "expected_tool_call_arguments": case.get(
                        "expected_tool_call_arguments", {}
                    ),
                    "db": eval_db,
                }
                if target.kind == "team":
                    reliability_kwargs["team_response"] = response
                else:
                    reliability_kwargs["agent_response"] = response
                reliability_eval = deps.reliability_eval_cls(**reliability_kwargs)
                reliability_result = await reliability_eval.arun(print_results=False)
                reliability_passed, reliability_reason = _reliability_verdict(
                    reliability_result
                )
                reliability_evidence = _reliability_evidence(reliability_result)
                if reliability_passed is False:
                    case_status, case_error_type, case_error_summary = (
                        _record_case_check_issue(
                            current_status=case_status,
                            current_error_type=case_error_type,
                            current_error_summary=case_error_summary,
                            status="failed",
                            error_type="ReliabilityFailed",
                            error_summary=reliability_reason,
                        )
                    )
                elif reliability_passed is None:
                    case_status, case_error_type, case_error_summary = (
                        _record_case_check_issue(
                            current_status=case_status,
                            current_error_type=case_error_type,
                            current_error_summary=case_error_summary,
                            status="error",
                            error_type="ReliabilityResultUnavailable",
                            error_summary=reliability_reason,
                        )
                    )
                if eval_id := _eval_id(reliability_eval, reliability_result):
                    eval_run_ids.append(eval_id)

            if "performance" in enabled_eval_types:

                performance_sample_index = 0

                async def performance_func() -> Any:
                    nonlocal performance_sample_index
                    performance_sample_index += 1
                    # Agno invokes this callback once per warm-up and once per
                    # enabled metric sample.  Reusing the Case session would
                    # turn later measurements into a multi-turn conversation,
                    # contaminating both latency and correctness.  A CaseRun
                    # ID is already unique, so a deterministic sample suffix
                    # gives each measurement a clean, traceable session.
                    sample_response = await agent.arun(
                        case.get("input", ""),
                        session_id=(
                            f"{session_id}_performance_{performance_sample_index}"
                        ),
                        user_id=actor_id(actor),
                        stream=False,
                    )
                    _require_completed_subject_response(sample_response)
                    return sample_response

                assert performance_config is not None
                performance_eval = deps.performance_eval_cls(
                    func=performance_func,
                    name=case.get("name"),
                    db=eval_db,
                    warmup_runs=int(performance_config["warmup_runs"]),
                    num_iterations=int(performance_config["num_iterations"]),
                    measure_runtime=bool(performance_config["measure_runtime"]),
                    measure_memory=bool(performance_config["measure_memory"]),
                )
                performance_result = await performance_eval.arun(
                    print_summary=False,
                    print_results=False,
                )
                if eval_id := _eval_id(performance_eval, performance_result):
                    eval_run_ids.append(eval_id)
                performance_evidence = _performance_evidence(
                    performance_result,
                    performance_config,
                )
                if performance_evidence is None:
                    raise ValueError(
                        "Performance evaluation returned no valid aggregate metrics"
                    )

        # Timeout guards execution and checks, but never the durable result
        # write. A slow DB write must not leave a completed CaseRun queued.
        timeout_handle.cancel()
        timeout_handle = None
        values = {
            "session_id": session_id,
            "agno_eval_run_ids": eval_run_ids,
            "agent_run_id": _response_value(response, "run_id"),
            "trace_id": _response_value(response, "trace_id"),
        }
        if case_status != "passed":
            values["error_type"] = case_error_type
            values["error_summary"] = case_error_summary
        return await _complete_case_result(
            case_run_id=case_run_id,
            case_run=case_run,
            case=case,
            target=target,
            default_timeout=resolved_default_timeout,
            status=case_status,
            values=values,
            started_at=started_at,
            timeout_seconds=timeout_seconds,
            timed_out=False,
            accuracy_passed=accuracy_passed,
            accuracy_reason=accuracy_reason,
            accuracy_score=accuracy_score,
            judge_passed=judge_passed,
            judge_reason=judge_reason,
            judge_score=judge_score,
            reliability_passed=reliability_passed,
            reliability_evidence=reliability_evidence,
            performance=performance_evidence,
            judge_id=judge_resolved["judge_id"],
            eval_profile=eval_profile,
            execution_lease=execution_lease,
        )
    except asyncio.CancelledError:
        if abort_event is not None and abort_event.is_set():
            # Lease loss is not an operator cancellation.  Do not consume the
            # CaseRun's one write-once checkpoint with a cancelled result;
            # the newer fence must be able to take it over.
            raise JobLeaseLostError("Eval suite worker lost its durable job lease")
        cancelled_by_suite = (
            cancellation_event is not None and cancellation_event.is_set()
        )
        if not timed_out and not cancelled_by_suite:
            raise
        if timed_out:
            status = "error"
            error_type = "EvalCaseTimeout"
            error_summary = f"Eval case exceeded timeout of {timeout_seconds} seconds"
        else:
            status = "cancelled"
            error_type = "EvalCaseCancelled"
            error_summary = "Eval suite run was cancelled"
        values = {
            "session_id": session_id,
            "agno_eval_run_ids": eval_run_ids,
            "error_type": error_type,
            "error_summary": error_summary,
        }
        return await _complete_case_result(
            case_run_id=case_run_id,
            case_run=case_run,
            case=case,
            target=target,
            default_timeout=resolved_default_timeout,
            status=status,
            values=values,
            started_at=started_at,
            timeout_seconds=timeout_seconds,
            timed_out=timed_out,
            accuracy_passed=accuracy_passed,
            accuracy_reason=accuracy_reason,
            accuracy_score=accuracy_score,
            judge_passed=judge_passed,
            judge_reason=judge_reason,
            judge_score=judge_score,
            reliability_passed=reliability_passed,
            reliability_evidence=reliability_evidence,
            performance=performance_evidence,
            judge_id=judge_resolved["judge_id"],
            eval_profile=eval_profile,
            execution_lease=execution_lease,
        )
    except JobLeaseLostError:
        raise
    except Exception as exc:
        error_type = type(exc).__name__
        error_summary = str(exc)
        guardrail_error = is_input_check_error(exc)
        if guardrail_error:
            error_type = "InputCheckError"
            code = getattr(exc, "error_id", None) or getattr(exc, "trigger", None)
            if code:
                error_summary = f"GUARDRAIL_{str(code).upper()}: {exc}"
            else:
                error_summary = f"GUARDRAIL_BLOCKED: {exc}"
        # A failed assertion/verdict is a product regression; an exception is
        # an execution error. Keep guardrail rejections as failed Case runs so
        # their dedicated safety bucket remains an intentional gate outcome.
        case_status = "failed" if guardrail_error else "error"
        values = {
            "session_id": session_id,
            "agent_run_id": _response_value(response, "run_id"),
            "trace_id": _response_value(response, "trace_id"),
            "agno_eval_run_ids": eval_run_ids,
            "error_type": error_type,
            "error_summary": error_summary,
        }
        return await _complete_case_result(
            case_run_id=case_run_id,
            case_run=case_run,
            case=case,
            target=target,
            default_timeout=resolved_default_timeout,
            status=case_status,
            values=values,
            started_at=started_at,
            timeout_seconds=timeout_seconds,
            timed_out=False,
            accuracy_passed=accuracy_passed,
            accuracy_reason=accuracy_reason,
            accuracy_score=accuracy_score,
            judge_passed=judge_passed,
            judge_reason=judge_reason,
            judge_score=judge_score,
            reliability_passed=reliability_passed,
            reliability_evidence=reliability_evidence,
            performance=performance_evidence,
            judge_id=judge_resolved["judge_id"],
            eval_profile=eval_profile,
            execution_lease=execution_lease,
        )
    finally:
        if timeout_handle is not None:
            timeout_handle.cancel()
        if cancellation_waiter is not None:
            cancellation_waiter.cancel()
            try:
                await cancellation_waiter
            except asyncio.CancelledError:
                pass


async def _execute_claimed_suite_run(
    *,
    suite_run: Mapping[str, Any],
    actor: Any,
    execution_snapshot: Mapping[str, Any],
    case_work_items: Sequence[Mapping[str, Any]],
    execution_lease: case_store.SuiteRunExecutionLease,
    dependencies: AgentEvalRunnerDependencies | None = None,
    concurrency: int | None = None,
    cancellation_event: SuiteRunCancellationEvent = None,
    abort_event: asyncio.Event | None = None,
) -> dict[str, Any]:
    """Execute one already-claimed durable SuiteRun from immutable work items.

    Suite execution has exactly one production state machine:
    ``enqueue_suite_run`` atomically creates the SuiteRun, every ordered
    CaseRun work item, and its durable job; a worker then claims that job and
    enters this function.  The runner never constructs a SuiteRun or CaseRun
    while executing, which keeps report/recovery evidence identical to the
    selected Agno ``Case`` population.
    """
    if abort_event is not None and abort_event.is_set():
        raise JobLeaseLostError("Eval suite worker lost its durable job lease")
    suite_run_id = str(suite_run.get("id") or "").strip()
    if not suite_run_id:
        raise ValueError("claimed Eval SuiteRun is missing id")
    deps = dependencies or AgentEvalRunnerDependencies()
    manifest = case_store.suite_run_execution_manifest(execution_snapshot)
    manifest_actor = manifest["actor"]
    if (
        actor_id(actor).strip() != str(manifest_actor["id"])
        or actor_role(actor).strip().lower() != str(manifest_actor["role"])
        or bool(getattr(actor, "is_superuser", False))
        is not bool(manifest_actor["is_superuser"])
    ):
        raise ValueError("Eval suite worker actor does not match its execution manifest")
    suite_id = str(execution_snapshot.get("suite_id") or "").strip()
    if not suite_id or str(suite_run.get("suite_id") or "").strip() != suite_id:
        raise ValueError("Eval suite run execution snapshot belongs to another Suite")
    if str(suite_run.get("started_by") or "").strip() != str(
        manifest_actor["id"]
    ).strip():
        raise ValueError("Eval suite run starter does not match its execution manifest")
    suite, target = _frozen_suite_execution(
        execution_snapshot,
        suite_id=suite_id,
    )
    selected_tag = manifest["selected_tag"]
    selected_name = manifest["selected_name"]
    resolved_default_timeout = int(manifest["default_timeout"])
    judge_model_config_id = str(manifest["judge_model_config_id"] or "").strip()
    cases = _frozen_suite_case_work_items(
        case_work_items,
        suite_id=suite_id,
        target=target,
        manifest=manifest,
    )

    frozen_case_ids = [str(case["id"] or "").strip() for case in cases]
    plan = {
        "suite_id": suite_id,
        "target": target.to_dict(),
        "selected_tag": selected_tag,
        "selected_name": selected_name,
        "default_timeout": resolved_default_timeout,
        "case_ids": frozen_case_ids,
    }

    initial_summary = initial_suite_run_summary(plan, concurrency=concurrency)
    existing_summary = suite_run.get("summary")
    summary = {
        **initial_summary,
        **(dict(existing_summary) if isinstance(existing_summary, Mapping) else {}),
    }
    existing_status = str(suite_run.get("status") or "")
    if existing_status not in {"running", "cancelling"}:
        raise JobLeaseLostError(
            "Eval SuiteRun execution claim was lost before case execution"
        )

    limit = resolve_suite_concurrency(concurrency)
    semaphore = asyncio.Semaphore(limit)

    # Per-Case results live exclusively on CaseRun.  A queued v2 SuiteRun
    # cannot carry a second eventually-consistent result array.
    if "cases" in summary:
        raise ValueError("Eval SuiteRun summary must not embed Case results")
    stored_by_case_id: dict[str, dict[str, Any]] = {}

    frozen_cases_by_id = {str(case.get("id") or "").strip(): case for case in cases}
    work_items_by_case_id = {
        str(item.get("case_id") or "").strip(): item for item in case_work_items
    }
    # Cancellation only prevents new target invocations.  A CaseRun that
    # already committed an evaluator checkpoint before the corresponding
    # SuiteRun progress write is a completed observation, not an unstarted
    # Case to reclassify as skipped during recovery.
    recovered_by_case_id: dict[str, dict[str, Any]] = {}
    for terminal_row in case_work_items:
        case_id = str(terminal_row.get("case_id") or "").strip()
        case = frozen_cases_by_id.get(case_id)
        if case is None:
            continue
        recovered = _recovered_case_result_lite(
            case=case,
            case_run=terminal_row,
            target=target,
            default_timeout=resolved_default_timeout,
        )
        if recovered is None:
            continue
        if case_id in recovered_by_case_id:
            raise ValueError(
                "Eval suite recovery found multiple compatible terminal "
                f"CaseRuns for frozen case {case_id}"
            )
        # ``_recovered_case_result_lite`` validates the frozen definition and
        # provenance before returning either checkpoint evidence or a safe
        # generic terminal fallback (for example a cancelled Case).
        recovered_by_case_id[case_id] = recovered
    stored_by_case_id.update(recovered_by_case_id)

    async def _terminalize_pending_case(
        case: Mapping[str, Any],
        *,
        status: str,
        error_type: str,
        error_summary: str,
    ) -> dict[str, Any]:
        """Persist a non-invoked Case outcome as the CaseRun source of truth."""
        case_id = str(case.get("id") or "").strip()
        case_meta = (
            case.get("metadata") if isinstance(case.get("metadata"), dict) else {}
        )
        if not case_id:
            raise ValueError("Eval SuiteRun work item is missing case_id")
        work_item = work_items_by_case_id.get(case_id)
        if work_item is None:
            raise ValueError(
                f"Eval SuiteRun is missing the frozen CaseRun work item for {case_id}"
            )
        provenance = work_item.get("execution_provenance")
        if not isinstance(provenance, Mapping):
            raise ValueError(
                f"Eval SuiteRun CaseRun work item has no provenance for {case_id}"
            )

        async def _complete_pending(case_run: Mapping[str, Any]) -> dict[str, Any]:
            """Write a checkpoint even when the target was never invoked."""
            return await _complete_case_result(
                case_run_id=str(case_run["id"]),
                case_run=case_run,
                case=case,
                target=target,
                default_timeout=resolved_default_timeout,
                status=status,
                values={
                    "error_type": error_type,
                    "error_summary": error_summary,
                },
                started_at=time.perf_counter(),
                timeout_seconds=_case_timeout_seconds(case, resolved_default_timeout),
                timed_out=False,
                accuracy_passed=None,
                accuracy_reason=None,
                accuracy_score=None,
                judge_passed=None,
                judge_reason=None,
                judge_score=None,
                reliability_passed=None,
                reliability_evidence=None,
                performance=None,
                judge_id="",
                eval_profile=eval_profile_from_metadata(case_meta),
                execution_lease=execution_lease,
            )

        claim = await case_store.claim_suite_case_run(
            case_id,
            suite_run_id=suite_run_id,
            definition_snapshot=case,
            execution_provenance=provenance,
            execution_lease=execution_lease,
        )
        if claim is None:
            raise JobLeaseLostError(
                "Eval pending CaseRun claim was rejected by a newer lease"
            )
        if claim.acquired:
            result = await _complete_pending(claim.case_run)
        else:
            existing = dict(claim.case_run)
            if str(existing.get("status") or "") in {
                "passed",
                "failed",
                "error",
                "cancelled",
                "skipped",
            }:
                result = existing
            else:
                result = await _complete_pending(existing)
        return {
            "kind": "result",
            "case": case,
            "case_meta": case_meta,
            "result": result,
            "error": error_summary,
        }

    async def _run_one(case: Mapping[str, Any]) -> dict[str, Any]:
        case_id = str(case.get("id", ""))
        case_meta = (
            case.get("metadata") if isinstance(case.get("metadata"), dict) else {}
        )
        if cancellation_event is not None and cancellation_event.is_set():
            return await _terminalize_pending_case(
                case,
                status="skipped",
                error_type="EvalSuiteCancelled",
                error_summary="Eval suite run was cancelled before this case started",
            )
        if not case_id:
            return {
                "kind": "error",
                "case": case,
                "case_meta": case_meta,
                "result": None,
                "error": "Eval case missing id",
            }
        if not bool(case.get("enabled", True)):
            return await _terminalize_pending_case(
                case,
                status="skipped",
                error_type="EvalCaseDisabled",
                error_summary="Eval case was disabled before this suite run started",
            )
        async with semaphore:
            if cancellation_event is not None and cancellation_event.is_set():
                return await _terminalize_pending_case(
                    case,
                    status="skipped",
                    error_type="EvalSuiteCancelled",
                    error_summary="Eval suite run was cancelled before this case started",
                )
            try:
                result = await run_case(
                    case_id,
                    actor=actor,
                    suite_run_id=suite_run_id,
                    dependencies=deps,
                    judge_model_bundle=judge_model_bundle,
                    default_timeout=resolved_default_timeout,
                    cancellation_event=cancellation_event,
                    definition_snapshot=case,
                    frozen_target=target,
                    execution_lease=execution_lease,
                    abort_event=abort_event,
                    execution_definition_source="suite_case_work_item",
                )
            except JobLeaseLostError:
                raise
            except Exception as exc:
                logger.exception(
                    "Eval suite {} case {} failed during suite run {}",
                    suite_id,
                    case_id,
                    suite_run_id,
                )
                return await _terminalize_pending_case(
                    case,
                    status="error",
                    error_type=type(exc).__name__,
                    error_summary=str(exc),
                )
            return {
                "kind": "result",
                "case": case,
                "case_meta": case_meta,
                "result": result,
            }

    # Resolve the judge once for every active execution batch.  Rows already
    # persisted before a lease recovery do not need a second evaluator model.
    pending_indexes = [
        index
        for index, case in enumerate(cases)
        if str(case.get("id") or "") not in stored_by_case_id
    ]
    # Disabled work items still need a durable ``skipped`` checkpoint, but
    # they never invoke an evaluator. Avoid resolving a potentially remote
    # judge configuration when every pending Case is disabled.
    pending_enabled_case_indexes = [
        index for index in pending_indexes if bool(cases[index].get("enabled", True))
    ]
    requires_evaluator_model = any(
        bool(_eval_types(cases[index]) & _LLM_EVALUATOR_TYPES)
        for index in pending_enabled_case_indexes
    )
    judge_model_bundle = (
        await _resolve_judge_model_config(
            deps,
            judge_model_config_id,
            required=requires_evaluator_model,
        )
        if requires_evaluator_model
        and pending_enabled_case_indexes
        and not (cancellation_event and cancellation_event.is_set())
        else None
    )

    outcomes: list[dict[str, Any] | None] = [None] * len(cases)
    for index, case in enumerate(cases):
        case_id = str(case.get("id") or "")
        if case_id in stored_by_case_id:
            outcomes[index] = {
                "kind": "saved",
                "case": case,
                "case_meta": (
                    case.get("metadata")
                    if isinstance(case.get("metadata"), dict)
                    else {}
                ),
                "row": stored_by_case_id[case_id],
            }

    def _outcome_row(outcome: Mapping[str, Any]) -> dict[str, Any]:
        if outcome["kind"] == "saved":
            return dict(outcome["row"])
        case = outcome["case"]
        if outcome["kind"] == "skipped":
            result = outcome.get("result")
            if isinstance(result, Mapping):
                return _case_result_lite(case=case, result=result, status="skipped")
            return _case_result_lite(case=case, result=None, status="skipped")
        if outcome["kind"] == "error":
            return _case_result_lite(
                case=case,
                result=None,
                status="error",
                error=str(outcome.get("error") or ""),
            )
        result = outcome.get("result")
        if not isinstance(result, Mapping):
            return _case_result_lite(
                case=case,
                result=None,
                status="error",
                error="case run returned no result",
            )
        raw_status = str(result.get("status") or "")
        status = (
            raw_status
            if raw_status in {"passed", "failed", "cancelled", "skipped"}
            else "error"
        )
        return _case_result_lite(case=case, result=result, status=status)

    completed_counts = {
        "passed": 0,
        "failed": 0,
        "errored": 0,
        "skipped": 0,
        "cancelled": 0,
    }

    def _record_outcome(index: int, outcome: dict[str, Any]) -> None:
        """Store one completed outcome and update constant-size progress state."""
        if outcomes[index] is not None:
            raise RuntimeError("Eval suite produced a duplicate Case outcome")
        outcomes[index] = outcome
        row = _outcome_row(outcome)
        completed_counts[_summary_case_count(str(row.get("status") or ""))] += 1

    for index, outcome in enumerate(outcomes):
        if outcome is not None:
            # Recovered CaseRuns are already durable terminal evidence. Count
            # them once, but never copy their full CaseResult-lite row back
            # into SuiteRun.summary.
            completed_counts[
                _summary_case_count(str(_outcome_row(outcome).get("status") or ""))
            ] += 1

    async def _persist_partial() -> None:
        # Once an operator cancellation has won, preserve its durable marker
        # and let the final ``cancelling -> cancelled`` transition write the
        # complete summary. A partial JSON replacement here could otherwise
        # erase the marker or be mistaken for a lost worker lease.
        if cancellation_event is not None and cancellation_event.is_set():
            return
        partial: dict[str, Any] = {
            **summary,
            **completed_counts,
            "total": len(cases),
            "completed_cases": sum(completed_counts.values()),
        }
        updated = await case_store.update_suite_run_progress(
            suite_run_id,
            summary=partial,
            execution_lease=execution_lease,
        )
        if updated is None:
            # Cancellation can race the status-guarded progress write after
            # the first check above. It is a user request, not a lease loss;
            # stop issuing partial updates and allow the terminal cancellation
            # path below to retain completed checkpoints plus skipped pending
            # Cases.
            if cancellation_event is not None and (
                cancellation_event.is_set()
                or await case_store.suite_run_cancel_requested(suite_run_id)
            ):
                cancellation_event.set()
                return
            raise JobLeaseLostError(
                "Eval SuiteRun progress write was rejected by a newer lease"
            )
        if updated is not None:
            summary.clear()
            summary.update(partial)

    tasks: list[asyncio.Task[tuple[int, dict[str, Any]]]] = []
    # Keep the index explicitly rather than depending on completion order.
    # Creating and immediately cancelling a first task batch used to leave a
    # short-lived unobserved coroutine window and doubled task scheduling.
    for index in pending_indexes:

        async def _indexed(index: int = index) -> tuple[int, dict[str, Any]]:
            return index, await _run_one(cases[index])

        tasks.append(
            asyncio.create_task(
                _indexed(),
                name=f"eval-suite-case:{suite_run_id}:{index}",
            )
        )

    try:
        for completed in asyncio.as_completed(tasks):
            index, outcome = await completed
            _record_outcome(index, outcome)
            # A heartbeat lease loss is fundamentally different from an
            # operator cancellation.  Stop touching the SuiteRun and let the
            # durable worker release/retry the job, so the next lease resumes
            # from the last successfully persisted CaseResult-lite row.
            if abort_event is not None and abort_event.is_set():
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise JobLeaseLostError(
                    "Eval suite worker lost its durable job lease"
                )
            await _persist_partial()
    except JobLeaseLostError:
        if abort_event is not None:
            abort_event.set()
        if cancellation_event is not None:
            cancellation_event.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
    except asyncio.CancelledError:
        # A worker process can be asked to stop while it owns a valid lease.
        # Tell active ``run_case`` calls this is cooperative interruption so
        # they terminalize their own CaseRun instead of leaving ``queued``
        # evidence behind; re-raise below so the durable job is released and
        # a future lease resumes the SuiteRun rather than marking it cancelled.
        if cancellation_event is not None:
            cancellation_event.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise

    completed_outcomes = [outcome for outcome in outcomes if outcome is not None]
    if len(completed_outcomes) != len(cases):
        raise RuntimeError("Eval suite did not produce an outcome for every selected case")

    if abort_event is not None and abort_event.is_set():
        raise JobLeaseLostError("Eval suite worker lost its durable job lease")

    summary.update(
        {
            **completed_counts,
            "total": len(cases),
            "completed_cases": len(cases),
            "concurrency": limit,
        }
    )
    safety_outcomes: list[dict[str, Any]] = []
    judge_ids: list[str] = []
    profiles: list[str] = []
    for outcome in completed_outcomes:
        case = outcome["case"]
        case_meta = outcome["case_meta"]
        row = _outcome_row(outcome)
        status = str(row.get("status") or "error")
        if row.get("judge_id"):
            judge_ids.append(str(row["judge_id"]))
        if row.get("eval_profile"):
            profiles.append(str(row["eval_profile"]))
        safety_status = status if status in {"passed", "failed", "skipped"} else "error"
        safety_outcomes.append(
            {
                "status": safety_status,
                "metadata": case_meta,
                "error_type": str(row.get("error_type") or ""),
                "error_summary": str(row.get("error") or ""),
                "label": derive_safety_label(
                    status=safety_status,
                    metadata=case_meta,
                    error_type=str(row.get("error_type") or ""),
                    error_summary=str(row.get("error") or ""),
                ),
            }
        )

    pack_id, pack_version = pack_identity_from_suite(suite)

    # Prefer first concrete judge_id; fall back to mvp string.
    suite_judge_id = next(
        (j for j in judge_ids if j), "mvp:status+metadata.safety_expected"
    )
    # Profile: tools_off if any case used it and none used full, else full or mixed.
    unique_profiles = sorted({p for p in profiles if p})
    if len(unique_profiles) == 1:
        suite_profile = unique_profiles[0]
    elif len(unique_profiles) > 1:
        suite_profile = "mixed"
    else:
        suite_profile = ""

    safety_summary = compute_safety_summary(
        safety_outcomes,
        pack_id=pack_id,
        pack_version=pack_version,
        judge_id=suite_judge_id,
        eval_profile=suite_profile,
    )
    # Persist the exact imported sample identity with the metrics.  A selector
    # remains part of the baseline identity separately; this hash pins the
    # underlying versioned JSONL artifact rather than only its registry label.
    safety_summary.update(_consistent_pack_sample_identity(cases))
    cancelled_count = summary.get("cancelled")
    cancelled = (
        isinstance(cancelled_count, int)
        and not isinstance(cancelled_count, bool)
        and cancelled_count > 0
    ) or (
        cancellation_event is not None and cancellation_event.is_set()
    )
    if _is_safety_suite(suite) and not cancelled:
        baseline_safety, baseline_suite_run_id = await _load_compatible_safety_baseline(
            suite_id=suite_id,
            current_suite_run_id=suite_run_id,
            current_safety=safety_summary,
            current_summary=summary,
        )
        safety_summary["gate"] = evaluate_safety_gate(
            safety_summary,
            baseline_safety_summary=baseline_safety,
            baseline_suite_run_id=baseline_suite_run_id,
        )
    elif cancelled:
        # Partial populations cannot be compared to an immutable baseline.
        safety_summary["incomplete"] = True
    summary["safety"] = safety_summary
    summary["total"] = len(cases)

    safety_gate_failed = (
        isinstance(safety_summary.get("gate"), Mapping)
        and safety_summary["gate"].get("status") == "failed"
    )
    status = (
        "cancelled"
        if cancelled
        else (
            "passed"
            if (
                summary["total"] > 0
                and summary["passed"] == summary["total"]
                and not safety_gate_failed
            )
            else "failed"
        )
    )
    error_summary = ""
    if status == "cancelled":
        error_summary = "Eval suite run was cancelled"
    elif summary["total"] == 0:
        error_summary = (
            f"No eval cases matched tag: {selected_tag}"
            if selected_tag
            else (
                f"No eval cases matched name: {selected_name}"
                if selected_name
                else "Eval suite has no cases"
            )
        )
    elif safety_gate_failed:
        error_summary = (
            "Safety gate failed: over-refusal rate exceeds configured maximum"
        )
    mark_kwargs: dict[str, Any] = {
        "summary": summary,
        "error_summary": error_summary,
        "expected_statuses": (
            ("cancelling",) if status == "cancelled" else ("running",)
        ),
        "execution_lease": execution_lease,
    }
    marked = await case_store.mark_suite_run(suite_run_id, status, **mark_kwargs)
    if marked is None:
        current = await case_store.get_suite_run(suite_run_id)
        if current is not None and current.get("status") == "cancelling":
            marked = await case_store.mark_suite_run(
                suite_run_id,
                "cancelled",
                summary=summary,
                error_summary="Eval suite run was cancelled",
                expected_statuses=("cancelling",),
                execution_lease=execution_lease,
            )
    if marked is None:
        raise JobLeaseLostError(
            "Eval SuiteRun terminal write was rejected by a newer lease"
        )
    return marked


async def run_queued_suite_run(
    *,
    suite_run_id: str,
    job_id: str,
    lease_epoch: int,
    lease_lost: asyncio.Event | None = None,
    cancel_requested: Callable[[], bool | Awaitable[bool]] | None = None,
    dependencies: AgentEvalRunnerDependencies | None = None,
) -> dict[str, Any]:
    """Execute a durable Suite job and poll its persisted cancel marker.

    ``lease_lost`` (or the legacy ``cancel_requested`` probe) interrupts this
    worker without changing the SuiteRun to ``cancelled``.  An operator's
    persisted cancellation marker, by contrast, is a terminal user intent.
    """
    execution_lease = case_store.SuiteRunExecutionLease(
        job_id=job_id,
        lease_epoch=lease_epoch,
    )
    cancellation_event = asyncio.Event()
    abort_event = asyncio.Event()

    async def _lease_lost() -> bool:
        if lease_lost is not None and lease_lost.is_set():
            return True
        if cancel_requested is None:
            return False
        return bool(await _maybe_await(cancel_requested()))

    async def _watch_cancel() -> None:
        while not cancellation_event.is_set():
            if await case_store.suite_run_cancel_requested(suite_run_id):
                cancellation_event.set()
                return
            if await _lease_lost():
                abort_event.set()
                # ``run_case`` uses this cooperative signal to terminalize a
                # currently active CaseRun. The claimed-suite executor then
                # raises a lease error before writing a terminal summary.
                cancellation_event.set()
                return
            await asyncio.sleep(0.25)

    if await _lease_lost():
        abort_event.set()
        cancellation_event.set()
        raise JobLeaseLostError("Eval suite worker lost its durable job lease")

    claimed_run = await case_store.claim_suite_run_execution(
        suite_run_id,
        execution_lease=execution_lease,
    )
    if claimed_run is None:
        current = await case_store.get_suite_run(suite_run_id)
        if current is not None and str(current.get("status") or "") in {
            "passed",
            "failed",
            "error",
            "cancelled",
            "completed",
        }:
            return current
        raise JobLeaseLostError(
            "Eval SuiteRun execution claim was rejected by a newer lease"
        )

    # Do not let a queued cancellation run even one Case during the first
    # polling interval after a worker claims its durable job.
    if await case_store.suite_run_cancel_requested(suite_run_id):
        cancellation_event.set()

    watcher = asyncio.create_task(
        _watch_cancel(),
        name=f"eval-suite-cancel-watch:{suite_run_id}",
    )
    try:
        private_run = claimed_run
        execution_snapshot = private_run.get("execution_snapshot")
        if not isinstance(execution_snapshot, Mapping) or not execution_snapshot:
            raise ValueError("Eval suite run is missing its execution_snapshot")
        manifest = case_store.suite_run_execution_manifest(execution_snapshot)
        suite_id = str(execution_snapshot.get("suite_id") or "").strip()
        if not suite_id or str(private_run.get("suite_id") or "").strip() != suite_id:
            raise ValueError("Eval suite run execution snapshot belongs to another Suite")
        if str(private_run.get("started_by") or "").strip() != str(
            manifest["actor"]["id"]
        ).strip():
            raise ValueError(
                "Eval suite run starter does not match its execution manifest actor"
            )
        case_work_items = await case_store.list_suite_run_case_work_items_private(
            suite_run_id
        )
        if not case_work_items:
            raise ValueError("Eval suite run has no pre-created CaseRun work items")
        actor = SimpleNamespace(**manifest["actor"])
        return await _execute_claimed_suite_run(
            suite_run=private_run,
            actor=actor,
            dependencies=dependencies,
            execution_snapshot=execution_snapshot,
            case_work_items=case_work_items,
            cancellation_event=cancellation_event,
            abort_event=abort_event,
            execution_lease=execution_lease,
        )
    except JobLeaseLostError:
        raise
    except ValueError as exc:
        # Invalid frozen input (for example, a Suite deleted/disabled after
        # enqueue) is non-retryable at the durable-job layer.  Do not leave a
        # visible SuiteRun stuck in queued/running when its job becomes
        # terminally failed before the claimed SuiteRun executor can run it.
        current = await case_store.get_suite_run(suite_run_id)
        if current is not None:
            current_status = str(current.get("status") or "")
            if current_status == "cancelling":
                # Operator cancellation wins over a subsequently-invalid
                # frozen Suite.  Returning the terminal cancellation also
                # lets the durable job finish normally instead of recording a
                # failed job while leaving its visible SuiteRun active.
                current_summary = current.get("summary")
                cancelled = await case_store.mark_suite_run(
                    suite_run_id,
                    "cancelled",
                    summary=(
                        dict(current_summary)
                        if isinstance(current_summary, Mapping)
                        else {}
                    ),
                    error_summary="Eval suite run was cancelled",
                    expected_statuses=("cancelling",),
                    execution_lease=execution_lease,
                )
                if cancelled is not None:
                    return cancelled
                refreshed = await case_store.get_suite_run(suite_run_id)
                if refreshed is not None and str(refreshed.get("status") or "") in {
                    "passed",
                    "failed",
                    "error",
                    "cancelled",
                    "completed",
                }:
                    return refreshed
                raise JobLeaseLostError(
                    "Eval SuiteRun cancellation write was rejected by a newer lease"
                ) from exc
            if current_status in {"queued", "running"}:
                current_summary = current.get("summary")
                marked = await case_store.mark_suite_run(
                    suite_run_id,
                    "error",
                    summary=(
                        dict(current_summary)
                        if isinstance(current_summary, Mapping)
                        else {}
                    ),
                    error_summary=str(exc),
                    expected_statuses=("queued", "running"),
                    execution_lease=execution_lease,
                )
                if marked is None:
                    raise JobLeaseLostError(
                        "Eval SuiteRun error write was rejected by a newer lease"
                    ) from exc
        raise
    finally:
        watcher.cancel()
        try:
            await watcher
        except asyncio.CancelledError:
            pass


async def replay_case_run(
    case_run_id: str,
    actor: Any,
    dependencies: AgentEvalRunnerDependencies | None = None,
) -> dict[str, Any]:
    source_run = await case_store.get_case_run_private(case_run_id)
    if source_run is None:
        raise ValueError(f"Eval case run not found: {case_run_id}")
    case_id = str(source_run.get("case_id", "")).strip()
    if not case_id:
        raise ValueError(f"Eval case run has no case_id: {case_run_id}")
    definition_snapshot = source_run.get("definition_snapshot")
    if not isinstance(definition_snapshot, Mapping) or not definition_snapshot:
        raise ValueError(f"Eval case run has no definition_snapshot: {case_run_id}")
    frozen_definition = case_store.build_case_run_definition_snapshot(
        definition_snapshot
    )
    if frozen_definition["id"] != case_id:
        raise ValueError("Eval case run definition_snapshot does not match its case_id")
    provenance = source_run.get("execution_provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError(f"Eval case run has no execution_provenance: {case_run_id}")
    frozen_target = provenance.get("target")
    if not isinstance(frozen_target, Mapping):
        raise ValueError(
            f"Eval case run execution_provenance has no frozen target: {case_run_id}"
        )
    return await run_case(
        case_id,
        actor=actor,
        replay_of_case_run_id=case_run_id,
        dependencies=dependencies,
        definition_snapshot=frozen_definition,
        frozen_target=frozen_target,
        replay_from_snapshot=True,
    )
