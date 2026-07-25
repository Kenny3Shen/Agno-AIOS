from collections.abc import Mapping, Sequence
from typing import Any

from api.services.agent_eval_report_service import REPORT_FORMAT, build_suite_run_report


def _report(
    suite_run: Mapping[str, Any],
    *,
    case_results: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    return build_suite_run_report(suite_run, case_results=case_results)


def _passed_case(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "refuses safely",
        "case_id": "case-1",
        "case_run_id": "case-run-1",
        "session_id": "eval_case-run-1",
        "duration_seconds": 1.25,
        "timeout_seconds": 45,
        "judge_passed": True,
        "judge_reason": None,
        "judge_score": 9,
        "reliability_passed": None,
        "passed": True,
        "skipped": False,
        "status": "passed",
        "error": "",
        **overrides,
    }


def test_build_suite_run_report_is_agno_shaped_and_redacts_raw_content() -> None:
    report = _report(
        {
            "id": "suite-run-1",
            "suite_id": "suite-1",
            "status": "passed",
            "started_at": "2026-07-22T00:00:00+00:00",
            "completed_at": "2026-07-22T00:01:00+00:00",
            "summary": {
                "safety": {"asr": 0.0, "refusal_rate": 1.0, "untrusted": "omit"},
            },
        },
        case_results=[
            _passed_case(
                input="raw harmful prompt must not leak",
                output="raw model completion must not leak",
            )
        ],
    )

    assert report["format"] == REPORT_FORMAT
    assert report["summary"] == {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "errored": 0,
        "skipped": 0,
        "status": "PASS",
        "safety": {"asr": 0.0, "refusal_rate": 1.0},
    }
    assert report["case_results_available"] is True
    assert report["cases"] == [
        {
            "name": "refuses safely",
            "case_id": "case-1",
            "case_run_id": "case-run-1",
            "session_id": "eval_case-run-1",
            "duration_seconds": 1.25,
            "timeout_seconds": 45,
            "accuracy_passed": None,
            "accuracy_reason": None,
            "accuracy_score": None,
            "judge_passed": True,
            "judge_reason": None,
            "judge_score": 9,
            "reliability_passed": None,
            "timed_out": False,
            "skipped": False,
            "passed": True,
            "error": None,
            "status": "passed",
            "judge_id": None,
            "eval_profile": None,
        }
    ]
    assert "input" not in report["cases"][0]
    assert "output" not in report["cases"][0]


def test_build_suite_run_report_uses_case_runs_not_embedded_summary_cases() -> None:
    report = _report(
        {
            "id": "suite-run-1",
            "suite_id": "suite-1",
            "status": "failed",
            "summary": {
                "passed": 999,
                "cases": [{"name": "stale", "status": "passed", "passed": True}],
            },
        },
        case_results=[
            _passed_case(
                name="durable failure",
                status="failed",
                passed=False,
                error="judge failed",
            )
        ],
    )

    assert report["summary"].get("total") == 1
    assert report["summary"]["passed"] == 0
    assert report["summary"]["failed"] == 1
    assert report["cases"][0]["name"] == "durable failure"


def test_build_suite_run_report_exports_only_safe_reliability_diagnostics() -> None:
    report = _report(
        {"id": "suite-run-reliability", "suite_id": "suite-1", "status": "failed", "summary": {}},
        case_results=[
            _passed_case(
                status="failed",
                passed=False,
                reliability_passed=False,
                reliability_evidence={
                    "failed_tool_calls": ["unapproved_tool", {"raw_tool_args": "must not export"}],
                    "passed_tool_calls": ["approved_tool"],
                    "additional_tool_calls": ["audit_tool"],
                    "missing_tool_calls": ["approved_tool"],
                    "failed_argument_checks": ["approved_tool", {"raw_tool_args": "must not export"}],
                    "passed_argument_checks": ["safe_lookup"],
                },
                input="raw harmful prompt must not export",
                output="raw model completion must not export",
            )
        ],
    )

    assert report["cases"][0]["reliability_evidence"] == {
        "failed_tool_calls": ["unapproved_tool"],
        "passed_tool_calls": ["approved_tool"],
        "additional_tool_calls": ["audit_tool"],
        "missing_tool_calls": ["approved_tool"],
        "failed_argument_checks": ["approved_tool"],
        "passed_argument_checks": ["safe_lookup"],
    }
    assert "raw_tool_args" not in str(report)
    assert "raw harmful prompt" not in str(report)
    assert "raw model completion" not in str(report)


def test_build_suite_run_report_exports_only_aggregate_performance_metrics() -> None:
    report = _report(
        {"id": "suite-run-performance", "suite_id": "suite-1", "status": "passed", "summary": {}},
        case_results=[
            _passed_case(
                performance={
                    "warmup_runs": 1,
                    "num_iterations": 3,
                    "runtime_seconds": {"avg": 0.125, "median": 0.1, "p95": 0.2},
                    "memory_mib": {"avg": 4.1, "median": 4.0, "p95": 5.0},
                    "run_times": ["raw samples must not export"],
                    "output": "raw model completion must not export",
                }
            )
        ],
    )

    assert report["cases"][0]["performance"] == {
        "warmup_runs": 1,
        "num_iterations": 3,
        "runtime_seconds": {"avg": 0.125, "median": 0.1, "p95": 0.2},
        "memory_mib": {"avg": 4.1, "median": 4.0, "p95": 5.0},
    }
    assert "raw samples" not in str(report)
    assert "raw model completion" not in str(report)


def test_build_suite_run_report_preserves_safe_sample_identity_and_gate_evidence() -> None:
    sample_hash = "a" * 64
    report = _report(
        {
            "id": "suite-run-gate",
            "suite_id": "suite-1",
            "status": "passed",
            "summary": {
                "safety": {
                    "asr": 0.0,
                    "pack_cases_sha256": sample_hash,
                    "pack_cases_count": 20,
                    "pack_sample_seed": 42,
                    "pack_source_kind": "hf",
                    "resolved_source": "https://token@example.invalid/private",
                    "manifest": {"raw_prompt": "must never export"},
                    "pack_source_url": "must never export",
                    "gate": {
                        "version": "v1",
                        "status": "failed",
                        "baseline_suite_run_id": "suite-run-baseline",
                        "policy": {
                            "max_over_refusal_rate": 0.15,
                            "asr_regression_tolerance": 0.05,
                            "refusal_regression_tolerance": 0.03,
                            "untrusted_policy": "must not be exported",
                        },
                        "checks": [
                            {
                                "id": "max_over_refusal_rate",
                                "status": "failed",
                                "actual": 0.2,
                                "threshold": 0.15,
                                "untrusted_raw_output": "must not be exported",
                            }
                        ],
                    },
                },
            },
        },
        case_results=[_passed_case()],
    )

    assert report["summary"]["status"] == "FAIL"
    assert report["summary"]["safety"] == {
        "asr": 0.0,
        "pack_cases_sha256": sample_hash,
        "pack_cases_count": 20,
        "pack_sample_seed": 42,
        "pack_source_kind": "hf",
        "gate": {
            "version": "v1",
            "status": "failed",
            "passed": False,
            "baseline_suite_run_id": "suite-run-baseline",
            "policy": {
                "max_over_refusal_rate": 0.15,
                "asr_regression_tolerance": 0.05,
                "refusal_regression_tolerance": 0.03,
            },
            "checks": [
                {
                    "id": "max_over_refusal_rate",
                    "status": "failed",
                    "actual": 0.2,
                    "threshold": 0.15,
                }
            ],
        },
    }
    assert "untrusted_raw_output" not in str(report)
    assert "private" not in str(report)
    assert "raw_prompt" not in str(report)
    assert "pack_source_url" not in str(report)


def test_build_suite_run_report_preserves_timeout_and_selectors() -> None:
    report = _report(
        {
            "id": "suite-run-timeout",
            "suite_id": "suite-1",
            "status": "failed",
            "summary": {
                "default_timeout": 45,
                "selected_tag": "smoke",
                "selected_cases": 1,
            },
        },
        case_results=[
            _passed_case(
                name="slow check",
                status="error",
                passed=False,
                timed_out=True,
                timeout_seconds=45,
                error="Eval case exceeded timeout of 45 seconds",
            )
        ],
    )

    assert report["summary"]["default_timeout"] == 45
    assert report["summary"]["selected_tag"] == "smoke"
    assert report["summary"]["selected_cases"] == 1
    assert report["cases"][0]["timed_out"] is True
    assert report["cases"][0]["timeout_seconds"] == 45


def test_build_suite_run_report_does_not_reconstruct_missing_case_evidence() -> None:
    report = _report(
        {
            "id": "suite-run-legacy",
            "suite_id": "suite-1",
            "status": "completed",
            "summary": {"passed": 2, "failed": 0},
        }
    )

    assert report["summary"] == {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "errored": 0,
        "skipped": 0,
        "status": "FAIL",
    }
    assert report["cases"] == []
    assert report["case_results_available"] is False


def test_build_suite_run_report_keeps_the_name_selector_for_ci_reproducibility() -> None:
    report = _report(
        {
            "id": "suite-run-case",
            "suite_id": "suite-1",
            "status": "passed",
            "summary": {"selected_name": "Smoke check", "selected_cases": 1},
        },
        case_results=[_passed_case()],
    )

    assert report["summary"]["selected_name"] == "Smoke check"
    assert report["summary"]["selected_cases"] == 1
