from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any
from uuid import uuid4

from api.auth.claims import KNOWN_ROLES, actor_id
from api.services.eval_targets import parse_eval_target
from api.services.safety_eval_rubrics import eval_profile_from_metadata
from api.utils.pagination import pagination_meta
from api.persistence.agent_evals import (
    create_case_row_async,
    create_case_run_row_async,
    create_suite_row_async,
    complete_case_run_row_if_queued_async,
    claim_suite_case_run_row_async,
    claim_suite_run_execution_row_async,
    delete_case_row_async,
    delete_suite_rows_async,
    get_case_row_async,
    get_case_run_row_async,
    get_suite_row_async,
    get_suite_run_row_async,
    import_pack_rows_async,
    list_case_rows_async,
    list_case_rows_page_async,
    list_case_runs_by_agno_eval_run_ids_rows_async,
    list_case_run_rows_async,
    list_suite_run_case_work_item_rows_async,
    list_suite_rows_async,
    list_suite_run_rows_async,
    remove_imported_pack_rows_async,
    request_suite_run_cancel_row_async,
    update_case_row_async,
    update_case_run_row_async,
    update_case_run_row_if_execution_lease_async,
    update_suite_row_async,
    update_suite_run_row_if_execution_lease_async,
)

SUPPORTED_EVAL_TYPES = {"accuracy", "agent_as_judge", "reliability", "performance"}
SUPPORTED_JUDGE_MODES = {"binary", "numeric"}
MAX_CASE_TIMEOUT_SECONDS = 3_600
MAX_CASE_ADDITIONAL_GUIDELINES = 20
MAX_CASE_ADDITIONAL_GUIDELINE_CHARS = 2_000
MAX_TOOL_ARGUMENT_CONTRACT_TOOLS = 50
MAX_TOOL_ARGUMENT_SPECS_PER_TOOL = 20
MAX_TOOL_ARGUMENT_CONTRACT_BYTES = 32_000
MAX_TOOL_NAME_CHARS = 160
# A CaseRun definition is durable replay evidence and can contain the Case's
# prompt and expected output. Keep it private, JSON-native, and bounded so a
# malformed direct caller cannot turn one persisted run into an unbounded
# database write. The larger definition budget accommodates normal evaluation
# prompts; provenance deliberately remains much smaller metadata.
MAX_CASE_RUN_DEFINITION_SNAPSHOT_BYTES = 256 * 1024
MAX_CASE_RUN_EXECUTION_PROVENANCE_BYTES = 64 * 1024
MAX_CASE_RUN_TERMINAL_CHECKPOINT_BYTES = 64 * 1024
MAX_CASE_RUN_PRIVATE_JSON_DEPTH = 32
MAX_SUITE_RUN_EXECUTION_SNAPSHOT_BYTES = 4 * 1024 * 1024
# A SuiteRun snapshot intentionally contains only Suite-level immutable
# metadata.  Case definitions and their execution provenance live exclusively
# on the pre-created CaseRun work items, which are also the result source of
# truth.  Bump this when the private snapshot shape changes rather than trying
# to infer a mixed state from historical rows.
SUITE_RUN_EXECUTION_SNAPSHOT_VERSION = 2
SUITE_RUN_EXECUTION_MANIFEST_VERSION = 2
CASE_RUN_TERMINAL_CHECKPOINT_VERSION = 1
_TERMINAL_CASE_RUN_STATUSES = {
    "passed",
    "failed",
    "error",
    "cancelled",
    "skipped",
}
_MAX_SUITE_RUN_MANIFEST_TEXT_CHARS = 1_024


@dataclass(frozen=True, slots=True)
class SuiteRunExecutionLease:
    """Private durable-job fence required for a queued SuiteRun write."""

    job_id: str
    lease_epoch: int

    def __post_init__(self) -> None:
        if not self.job_id.strip():
            raise ValueError("execution lease job_id is required")
        if isinstance(self.lease_epoch, bool) or self.lease_epoch < 1:
            raise ValueError("execution lease epoch must be a positive integer")


@dataclass(frozen=True, slots=True)
class SuiteCaseRunClaim:
    """The durable worker's claim result for one logical Suite CaseRun."""

    case_run: dict[str, Any]
    acquired: bool
_TERMINAL_CHECKPOINT_RELIABILITY_FIELDS = {
    "failed_tool_calls",
    "passed_tool_calls",
    "additional_tool_calls",
    "missing_tool_calls",
    "failed_argument_checks",
    "passed_argument_checks",
}
_TERMINAL_CHECKPOINT_MAX_RELIABILITY_ITEMS = 50
_TERMINAL_CHECKPOINT_MAX_RELIABILITY_ITEM_CHARS = 512
_TERMINAL_CHECKPOINT_MAX_JUDGE_ID_CHARS = 1_024
# Performance evaluations can invoke the target once for each warm-up and
# once for every enabled metric. Keep the durable Case contract bounded so a
# malformed direct API request cannot turn a normal Suite run into hundreds of
# expensive model calls before its timeout elapses.
DEFAULT_PERFORMANCE_WARMUP_RUNS = 1
DEFAULT_PERFORMANCE_NUM_ITERATIONS = 3
MAX_PERFORMANCE_WARMUP_RUNS = 100
MAX_PERFORMANCE_NUM_ITERATIONS = 100
_PACK_ID_TAG_PREFIX = "pack:"
_PACK_VERSION_TAG_PREFIX = "pack_version:"


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


def _case_tags(value: Any) -> list[str]:
    """Trim and de-duplicate Case tags while retaining their first-seen order."""
    if not isinstance(value, list):
        return []
    tags: list[str] = []
    seen: set[str] = set()
    for raw_tag in value:
        tag = _string(raw_tag).strip()
        if tag and tag not in seen:
            tags.append(tag)
            seen.add(tag)
    return tags


def _additional_guidelines(value: Any) -> list[str]:
    """Validate Agno's ordered per-Case evaluator guidance.

    The field is deliberately separate from ``metadata``: it changes what an
    AccuracyEval / AgentAsJudgeEval considers correct and therefore belongs in
    the auditable Case definition. Empty items and duplicates are discarded;
    malformed or oversized input is rejected instead of silently changing the
    evaluator contract.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("additional_guidelines must be a list of strings")
    if len(value) > MAX_CASE_ADDITIONAL_GUIDELINES:
        raise ValueError(
            "additional_guidelines may contain at most "
            f"{MAX_CASE_ADDITIONAL_GUIDELINES} items"
        )

    guidelines: list[str] = []
    seen: set[str] = set()
    for raw_guideline in value:
        if not isinstance(raw_guideline, str):
            raise ValueError("additional_guidelines must be a list of strings")
        guideline = raw_guideline.strip()
        if not guideline:
            continue
        if len(guideline) > MAX_CASE_ADDITIONAL_GUIDELINE_CHARS:
            raise ValueError(
                "each additional_guideline must be at most "
                f"{MAX_CASE_ADDITIONAL_GUIDELINE_CHARS} characters"
            )
        if guideline not in seen:
            guidelines.append(guideline)
            seen.add(guideline)
    return guidelines


def normalize_expected_tool_call_arguments(value: Any) -> dict[str, Any]:
    """Validate Agno ``ReliabilityEval`` argument-subset contracts.

    Agno accepts a mapping from tool name to either one argument object or a
    non-empty list of argument objects. Each object is matched as a subset of
    the arguments of one clean tool execution. Store only canonical JSON here:
    otherwise a malformed direct API/client write can reach ``ReliabilityEval``
    and turn a case execution into an implementation error rather than a clear
    authoring validation error.
    """
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("expected_tool_call_arguments must be an object")
    if len(value) > MAX_TOOL_ARGUMENT_CONTRACT_TOOLS:
        raise ValueError(
            "expected_tool_call_arguments may contain at most "
            f"{MAX_TOOL_ARGUMENT_CONTRACT_TOOLS} tools"
        )

    normalized: dict[str, Any] = {}
    for raw_tool_name, raw_specs in value.items():
        if not isinstance(raw_tool_name, str):
            raise ValueError("expected_tool_call_arguments tool names must be strings")
        tool_name = raw_tool_name.strip()
        if not tool_name:
            raise ValueError("expected_tool_call_arguments tool names must not be blank")
        if len(tool_name) > MAX_TOOL_NAME_CHARS:
            raise ValueError(
                "expected_tool_call_arguments tool names must be at most "
                f"{MAX_TOOL_NAME_CHARS} characters"
            )
        if tool_name in normalized:
            raise ValueError(
                "expected_tool_call_arguments contains duplicate tool names after trimming"
            )

        specs = raw_specs if isinstance(raw_specs, list) else [raw_specs]
        if not specs:
            raise ValueError(
                "expected_tool_call_arguments tool specs must not be empty lists"
            )
        if len(specs) > MAX_TOOL_ARGUMENT_SPECS_PER_TOOL:
            raise ValueError(
                "expected_tool_call_arguments may contain at most "
                f"{MAX_TOOL_ARGUMENT_SPECS_PER_TOOL} specs per tool"
            )

        canonical_specs: list[dict[str, Any]] = []
        for raw_spec in specs:
            if not isinstance(raw_spec, Mapping):
                raise ValueError(
                    "expected_tool_call_arguments values must be objects or lists of objects"
                )
            try:
                encoded_spec = json.dumps(
                    raw_spec,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                decoded_spec = json.loads(encoded_spec)
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise ValueError(
                    "expected_tool_call_arguments specs must contain JSON values"
                ) from exc
            if not isinstance(decoded_spec, dict):
                raise ValueError(
                    "expected_tool_call_arguments values must be objects or lists of objects"
                )
            canonical_specs.append(decoded_spec)

        normalized[tool_name] = (
            canonical_specs if isinstance(raw_specs, list) else canonical_specs[0]
        )

    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "expected_tool_call_arguments specs must contain JSON values"
        ) from exc
    if len(encoded) > MAX_TOOL_ARGUMENT_CONTRACT_BYTES:
        raise ValueError(
            "expected_tool_call_arguments must be at most "
            f"{MAX_TOOL_ARGUMENT_CONTRACT_BYTES} UTF-8 bytes"
        )
    return normalized


def _imported_pack_identity(tags: Any) -> tuple[str, str] | None:
    """Return a strict imported-pack identity only for one exact tag pair.

    Pack Suites are immutable data artifacts: allowing an operator to append a
    normal Case to one would make a later pack removal delete unrelated data.
    The identity rule deliberately matches the importer and deletion path.
    """
    if not isinstance(tags, list):
        return None
    pack_ids: set[str] = set()
    pack_versions: set[str] = set()
    for raw_tag in tags:
        tag = _string(raw_tag).strip()
        if tag.startswith(_PACK_ID_TAG_PREFIX):
            pack_id = tag.removeprefix(_PACK_ID_TAG_PREFIX).strip()
            if pack_id:
                pack_ids.add(pack_id)
        elif tag.startswith(_PACK_VERSION_TAG_PREFIX):
            pack_version = tag.removeprefix(_PACK_VERSION_TAG_PREFIX).strip()
            if pack_version:
                pack_versions.add(pack_version)
    if len(pack_ids) != 1 or len(pack_versions) != 1:
        return None
    return next(iter(pack_ids)), next(iter(pack_versions))


def _assert_no_reserved_pack_tags(tags: Any) -> None:
    """Keep strict Pack identity tags exclusive to the importer."""
    for raw_tag in _string_list(tags):
        if raw_tag.startswith((_PACK_ID_TAG_PREFIX, _PACK_VERSION_TAG_PREFIX)):
            raise ValueError(
                "pack: and pack_version: tags are reserved for imported eval packs"
            )


async def _require_mutable_suite(
    suite_id: str,
    *,
    allow_imported_pack_mutation: bool,
) -> dict[str, Any] | None:
    """Return a Suite unless it is a strict imported artifact.

    ``None`` retains the public store convention for a missing resource. The
    importer is the only caller allowed to upsert an imported Pack Suite.
    """
    suite = await get_suite(suite_id)
    if suite is None:
        return None
    if (
        not allow_imported_pack_mutation
        and _imported_pack_identity(suite.get("tags")) is not None
    ):
        raise ValueError(
            "Imported eval pack suites are immutable; remove and re-import the pack instead"
        )
    return suite


def _selected_case_tag(value: Any) -> str | None:
    if value is None:
        return None
    tag = _string(value).strip()
    if not tag:
        raise ValueError("tag must not be blank")
    return tag


def _selected_case_name(value: Any) -> str | None:
    if value is None:
        return None
    name = _string(value).strip()
    if not name:
        raise ValueError("name must not be blank")
    return name


def _dict_value(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_safe_snapshot_value(
    value: Any,
    *,
    field: str,
    depth: int = 0,
    ancestors: set[int] | None = None,
) -> Any:
    """Return a detached JSON value or reject a non-replayable value.

    ``json.dumps`` alone would silently stringify integer object keys and can
    recurse into cyclic custom containers. Snapshot evidence must preserve its
    JSON meaning exactly, so reject those ambiguous inputs before canonical
    serialization.
    """
    if depth > MAX_CASE_RUN_PRIVATE_JSON_DEPTH:
        raise ValueError(
            f"{field} may be nested at most {MAX_CASE_RUN_PRIVATE_JSON_DEPTH} levels"
        )
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not isfinite(value):
            raise ValueError(f"{field} must contain finite JSON numbers")
        return value

    active = ancestors if ancestors is not None else set()
    if isinstance(value, Mapping):
        marker = id(value)
        if marker in active:
            raise ValueError(f"{field} must not contain cyclic values")
        active.add(marker)
        try:
            normalized: dict[str, Any] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise ValueError(f"{field} object keys must be strings")
                normalized[key] = _json_safe_snapshot_value(
                    item,
                    field=field,
                    depth=depth + 1,
                    ancestors=active,
                )
            return normalized
        finally:
            active.remove(marker)

    if isinstance(value, (list, tuple)):
        marker = id(value)
        if marker in active:
            raise ValueError(f"{field} must not contain cyclic values")
        active.add(marker)
        try:
            return [
                _json_safe_snapshot_value(
                    item,
                    field=field,
                    depth=depth + 1,
                    ancestors=active,
                )
                for item in value
            ]
        finally:
            active.remove(marker)

    raise ValueError(f"{field} must contain only JSON-safe values")


def _canonical_private_case_run_mapping(
    value: Any,
    *,
    field: str,
    max_bytes: int,
) -> dict[str, Any]:
    """Validate and detach a bounded private CaseRun JSON object."""
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object")

    normalized = _json_safe_snapshot_value(value, field=field)
    if not isinstance(normalized, dict):  # pragma: no cover - guarded above.
        raise ValueError(f"{field} must be an object")
    try:
        encoded = json.dumps(
            normalized,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise ValueError(f"{field} must contain only JSON-safe values") from exc
    if len(encoded) > max_bytes:
        raise ValueError(f"{field} must be at most {max_bytes} UTF-8 bytes")
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):  # pragma: no cover - JSON object input.
        raise ValueError(f"{field} must be an object")
    return decoded


def normalize_case_run_definition_snapshot(value: Any) -> dict[str, Any]:
    """Canonicalize immutable private Case definition evidence for storage."""
    return _canonical_private_case_run_mapping(
        value,
        field="definition_snapshot",
        max_bytes=MAX_CASE_RUN_DEFINITION_SNAPSHOT_BYTES,
    )


def normalize_case_run_execution_provenance(value: Any) -> dict[str, Any]:
    """Canonicalize immutable private execution provenance for storage."""
    return _canonical_private_case_run_mapping(
        value,
        field="execution_provenance",
        max_bytes=MAX_CASE_RUN_EXECUTION_PROVENANCE_BYTES,
    )


def _terminal_checkpoint_optional_bool(value: Any, *, field: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"terminal_checkpoint.{field} must be a boolean or null")
    return value


def _terminal_checkpoint_score(
    value: Any,
    *,
    field: str,
    integer: bool,
) -> int | float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"terminal_checkpoint.{field} must be a score or null")
    score = float(value)
    if not isfinite(score) or not 1.0 <= score <= 10.0:
        raise ValueError(
            f"terminal_checkpoint.{field} must be between 1 and 10 or null"
        )
    if integer:
        if not score.is_integer():
            raise ValueError(f"terminal_checkpoint.{field} must be an integer or null")
        return int(score)
    return score


def _terminal_checkpoint_reliability_evidence(value: Any) -> dict[str, list[str]] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("terminal_checkpoint.reliability_evidence must be an object or null")
    unknown = sorted(
        str(key)
        for key in value
        if not isinstance(key, str) or key not in _TERMINAL_CHECKPOINT_RELIABILITY_FIELDS
    )
    if unknown:
        raise ValueError(
            "terminal_checkpoint.reliability_evidence contains unsupported fields: "
            + ", ".join(unknown)
        )
    normalized: dict[str, list[str]] = {}
    for key, raw_items in value.items():
        if not isinstance(raw_items, list):
            raise ValueError(
                f"terminal_checkpoint.reliability_evidence.{key} must be a list"
            )
        if len(raw_items) > _TERMINAL_CHECKPOINT_MAX_RELIABILITY_ITEMS:
            raise ValueError(
                f"terminal_checkpoint.reliability_evidence.{key} has too many items"
            )
        items: list[str] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, str):
                raise ValueError(
                    f"terminal_checkpoint.reliability_evidence.{key} must contain strings"
                )
            item = raw_item.strip()
            if not item or len(item) > _TERMINAL_CHECKPOINT_MAX_RELIABILITY_ITEM_CHARS:
                raise ValueError(
                    f"terminal_checkpoint.reliability_evidence.{key} contains an invalid item"
                )
            items.append(item)
        if items:
            normalized[key] = items
    return normalized or None


def _terminal_checkpoint_aggregate(
    value: Any,
    *,
    field: str,
) -> dict[str, float]:
    if not isinstance(value, Mapping) or set(value) != {"avg", "median", "p95"}:
        raise ValueError(
            f"terminal_checkpoint.performance.{field} must contain avg, median, and p95"
        )
    normalized: dict[str, float] = {}
    for key in ("avg", "median", "p95"):
        raw_metric = value[key]
        if isinstance(raw_metric, bool) or not isinstance(raw_metric, (int, float)):
            raise ValueError(f"terminal_checkpoint.performance.{field}.{key} must be numeric")
        metric = float(raw_metric)
        if not isfinite(metric) or metric < 0:
            raise ValueError(
                f"terminal_checkpoint.performance.{field}.{key} must be finite and non-negative"
            )
        normalized[key] = round(metric, 6)
    return normalized


def _terminal_checkpoint_performance(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError("terminal_checkpoint.performance must be an object or null")
    supported = {"warmup_runs", "num_iterations", "runtime_seconds", "memory_mib"}
    unknown = sorted(
        str(key) for key in value if not isinstance(key, str) or key not in supported
    )
    if unknown:
        raise ValueError(
            "terminal_checkpoint.performance contains unsupported fields: "
            + ", ".join(unknown)
        )
    for key, minimum, maximum in (
        ("warmup_runs", 0, MAX_PERFORMANCE_WARMUP_RUNS),
        ("num_iterations", 1, MAX_PERFORMANCE_NUM_ITERATIONS),
    ):
        raw = value.get(key)
        if isinstance(raw, bool) or not isinstance(raw, int) or not minimum <= raw <= maximum:
            raise ValueError(
                f"terminal_checkpoint.performance.{key} must be an integer between "
                f"{minimum} and {maximum}"
            )
    normalized: dict[str, Any] = {
        "warmup_runs": value["warmup_runs"],
        "num_iterations": value["num_iterations"],
    }
    for key in ("runtime_seconds", "memory_mib"):
        if key in value:
            normalized[key] = _terminal_checkpoint_aggregate(value[key], field=key)
    if len(normalized) == 2:
        raise ValueError("terminal_checkpoint.performance must contain an aggregate")
    return normalized


def normalize_case_run_terminal_checkpoint(value: Any) -> dict[str, Any]:
    """Validate a private, compact, write-once terminal CaseResult checkpoint.

    The record deliberately contains only bounded evaluator aggregates.  It
    must never become a second definition snapshot or a place to retain model
    output, free-form judge reasoning, or raw tool arguments.
    """
    checkpoint = _canonical_private_case_run_mapping(
        value,
        field="terminal_checkpoint",
        max_bytes=MAX_CASE_RUN_TERMINAL_CHECKPOINT_BYTES,
    )
    supported = {
        "version",
        "status",
        "duration_seconds",
        "timeout_seconds",
        "timed_out",
        "accuracy_passed",
        "accuracy_score",
        "judge_passed",
        "judge_score",
        "reliability_passed",
        "reliability_evidence",
        "performance",
        "judge_id",
        "eval_profile",
    }
    unknown = sorted(key for key in checkpoint if key not in supported)
    if unknown:
        raise ValueError(
            "terminal_checkpoint contains unsupported fields: " + ", ".join(unknown)
        )
    required = supported - {"reliability_evidence", "performance"}
    missing = sorted(key for key in required if key not in checkpoint)
    if missing:
        raise ValueError(
            "terminal_checkpoint is missing required fields: " + ", ".join(missing)
        )

    version = checkpoint["version"]
    if isinstance(version, bool) or version != CASE_RUN_TERMINAL_CHECKPOINT_VERSION:
        raise ValueError("terminal_checkpoint.version is unsupported")
    status = checkpoint["status"]
    if not isinstance(status, str) or status not in _TERMINAL_CASE_RUN_STATUSES:
        raise ValueError("terminal_checkpoint.status must be a terminal CaseRun status")
    raw_duration = checkpoint["duration_seconds"]
    if isinstance(raw_duration, bool) or not isinstance(raw_duration, (int, float)):
        raise ValueError("terminal_checkpoint.duration_seconds must be numeric")
    duration_seconds = float(raw_duration)
    if not isfinite(duration_seconds) or duration_seconds < 0:
        raise ValueError(
            "terminal_checkpoint.duration_seconds must be finite and non-negative"
        )
    raw_timeout = checkpoint["timeout_seconds"]
    if isinstance(raw_timeout, bool) or not isinstance(raw_timeout, (int, float)):
        raise ValueError(
            "terminal_checkpoint.timeout_seconds must be a bounded positive number"
        )
    timeout_seconds = float(raw_timeout)
    if (
        not isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= MAX_CASE_TIMEOUT_SECONDS
    ):
        raise ValueError(
            "terminal_checkpoint.timeout_seconds must be a bounded positive number"
        )
    if not isinstance(checkpoint["timed_out"], bool):
        raise ValueError("terminal_checkpoint.timed_out must be a boolean")
    judge_id = checkpoint["judge_id"]
    if not isinstance(judge_id, str) or len(judge_id) > _TERMINAL_CHECKPOINT_MAX_JUDGE_ID_CHARS:
        raise ValueError("terminal_checkpoint.judge_id must be a bounded string")
    eval_profile = checkpoint["eval_profile"]
    if not isinstance(eval_profile, str) or eval_profile not in {"full", "tools_off"}:
        raise ValueError("terminal_checkpoint.eval_profile must be full or tools_off")

    return {
        "version": CASE_RUN_TERMINAL_CHECKPOINT_VERSION,
        "status": status,
        "duration_seconds": round(duration_seconds, 3),
        "timeout_seconds": (
            int(timeout_seconds) if timeout_seconds.is_integer() else timeout_seconds
        ),
        "timed_out": checkpoint["timed_out"],
        "accuracy_passed": _terminal_checkpoint_optional_bool(
            checkpoint["accuracy_passed"], field="accuracy_passed"
        ),
        "accuracy_score": _terminal_checkpoint_score(
            checkpoint["accuracy_score"], field="accuracy_score", integer=False
        ),
        "judge_passed": _terminal_checkpoint_optional_bool(
            checkpoint["judge_passed"], field="judge_passed"
        ),
        "judge_score": _terminal_checkpoint_score(
            checkpoint["judge_score"], field="judge_score", integer=True
        ),
        "reliability_passed": _terminal_checkpoint_optional_bool(
            checkpoint["reliability_passed"], field="reliability_passed"
        ),
        "reliability_evidence": _terminal_checkpoint_reliability_evidence(
            checkpoint.get("reliability_evidence")
        ),
        "performance": _terminal_checkpoint_performance(checkpoint.get("performance")),
        "judge_id": judge_id,
        "eval_profile": eval_profile,
    }


def _definition_snapshot_sha256(value: Any) -> str:
    """Return a stable safe fingerprint without surfacing snapshot contents."""
    try:
        snapshot = normalize_case_run_definition_snapshot(value)
    except ValueError:
        # Historical/corrupt rows must not make the public CaseRun listing
        # fail, nor should they cause their raw contents to be reflected.
        return ""
    if not snapshot:
        return ""
    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _manifest_text(value: Any, *, field: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError(f"execution_snapshot.run_manifest.{field} must be a string")
    normalized = value.strip()
    if not normalized and not allow_empty:
        raise ValueError(
            f"execution_snapshot.run_manifest.{field} must be a non-empty string"
        )
    if len(normalized) > _MAX_SUITE_RUN_MANIFEST_TEXT_CHARS:
        raise ValueError(
            f"execution_snapshot.run_manifest.{field} is too long"
        )
    return normalized


def _manifest_selector(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    return _manifest_text(value, field=field)


def normalize_suite_run_execution_manifest(value: Any) -> dict[str, Any]:
    """Validate the immutable private worker manifest for a SuiteRun.

    Durable jobs deliberately carry only a SuiteRun id.  The manifest freezes
    the actor capability projection and execution selectors that used to be
    duplicated in the job payload, so a later account/role/config edit cannot
    change an already queued evaluation.
    """
    manifest = _canonical_private_case_run_mapping(
        value,
        field="execution_snapshot.run_manifest",
        max_bytes=MAX_CASE_RUN_EXECUTION_PROVENANCE_BYTES,
    )
    supported = {
        "version",
        "actor",
        "selected_tag",
        "selected_name",
        "case_count",
        "default_timeout",
        "judge_model_config_id",
    }
    unknown = sorted(set(manifest) - supported)
    if unknown:
        raise ValueError(
            "execution_snapshot.run_manifest contains unsupported fields: "
            + ", ".join(unknown)
        )
    missing = sorted(supported - set(manifest))
    if missing:
        raise ValueError(
            "execution_snapshot.run_manifest is missing required fields: "
            + ", ".join(missing)
        )

    version = manifest["version"]
    if isinstance(version, bool) or version != SUITE_RUN_EXECUTION_MANIFEST_VERSION:
        raise ValueError("execution_snapshot.run_manifest.version is unsupported")
    actor = manifest["actor"]
    if not isinstance(actor, Mapping):
        raise ValueError("execution_snapshot.run_manifest.actor must be an object")
    actor_unknown = sorted(set(actor) - {"id", "role", "is_superuser"})
    if actor_unknown:
        raise ValueError(
            "execution_snapshot.run_manifest.actor contains unsupported fields: "
            + ", ".join(actor_unknown)
        )
    actor_missing = sorted({"id", "role", "is_superuser"} - set(actor))
    if actor_missing:
        raise ValueError(
            "execution_snapshot.run_manifest.actor is missing required fields: "
            + ", ".join(actor_missing)
        )
    actor_id_value = _manifest_text(actor["id"], field="actor.id")
    actor_role_value = _manifest_text(actor["role"], field="actor.role").lower()
    if actor_role_value not in KNOWN_ROLES:
        raise ValueError("execution_snapshot.run_manifest.actor.role is unsupported")
    actor_is_superuser = actor["is_superuser"]
    if not isinstance(actor_is_superuser, bool):
        raise ValueError(
            "execution_snapshot.run_manifest.actor.is_superuser must be a boolean"
        )

    selected_tag = _manifest_selector(manifest["selected_tag"], field="selected_tag")
    selected_name = _manifest_selector(
        manifest["selected_name"], field="selected_name"
    )
    if selected_tag is not None and selected_name is not None:
        raise ValueError(
            "execution_snapshot.run_manifest may specify selected_tag or "
            "selected_name, not both"
        )
    case_count = manifest["case_count"]
    if (
        isinstance(case_count, bool)
        or not isinstance(case_count, int)
        or not 1 <= case_count <= 100_000
    ):
        raise ValueError(
            "execution_snapshot.run_manifest.case_count must be an integer "
            "between 1 and 100000"
        )
    default_timeout = manifest["default_timeout"]
    if (
        isinstance(default_timeout, bool)
        or not isinstance(default_timeout, int)
        or not 1 <= default_timeout <= MAX_CASE_TIMEOUT_SECONDS
    ):
        raise ValueError(
            "execution_snapshot.run_manifest.default_timeout must be an integer "
            "between 1 and 3600"
        )
    judge_model_config_id = _manifest_text(
        manifest["judge_model_config_id"],
        field="judge_model_config_id",
        allow_empty=True,
    )
    return {
        "version": SUITE_RUN_EXECUTION_MANIFEST_VERSION,
        "actor": {
            "id": actor_id_value,
            "role": actor_role_value,
            "is_superuser": actor_is_superuser,
        },
        "selected_tag": selected_tag,
        "selected_name": selected_name,
        "case_count": case_count,
        "default_timeout": default_timeout,
        "judge_model_config_id": judge_model_config_id,
    }


def suite_run_execution_manifest(snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Extract a required immutable worker manifest from a frozen snapshot."""
    raw_manifest = snapshot.get("run_manifest")
    if raw_manifest is None:
        raise ValueError("Eval suite run is missing its execution manifest")
    return normalize_suite_run_execution_manifest(raw_manifest)


def normalize_suite_run_execution_snapshot(value: Any) -> dict[str, Any]:
    """Validate a private frozen Suite execution input.

    The runner builds this at enqueue time from the selected Suite.  It
    deliberately remains separate from the public ``summary`` so a worker can
    resume its frozen target and manifest without returning private execution
    metadata through normal SuiteRun list/get endpoints.  Selected Case
    definitions are *not* duplicated here: the ordered CaseRun work items own
    them exclusively.
    """
    snapshot = _canonical_private_case_run_mapping(
        value,
        field="execution_snapshot",
        max_bytes=MAX_SUITE_RUN_EXECUTION_SNAPSHOT_BYTES,
    )
    if not snapshot:
        return {}

    supported = {
        "version",
        "suite_id",
        "suite_name",
        "suite_tags",
        "target",
        "run_manifest",
    }
    unknown = sorted(set(snapshot) - supported)
    if unknown:
        raise ValueError(
            "execution_snapshot contains unsupported fields: " + ", ".join(unknown)
        )

    version = snapshot.get("version")
    if isinstance(version, bool) or version != SUITE_RUN_EXECUTION_SNAPSHOT_VERSION:
        raise ValueError(
            "execution_snapshot.version must be "
            f"{SUITE_RUN_EXECUTION_SNAPSHOT_VERSION}"
        )
    suite_id = snapshot.get("suite_id")
    if not isinstance(suite_id, str) or not (normalized_suite_id := suite_id.strip()):
        raise ValueError("execution_snapshot.suite_id must be a non-empty string")
    target = snapshot.get("target")
    if not isinstance(target, Mapping):
        raise ValueError("execution_snapshot.target must be an object")
    target_kind = target.get("kind")
    target_id = target.get("id")
    if not isinstance(target_kind, str) or target_kind not in {"agent", "team"}:
        raise ValueError("execution_snapshot.target.kind must be 'agent' or 'team'")
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValueError("execution_snapshot.target.id must be a non-empty string")

    # Suite tags are evaluator-relevant even though the editable Suite is not:
    # safety packs and baseline gates derive their immutable pack identity from
    # these tags.  Keep them alongside the frozen target rather than asking a
    # recovered worker to read a potentially edited/deleted Suite.
    if "suite_tags" not in snapshot or not isinstance(snapshot["suite_tags"], list):
        raise ValueError("execution_snapshot.suite_tags must be a list")
    suite_tags = _case_tags(snapshot["suite_tags"])
    suite_name = snapshot.get("suite_name", "")
    if not isinstance(suite_name, str):
        raise ValueError("execution_snapshot.suite_name must be a string")

    canonical_snapshot = {
        "version": SUITE_RUN_EXECUTION_SNAPSHOT_VERSION,
        "suite_id": normalized_suite_id,
        "suite_name": suite_name.strip(),
        "suite_tags": suite_tags,
        "target": {"kind": target_kind, "id": target_id.strip()},
    }
    if "run_manifest" in snapshot:
        canonical_snapshot["run_manifest"] = normalize_suite_run_execution_manifest(
            snapshot["run_manifest"]
        )
    return _canonical_private_case_run_mapping(
        canonical_snapshot,
        field="execution_snapshot",
        max_bytes=MAX_SUITE_RUN_EXECUTION_SNAPSHOT_BYTES,
    )


def normalize_performance_config(value: Any) -> dict[str, int | bool]:
    """Validate the complete, bounded ``PerformanceEval`` execution contract.

    ``PerformanceEval`` accepts arbitrary integers and will execute its target
    repeatedly for warm-ups, runtime samples, and memory samples.  Persist a
    small explicit configuration instead of passing an opaque JSON blob through
    to Agno: each selected performance Case then has predictable cost and can
    be reproduced from its definition alone.
    """
    if value is None:
        raw: Mapping[Any, Any] = {}
    elif isinstance(value, Mapping):
        raw = value
    else:
        raise ValueError("performance_config must be an object")

    supported_keys = {
        "warmup_runs",
        "num_iterations",
        "measure_runtime",
        "measure_memory",
    }
    unsupported_keys = sorted(
        str(key) for key in raw if not isinstance(key, str) or key not in supported_keys
    )
    if unsupported_keys:
        raise ValueError(
            "performance_config contains unsupported fields: "
            + ", ".join(unsupported_keys)
        )

    def integer(
        key: str,
        *,
        default: int,
        minimum: int,
        maximum: int,
    ) -> int:
        if key not in raw:
            return default
        candidate = raw[key]
        if isinstance(candidate, bool) or not isinstance(candidate, int):
            raise ValueError(
                f"performance_config.{key} must be an integer between "
                f"{minimum} and {maximum}"
            )
        if not minimum <= candidate <= maximum:
            raise ValueError(
                f"performance_config.{key} must be an integer between "
                f"{minimum} and {maximum}"
            )
        return candidate

    def boolean(key: str, *, default: bool) -> bool:
        if key not in raw:
            return default
        candidate = raw[key]
        if not isinstance(candidate, bool):
            raise ValueError(f"performance_config.{key} must be a boolean")
        return candidate

    normalized = {
        "warmup_runs": integer(
            "warmup_runs",
            default=DEFAULT_PERFORMANCE_WARMUP_RUNS,
            minimum=0,
            maximum=MAX_PERFORMANCE_WARMUP_RUNS,
        ),
        "num_iterations": integer(
            "num_iterations",
            default=DEFAULT_PERFORMANCE_NUM_ITERATIONS,
            minimum=1,
            maximum=MAX_PERFORMANCE_NUM_ITERATIONS,
        ),
        "measure_runtime": boolean("measure_runtime", default=True),
        "measure_memory": boolean("measure_memory", default=False),
    }
    if not normalized["measure_runtime"] and not normalized["measure_memory"]:
        raise ValueError(
            "performance_config must enable measure_runtime or measure_memory"
        )
    return normalized


def _eval_types(value: Any) -> list[str]:
    """Normalize a new Case's explicitly requested Agno checks.

    A Case must name at least one check. Do not silently insert Accuracy for a
    missing value: it has a distinct expected-output contract and guessing it
    turns a malformed request into a confusing later validation failure.
    """
    if value is None:
        raise ValueError("eval_types is required")
    if not isinstance(value, list):
        raise ValueError("eval_types must be a list")
    if not value:
        raise ValueError("eval_types must contain at least one evaluation type")
    if not all(isinstance(item, str) for item in value):
        raise ValueError("eval_types must be a list of strings")
    types = list(dict.fromkeys(item.strip() for item in value if item.strip()))
    if not types:
        raise ValueError("eval_types must contain at least one evaluation type")
    unsupported = sorted(set(types) - SUPPORTED_EVAL_TYPES)
    if unsupported:
        raise ValueError(f"Unsupported eval type: {', '.join(unsupported)}")
    return types


def _judge_mode(value: Any) -> str:
    """Validate the first-class mode that maps to Agno scoring_strategy."""
    if value is None:
        return "binary"
    if not isinstance(value, str):
        raise ValueError("judge_mode must be either 'binary' or 'numeric'")
    mode = value.strip().lower()
    if mode not in SUPPORTED_JUDGE_MODES:
        raise ValueError("judge_mode must be either 'binary' or 'numeric'")
    return mode


def _threshold(value: Any) -> int:
    if value is None:
        return 7
    if isinstance(value, bool):
        raise ValueError("threshold must be an integer between 1 and 10")
    try:
        threshold = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("threshold must be an integer between 1 and 10") from exc
    if not 1 <= threshold <= 10:
        raise ValueError("threshold must be an integer between 1 and 10")
    return threshold


def _validate_case_contract(values: Mapping[str, Any]) -> None:
    """Reject incomplete evaluator contracts before they reach a runner.

    This mirrors Agno Case's useful configurations while making the API's
    selected checks unambiguous: a judge needs criteria, Accuracy needs a
    reference output, and Reliability needs at least one expected tool.  Tool
    argument contracts must describe only tools that Reliability is allowed to
    evaluate.
    """
    eval_types = values.get("eval_types")
    if not isinstance(eval_types, list) or not eval_types:
        raise ValueError("eval_types must contain at least one evaluation type")
    selected = set(eval_types)
    if "agent_as_judge" in selected and not _string(values.get("criteria")).strip():
        raise ValueError("agent_as_judge evals require criteria")
    if "accuracy" in selected and not _string(values.get("expected_output")).strip():
        raise ValueError("accuracy evals require expected_output")
    expected_tool_calls = values.get("expected_tool_calls")
    if not isinstance(expected_tool_calls, list):
        raise ValueError("expected_tool_calls must be a list")
    tool_names = set(expected_tool_calls)
    if "reliability" in selected and not tool_names:
        raise ValueError("reliability evals require expected_tool_calls")
    argument_contract = values.get("expected_tool_call_arguments")
    if not isinstance(argument_contract, Mapping):
        raise ValueError("expected_tool_call_arguments must be an object")
    unexpected_contract_tools = sorted(
        str(tool_name) for tool_name in argument_contract if tool_name not in tool_names
    )
    if unexpected_contract_tools:
        raise ValueError(
            "expected_tool_call_arguments keys must be included in "
            "expected_tool_calls: "
            + ", ".join(unexpected_contract_tools)
        )


def _bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _timeout_seconds(value: Any) -> int | None:
    """Validate Agno's optional per-Case timeout without treating ``0`` as unset."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("timeout_seconds must be an integer between 1 and 3600")
    try:
        timeout = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "timeout_seconds must be an integer between 1 and 3600"
        ) from exc
    if not 1 <= timeout <= MAX_CASE_TIMEOUT_SECONDS:
        raise ValueError("timeout_seconds must be an integer between 1 and 3600")
    return timeout


def _stored_timeout_seconds(value: Any) -> int | None:
    """Tolerate malformed historical rows while making new writes strict."""
    try:
        return _timeout_seconds(value)
    except ValueError:
        return None


def _completed_at(status: str) -> datetime | None:
    if status in {
        "passed",
        "failed",
        "error",
        "cancelled",
        "completed",
        "skipped",
    }:
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


def build_create_case_values(payload: dict[str, Any]) -> dict[str, Any]:
    """Build and validate the database values for a new Eval Case."""
    if "target" in payload or "target_agent_id" in payload:
        raise ValueError("Eval Case target is inherited from its Suite")
    values = {
        "id": uuid4().hex,
        "suite_id": _require_text(payload, "suite_id"),
        "name": _require_text(payload, "name"),
        "description": _string(payload.get("description")),
        "input": _require_text(payload, "input"),
        "expected_output": _string(payload.get("expected_output")),
        "criteria": _string(payload.get("criteria")),
        "judge_mode": _judge_mode(payload.get("judge_mode")),
        "additional_guidelines": _additional_guidelines(
            payload.get("additional_guidelines")
        ),
        "threshold": _threshold(payload.get("threshold")),
        "eval_types": _eval_types(payload.get("eval_types")),
        "expected_tool_calls": _string_list(payload.get("expected_tool_calls")),
        "expected_tool_call_arguments": normalize_expected_tool_call_arguments(
            payload.get("expected_tool_call_arguments")
        ),
        "allow_additional_tool_calls": _bool(
            payload.get("allow_additional_tool_calls"), True
        ),
        "performance_config": normalize_performance_config(
            payload.get("performance_config")
        ),
        "timeout_seconds": _timeout_seconds(payload.get("timeout_seconds")),
        "metadata": _dict_value(payload.get("metadata")),
        "tags": _case_tags(payload.get("tags")),
        "enabled": _bool(payload.get("enabled"), True),
    }
    _validate_case_contract(values)
    return values


def _filter_update(payload: dict[str, Any], handlers: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, handler in handlers.items():
        if key in payload:
            values[key] = handler(payload[key])
    if not values:
        raise ValueError("No supported fields to update")
    return values


def _project_update(
    payload: dict[str, Any], handlers: dict[str, Any]
) -> dict[str, Any]:
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
        "target": {
            "kind": _string(data.get("target_kind")),
            "id": _string(data.get("target_id")),
        },
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
        "input": _string(data.get("input")),
        "expected_output": _string(data.get("expected_output")),
        "criteria": _string(data.get("criteria")),
        "judge_mode": _judge_mode(data.get("judge_mode")),
        "additional_guidelines": _additional_guidelines(
            data.get("additional_guidelines")
        ),
        "threshold": _threshold(data.get("threshold")),
        "eval_types": _eval_types(data.get("eval_types")),
        "expected_tool_calls": _string_list(data.get("expected_tool_calls")),
        "expected_tool_call_arguments": normalize_expected_tool_call_arguments(
            data.get("expected_tool_call_arguments")
        ),
        "allow_additional_tool_calls": _bool(
            data.get("allow_additional_tool_calls"), True
        ),
        "performance_config": normalize_performance_config(
            data.get("performance_config")
        ),
        "timeout_seconds": _stored_timeout_seconds(data.get("timeout_seconds")),
        "metadata": _dict_value(data.get("metadata")),
        "tags": _case_tags(data.get("tags")),
        "enabled": _bool(data.get("enabled"), True),
        "created_at": _json_value(data.get("created_at")),
        "updated_at": _json_value(data.get("updated_at")),
    }


def build_case_run_definition_snapshot(case: Mapping[Any, Any]) -> dict[str, Any]:
    """Freeze the complete evaluator-relevant Case definition for one run.

    The returned object intentionally retains prompt/reference text because it
    is stored only in ``CaseRun.definition_snapshot``. It excludes mutable
    bookkeeping timestamps so the fingerprint changes only with the Case
    contract, not an unrelated persistence touch.
    """
    if not isinstance(case, Mapping):
        raise ValueError("Case definition snapshot must be an object")
    normalized = normalize_case(case)
    if not normalized["id"].strip():
        raise ValueError("Case definition snapshot requires id")
    if not normalized["suite_id"].strip():
        raise ValueError("Case definition snapshot requires suite_id")
    _validate_case_contract(normalized)
    snapshot = {
        key: normalized[key]
        for key in (
            "id",
            "suite_id",
            "name",
            "description",
            "input",
            "expected_output",
            "criteria",
            "judge_mode",
            "additional_guidelines",
            "threshold",
            "eval_types",
            "expected_tool_calls",
            "expected_tool_call_arguments",
            "allow_additional_tool_calls",
            "performance_config",
            "timeout_seconds",
            "metadata",
            "tags",
            "enabled",
        )
    }
    return normalize_case_run_definition_snapshot(snapshot)


def build_suite_run_execution_snapshot(
    suite: Mapping[Any, Any],
    *,
    run_manifest: Mapping[Any, Any] | None = None,
) -> dict[str, Any]:
    """Freeze only Suite-level input for one execution.

    Case definitions are frozen by :func:`build_suite_run_case_work_items` and
    persisted only on those CaseRun rows.  Keeping this snapshot small avoids
    a second durable copy of every prompt/reference answer.
    """
    if not isinstance(suite, Mapping):
        raise ValueError("Suite execution snapshot requires a suite object")
    normalized_suite = normalize_suite(suite)
    suite_id = normalized_suite["id"].strip()
    # ``get_suite`` returns the public normalised ``target`` object while raw
    # persistence rows use ``target_kind`` / ``target_id``.  Accept both at
    # this internal construction boundary, then persist one canonical target.
    raw_target = suite.get("target")
    target = parse_eval_target(
        raw_target if isinstance(raw_target, Mapping) else normalized_suite["target"],
        require_available=False,
    ).to_dict()
    if not suite_id:
        raise ValueError("Suite execution snapshot requires suite id")

    snapshot: dict[str, Any] = {
        "version": SUITE_RUN_EXECUTION_SNAPSHOT_VERSION,
        "suite_id": suite_id,
        "suite_name": normalized_suite["name"],
        "suite_tags": normalized_suite["tags"],
        "target": target,
    }
    if run_manifest is not None:
        snapshot["run_manifest"] = normalize_suite_run_execution_manifest(run_manifest)
    return normalize_suite_run_execution_snapshot(snapshot)


def build_case_run_execution_provenance(
    *,
    target: Mapping[str, Any],
    actor_role_value: str,
    actor_is_superuser: bool,
    definition_source: str,
    default_timeout: int,
    timeout_seconds: int | float,
    eval_profile: str,
    judge_model_config_id: str,
) -> dict[str, Any]:
    """Build the private, immutable execution contract for one CaseRun."""
    normalized_target = parse_eval_target(target, require_available=False).to_dict()
    normalized_role = str(actor_role_value or "").strip().lower()
    if normalized_role not in KNOWN_ROLES:
        raise ValueError("CaseRun execution provenance actor role is unsupported")
    if not isinstance(actor_is_superuser, bool):
        raise ValueError("CaseRun execution provenance actor superuser must be a boolean")
    normalized_source = str(definition_source or "").strip()
    if not normalized_source:
        raise ValueError("CaseRun execution provenance definition_source is required")
    if len(normalized_source) > _MAX_SUITE_RUN_MANIFEST_TEXT_CHARS:
        raise ValueError("CaseRun execution provenance definition_source is too long")
    if (
        isinstance(default_timeout, bool)
        or not isinstance(default_timeout, int)
        or not 1 <= default_timeout <= MAX_CASE_TIMEOUT_SECONDS
    ):
        raise ValueError("CaseRun execution provenance default_timeout is invalid")
    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise ValueError("CaseRun execution provenance timeout_seconds is invalid")
    normalized_timeout_seconds = float(timeout_seconds)
    if (
        not isfinite(normalized_timeout_seconds)
        or not 0 < normalized_timeout_seconds <= MAX_CASE_TIMEOUT_SECONDS
    ):
        raise ValueError("CaseRun execution provenance timeout_seconds is invalid")
    if eval_profile not in {"full", "tools_off"}:
        raise ValueError("CaseRun execution provenance eval_profile is invalid")
    normalized_judge_model_config_id = str(judge_model_config_id or "").strip()
    if len(normalized_judge_model_config_id) > _MAX_SUITE_RUN_MANIFEST_TEXT_CHARS:
        raise ValueError("CaseRun execution provenance judge model id is too long")
    return normalize_case_run_execution_provenance(
        {
            "version": 1,
            "definition_source": normalized_source,
            "target": normalized_target,
            "actor": {
                "role": normalized_role,
                "is_superuser": actor_is_superuser,
            },
            "default_timeout_seconds": default_timeout,
            "timeout_seconds": (
                int(normalized_timeout_seconds)
                if normalized_timeout_seconds.is_integer()
                else normalized_timeout_seconds
            ),
            "eval_profile": eval_profile,
            "judge_model_config_id": normalized_judge_model_config_id,
        }
    )


def build_suite_run_case_work_items(
    suite_run_id: str,
    execution_snapshot: Mapping[str, Any],
    cases: Sequence[Mapping[Any, Any]],
) -> list[dict[str, Any]]:
    """Pre-create the immutable CaseRun work items for one queued SuiteRun.

    A worker only claims one of these rows; it must never create a new CaseRun
    while executing.  The work item index also gives the database a stable
    identifier for frozen suite order independent of timestamps.
    """
    normalized_suite_run_id = _string(suite_run_id).strip()
    if not normalized_suite_run_id:
        raise ValueError("suite_run_id is required for CaseRun work items")
    if isinstance(cases, (str, bytes)) or not isinstance(cases, Sequence):
        raise ValueError("Eval suite run requires selected CaseRun work items")
    snapshot = normalize_suite_run_execution_snapshot(execution_snapshot)
    manifest = suite_run_execution_manifest(snapshot)
    target = snapshot["target"]
    actor = manifest["actor"]
    default_timeout = manifest["default_timeout"]
    items: list[dict[str, Any]] = []
    for work_item_index, raw_case in enumerate(cases):
        if not isinstance(raw_case, Mapping):
            raise ValueError(
                f"Eval suite run CaseRun work item {work_item_index} must be an object"
            )
        definition = build_case_run_definition_snapshot(raw_case)
        if definition["suite_id"].strip() != snapshot["suite_id"]:
            raise ValueError(
                "Eval suite run CaseRun work item must belong to the frozen Suite"
            )
        timeout_seconds = _stored_timeout_seconds(definition.get("timeout_seconds"))
        if timeout_seconds is None:
            timeout_seconds = default_timeout
        metadata = definition.get("metadata")
        eval_profile = eval_profile_from_metadata(
            metadata if isinstance(metadata, Mapping) else {}
        )
        items.append(
            {
                "id": uuid4().hex,
                "suite_run_id": normalized_suite_run_id,
                "case_id": definition["id"],
                "work_item_index": work_item_index,
                "status": "queued",
                "agent_run_id": "",
                "session_id": "",
                "trace_id": "",
                "agno_eval_run_ids": [],
                "error_type": "",
                "error_summary": "",
                "replay_of_case_run_id": "",
                "definition_snapshot": definition,
                "execution_provenance": build_case_run_execution_provenance(
                    target=target,
                    actor_role_value=str(actor["role"]),
                    actor_is_superuser=bool(actor["is_superuser"]),
                    definition_source="suite_case_work_item",
                    default_timeout=default_timeout,
                    timeout_seconds=timeout_seconds,
                    eval_profile=eval_profile,
                    judge_model_config_id=str(
                        manifest["judge_model_config_id"]
                    ),
                ),
            }
        )
    if not items:
        raise ValueError("Eval suite run requires at least one CaseRun work item")
    if len(items) != manifest["case_count"]:
        raise ValueError(
            "Eval suite run CaseRun work-item count does not match its execution manifest"
        )
    return items


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


def _normalize_suite_run_private(row: Any) -> dict[str, Any]:
    """Internal-only SuiteRun projection including frozen execution input."""
    data = _row_dict(row)
    return {
        **normalize_suite_run(data),
        "execution_snapshot": normalize_suite_run_execution_snapshot(
            data.get("execution_snapshot")
        ),
        "active_job_id": _string(data.get("active_job_id")),
        "active_lease_epoch": int(data.get("active_lease_epoch") or 0),
    }


def suite_case_result_lite(case_run: Mapping[str, Any]) -> dict[str, Any] | None:
    """Project one CaseRun's write-once evidence into a safe Suite result row.

    CaseRun is the durable source of truth for a Suite's per-Case outcome.
    This projection intentionally reads only immutable definition metadata plus
    the bounded terminal checkpoint; it never exposes a Case input, expected
    output, model response, or a free-form evaluator reason.
    """
    data = _row_dict(case_run)
    case_id = _string(data.get("case_id")).strip()
    if not case_id:
        return None

    name = case_id
    try:
        definition = normalize_case_run_definition_snapshot(
            data.get("definition_snapshot")
        )
    except ValueError:
        definition = {}
    if definition:
        name = _string(definition.get("name")).strip() or case_id

    status = _string(data.get("status")).strip()
    error_type = _string(data.get("error_type")).strip()
    error_summary = _string(data.get("error_summary")).strip()
    provenance = data.get("execution_provenance")
    provenance_mapping = provenance if isinstance(provenance, Mapping) else {}
    timeout_seconds = _stored_timeout_seconds(
        provenance_mapping.get("timeout_seconds")
    )
    checkpoint: dict[str, Any] | None = None
    raw_checkpoint = data.get("terminal_checkpoint")
    if isinstance(raw_checkpoint, Mapping) and raw_checkpoint:
        try:
            candidate = normalize_case_run_terminal_checkpoint(raw_checkpoint)
        except ValueError:
            candidate = None
        if candidate is not None and candidate["status"] == status:
            checkpoint = candidate
            timeout_seconds = candidate["timeout_seconds"]

    row: dict[str, Any] = {
        "name": name,
        "case_id": case_id,
        "case_run_id": _string(data.get("id")),
        "session_id": _string(data.get("session_id")),
        "duration_seconds": (
            checkpoint["duration_seconds"] if checkpoint is not None else None
        ),
        "timeout_seconds": timeout_seconds,
        "status": status,
        "passed": status == "passed",
        "timed_out": (
            bool(checkpoint["timed_out"])
            if checkpoint is not None
            else error_type == "EvalCaseTimeout"
        ),
        "skipped": status == "skipped",
        "error_type": error_type,
        "error": (
            error_summary if status in {"failed", "error", "cancelled"} else ""
        ),
        # The checkpoint deliberately excludes evaluator reasoning because it
        # can contain prompt/model text.  Keeping the keys stable gives the
        # frontend and report a uniform CaseResult-lite shape without storing
        # a second mutable result copy on SuiteRun.
        "accuracy_passed": (
            checkpoint["accuracy_passed"] if checkpoint is not None else None
        ),
        "accuracy_reason": None,
        "accuracy_score": (
            checkpoint["accuracy_score"] if checkpoint is not None else None
        ),
        "judge_passed": (
            checkpoint["judge_passed"] if checkpoint is not None else None
        ),
        "judge_reason": None,
        "judge_score": checkpoint["judge_score"] if checkpoint is not None else None,
        "reliability_passed": (
            checkpoint["reliability_passed"] if checkpoint is not None else None
        ),
        "judge_id": checkpoint["judge_id"] if checkpoint is not None else "",
        "eval_profile": (
            checkpoint["eval_profile"]
            if checkpoint is not None
            else _string(provenance_mapping.get("eval_profile"))
        ),
    }
    if checkpoint is not None:
        if checkpoint["reliability_evidence"] is not None:
            row["reliability_evidence"] = checkpoint["reliability_evidence"]
        if checkpoint["performance"] is not None:
            row["performance"] = checkpoint["performance"]
    return row


def normalize_case_run(row: Any) -> dict[str, Any]:
    data = _row_dict(row)
    normalized = {
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
        # Definition contents may include prompt/reference text. The stable
        # hash makes provenance/comparison possible without exposing either
        # the raw definition or execution provenance via normal APIs.
        "definition_snapshot_sha256": _definition_snapshot_sha256(
            data.get("definition_snapshot")
        ),
        "started_at": _json_value(data.get("started_at")),
        "completed_at": _json_value(data.get("completed_at")),
    }
    result = suite_case_result_lite(data)
    if result is not None:
        normalized["result"] = result
    return normalized


def _normalize_case_run_private(row: Any) -> dict[str, Any]:
    """Internal-only CaseRun projection used by durable replay logic."""
    data = _row_dict(row)
    raw_terminal_checkpoint = data.get("terminal_checkpoint")
    terminal_checkpoint = (
        {}
        if raw_terminal_checkpoint is None or raw_terminal_checkpoint == {}
        else normalize_case_run_terminal_checkpoint(raw_terminal_checkpoint)
    )
    return {
        **normalize_case_run(data),
        "definition_snapshot": normalize_case_run_definition_snapshot(
            data.get("definition_snapshot")
        ),
        "execution_provenance": normalize_case_run_execution_provenance(
            data.get("execution_provenance")
        ),
        "terminal_checkpoint": terminal_checkpoint,
        "work_item_index": (
            int(data["work_item_index"])
            if isinstance(data.get("work_item_index"), int)
            and not isinstance(data.get("work_item_index"), bool)
            else None
        ),
        "lease_job_id": _string(data.get("lease_job_id")),
        "lease_epoch": int(data.get("lease_epoch") or 0),
    }


async def create_suite(
    payload: dict[str, Any],
    actor: Any,
    *,
    allow_imported_pack_mutation: bool = False,
) -> dict[str, Any]:
    raw_tags = payload.get("tags")
    if not allow_imported_pack_mutation:
        _assert_no_reserved_pack_tags(raw_tags)
    target = parse_eval_target(payload.get("target"))
    values = {
        "id": uuid4().hex,
        "name": _require_text(payload, "name"),
        "description": _string(payload.get("description")),
        "target_kind": target.kind,
        "target_id": target.id,
        "enabled": _bool(payload.get("enabled"), True),
        "tags": _string_list(raw_tags),
        "created_by": actor_id(actor),
    }
    row = await create_suite_row_async(values=values)
    return normalize_suite(row)


async def list_suites(enabled: bool | None = None) -> dict[str, Any]:
    """Agno-style ``{data, meta}`` for suite definitions (full list)."""
    rows = await list_suite_rows_async(enabled=enabled)
    items = [normalize_suite(row) for row in rows]
    return {
        "data": items,
        "meta": pagination_meta(
            page=1,
            limit=max(len(items), 1),
            total_count=len(items),
        ),
    }


async def get_suite(suite_id: str) -> dict[str, Any] | None:
    row = await get_suite_row_async(suite_id)
    return normalize_suite(row) if row is not None else None


async def update_suite(
    suite_id: str,
    payload: dict[str, Any],
    *,
    allow_imported_pack_mutation: bool = False,
) -> dict[str, Any] | None:
    existing = await get_suite(suite_id)
    if existing is None:
        return None
    if (
        not allow_imported_pack_mutation
        and _imported_pack_identity(existing.get("tags")) is not None
    ):
        raise ValueError(
            "Imported eval pack suites are immutable; remove and re-import the pack instead"
        )
    if not allow_imported_pack_mutation and "tags" in payload:
        _assert_no_reserved_pack_tags(payload["tags"])
    if "target" in payload or "target_agent_id" in payload:
        raise ValueError(
            "Eval Suite target is immutable; create a new Suite to evaluate another target"
        )
    values = _filter_update(
        payload,
        {
            "name": lambda value: _string(value).strip(),
            "description": _string,
            "enabled": lambda value: _bool(value, True),
            "tags": _string_list,
        },
    )
    row = await update_suite_row_async(suite_id, values)
    return normalize_suite(row) if row is not None else None


async def delete_suite(suite_id: str) -> dict[str, Any] | None:
    """Delete one author-owned Suite and its complete workbench history.

    Imported Packs are intentionally excluded: their identity/version boundary
    must be removed through ``remove_imported_pack`` so an operator explicitly
    sees the Pack version being purged.
    """
    normalized_suite_id = _string(suite_id).strip()
    if not normalized_suite_id:
        raise ValueError("suite_id is required")
    existing = await get_suite(normalized_suite_id)
    if existing is None:
        return None
    if _imported_pack_identity(existing.get("tags")) is not None:
        raise ValueError(
            "Imported eval pack suites are immutable; remove and re-import the pack instead"
        )
    return await delete_suite_rows_async(normalized_suite_id)


async def remove_imported_pack(
    pack_id: str,
    *,
    pack_version: str,
) -> dict[str, Any]:
    """Remove one imported safety pack version and its run history."""
    normalized_pack_id = _string(pack_id).strip()
    normalized_pack_version = _string(pack_version).strip()
    if not normalized_pack_id:
        raise ValueError("pack_id is required")
    if not normalized_pack_version:
        raise ValueError("pack_version is required")
    return await remove_imported_pack_rows_async(
        normalized_pack_id,
        pack_version=normalized_pack_version,
    )


async def create_case(
    payload: dict[str, Any],
    *,
    allow_imported_pack_mutation: bool = False,
) -> dict[str, Any]:
    values = build_create_case_values(payload)
    suite_id = values["suite_id"]
    if (
        await _require_mutable_suite(
            suite_id,
            allow_imported_pack_mutation=allow_imported_pack_mutation,
        )
        is None
    ):
        raise ValueError("Eval suite not found")
    row = await create_case_row_async(values=values)
    return normalize_case(row)


async def import_pack(
    *,
    pack_id: str,
    pack_version: str,
    artifact_hash: str,
    suite_payload: dict[str, Any],
    case_payloads: list[dict[str, Any]],
    actor: Any,
) -> dict[str, Any]:
    raw_tags = suite_payload.get("tags")
    target = parse_eval_target(suite_payload.get("target"))
    suite_values = {
        "id": uuid4().hex,
        "name": _require_text(suite_payload, "name"),
        "description": _string(suite_payload.get("description")),
        "target_kind": target.kind,
        "target_id": target.id,
        "enabled": _bool(suite_payload.get("enabled"), True),
        "tags": _string_list(raw_tags),
        "created_by": actor_id(actor),
    }
    case_values = [build_create_case_values(payload) for payload in case_payloads]
    seen_external_ids: set[str] = set()
    duplicate_external_ids: set[str] = set()
    for values in case_values:
        metadata = values.get("metadata")
        external_id = (
            _string(metadata.get("external_id")).strip()
            if isinstance(metadata, Mapping)
            else ""
        )
        if not external_id:
            raise ValueError("Imported eval case external_id is required")
        if external_id in seen_external_ids:
            duplicate_external_ids.add(external_id)
        seen_external_ids.add(external_id)
    if duplicate_external_ids:
        raise ValueError(
            "Imported eval pack contains duplicate external_id values: "
            + ", ".join(sorted(duplicate_external_ids))
        )
    result = await import_pack_rows_async(
        pack_id=pack_id,
        pack_version=pack_version,
        artifact_hash=artifact_hash,
        suite_values=suite_values,
        case_values=case_values,
    )
    return {
        **result,
        "suite": normalize_suite(result["suite"]),
    }


async def list_cases(
    suite_id: str | None = None,
    enabled: bool | None = None,
    tag: str | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    """Return every matching Case for the Runner and Pack importer.

    This is intentionally not the public page endpoint: a Suite can contain
    more than 500 curated Cases, and silently truncating that set would make a
    benchmark's metrics and import idempotency incorrect.
    """
    rows = await list_case_rows_async(
        suite_id=suite_id,
        enabled=enabled,
        tag=_selected_case_tag(tag),
        name=_selected_case_name(name),
    )
    items = [normalize_case(row) for row in rows]
    return {
        "data": items,
        "meta": pagination_meta(
            page=1,
            limit=max(len(items), 1),
            total_count=len(items),
        ),
    }


async def list_cases_page(
    suite_id: str | None = None,
    enabled: bool | None = None,
    tag: str | None = None,
    name: str | None = None,
    *,
    page: int = 1,
    limit: int = 100,
) -> dict[str, Any]:
    """Browser/API page for Case authoring without exposing an entire pack."""
    safe_page = max(1, int(page or 1))
    safe_limit = max(1, min(int(limit or 100), 100))
    rows, total = await list_case_rows_page_async(
        suite_id=suite_id,
        enabled=enabled,
        tag=_selected_case_tag(tag),
        name=_selected_case_name(name),
        page=safe_page,
        limit=safe_limit,
    )
    return {
        "data": [normalize_case(row) for row in rows],
        "meta": pagination_meta(
            page=safe_page,
            limit=safe_limit,
            total_count=total,
        ),
    }


async def get_case(case_id: str) -> dict[str, Any] | None:
    row = await get_case_row_async(case_id)
    return normalize_case(row) if row is not None else None


async def update_case(
    case_id: str,
    payload: dict[str, Any],
    *,
    allow_imported_pack_mutation: bool = False,
) -> dict[str, Any] | None:
    if "target" in payload or "target_agent_id" in payload:
        raise ValueError("Eval Case target is inherited from its Suite")
    values = _filter_update(
        payload,
        {
            "suite_id": lambda value: _string(value).strip(),
            "name": lambda value: _string(value).strip(),
            "description": _string,
            "input": _string,
            "expected_output": _string,
            "criteria": _string,
            "judge_mode": _judge_mode,
            "additional_guidelines": _additional_guidelines,
            "threshold": _threshold,
            "eval_types": _eval_types,
            "expected_tool_calls": _string_list,
            "expected_tool_call_arguments": normalize_expected_tool_call_arguments,
            "allow_additional_tool_calls": lambda value: _bool(value, True),
            "performance_config": normalize_performance_config,
            "timeout_seconds": _timeout_seconds,
            "metadata": _dict_value,
            "tags": _case_tags,
            "enabled": lambda value: _bool(value, True),
        },
    )
    existing = await get_case(case_id)
    if existing is None:
        return None
    existing_suite_id = _string(existing.get("suite_id")).strip()
    existing_suite = await _require_mutable_suite(
        existing_suite_id,
        allow_imported_pack_mutation=allow_imported_pack_mutation,
    )
    if existing_suite is None:
        raise ValueError("Eval suite not found")
    if "suite_id" in payload:
        target_suite_id = _string(payload["suite_id"]).strip()
        if not target_suite_id:
            raise ValueError("suite_id is required")
        target_suite = await _require_mutable_suite(
            target_suite_id,
            allow_imported_pack_mutation=allow_imported_pack_mutation,
        )
        if target_suite is None:
            raise ValueError("Eval suite not found")
    _validate_case_contract({**existing, **values})
    row = await update_case_row_async(case_id, values)
    return normalize_case(row) if row is not None else None


async def delete_case(case_id: str) -> dict[str, Any] | None:
    """Delete one author-owned Case definition without rewriting run history."""
    normalized_case_id = _string(case_id).strip()
    if not normalized_case_id:
        raise ValueError("case_id is required")
    existing = await get_case(normalized_case_id)
    if existing is None:
        return None
    suite_id = _string(existing.get("suite_id")).strip()
    suite = await _require_mutable_suite(
        suite_id,
        allow_imported_pack_mutation=False,
    )
    if suite is None:
        raise ValueError("Eval suite not found")
    row = await delete_case_row_async(normalized_case_id)
    return normalize_case(row) if row is not None else None


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


async def get_suite_run(suite_run_id: str) -> dict[str, Any] | None:
    row = await get_suite_run_row_async(suite_run_id)
    return normalize_suite_run(row) if row is not None else None


async def get_suite_run_private(suite_run_id: str) -> dict[str, Any] | None:
    """Return frozen SuiteRun input for internal durable runner use only."""
    row = await get_suite_run_row_async(suite_run_id)
    return _normalize_suite_run_private(row) if row is not None else None


async def claim_suite_run_execution(
    suite_run_id: str,
    *,
    execution_lease: SuiteRunExecutionLease,
) -> dict[str, Any] | None:
    """Atomically fence a queued/recovered durable SuiteRun worker.

    Returning ``None`` is intentional: it means another lease is already the
    authority (or the run is terminal), so the caller must raise its durable
    lease-lost path instead of constructing a local Suite summary.
    """
    row = await claim_suite_run_execution_row_async(
        suite_run_id,
        job_id=execution_lease.job_id,
        lease_epoch=execution_lease.lease_epoch,
    )
    return _normalize_suite_run_private(row) if row is not None else None


async def update_suite_run_progress(
    suite_run_id: str,
    *,
    summary: Mapping[str, Any],
    execution_lease: SuiteRunExecutionLease,
) -> dict[str, Any] | None:
    """Persist partial progress only while the worker still owns ``running``.

    A cancellation request transitions the row to ``cancelling``.  Conditional
    writes ensure an in-flight completion cannot erase that operator intent.
    """
    row = await update_suite_run_row_if_execution_lease_async(
        suite_run_id,
        expected_statuses=("running",),
        job_id=execution_lease.job_id,
        lease_epoch=execution_lease.lease_epoch,
        values={"summary": _dict_value(summary)},
    )
    return normalize_suite_run(row) if row is not None else None


async def request_suite_run_cancel(suite_run_id: str) -> dict[str, Any] | None:
    """Request cooperative cancellation of a queued or running SuiteRun.

    The durable job remains lease-recoverable.  Its handler observes this
    durable marker, stops the active Case, marks pending Cases skipped, and
    then commits the terminal ``cancelled`` result itself.
    """
    row = await request_suite_run_cancel_row_async(
        suite_run_id,
        cancel_requested_at=datetime.now(UTC).isoformat(),
    )
    return normalize_suite_run(row) if row is not None else None


async def suite_run_cancel_requested(suite_run_id: str) -> bool:
    """Return whether a worker should cooperatively stop this SuiteRun."""
    row = await get_suite_run(suite_run_id)
    if row is None:
        return True
    return row["status"] in {"cancelling", "cancelled"}


async def create_case_run(
    case_id: str,
    suite_run_id: str | None = None,
    replay_of_case_run_id: str | None = None,
    *,
    definition_snapshot: Mapping[str, Any] | None = None,
    execution_provenance: Mapping[str, Any] | None = None,
    replay_from_snapshot: bool = False,
) -> dict[str, Any]:
    """Persist a CaseRun with immutable private execution evidence.

    ``replay_from_snapshot`` is the only path that may create a direct
    CaseRun after its editable Case has been deleted. It must name a source
    CaseRun and persist the exact frozen source definition; the persistence
    layer locks and verifies that source before inserting the replay row.
    """
    normalized_definition_snapshot = normalize_case_run_definition_snapshot(
        definition_snapshot
    )
    normalized_execution_provenance = normalize_case_run_execution_provenance(
        execution_provenance
    )
    replay_source_case_run_id = _string(replay_of_case_run_id).strip()
    if replay_from_snapshot:
        if not replay_source_case_run_id:
            raise ValueError("replay_from_snapshot requires replay_of_case_run_id")
        if not normalized_definition_snapshot:
            raise ValueError("replay_from_snapshot requires definition_snapshot")
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
        "replay_of_case_run_id": replay_source_case_run_id,
        "definition_snapshot": normalized_definition_snapshot,
        "execution_provenance": normalized_execution_provenance,
    }
    if replay_from_snapshot:
        row = await create_case_run_row_async(
            values=values,
            replay_source_case_run_id=replay_source_case_run_id,
        )
    else:
        row = await create_case_run_row_async(values=values)
    return normalize_case_run(row)


async def claim_suite_case_run(
    case_id: str,
    *,
    suite_run_id: str,
    definition_snapshot: Mapping[str, Any],
    execution_provenance: Mapping[str, Any],
    execution_lease: SuiteRunExecutionLease,
) -> SuiteCaseRunClaim | None:
    """Acquire one pre-created CaseRun work item for a fenced Suite execution.

    A later durable epoch may take over an unfinished row, but it never creates
    a sibling CaseRun for the same frozen Suite Case. Terminal rows are handed
    back with ``acquired=False`` so the runner can recover their checkpoint
    without invoking the target again. A missing work item returns ``None``
    and must be treated as a fenced execution invariant failure.
    """
    normalized_case_id = _string(case_id).strip()
    normalized_suite_run_id = _string(suite_run_id).strip()
    if not normalized_case_id or not normalized_suite_run_id:
        raise ValueError("fenced CaseRun requires case_id and suite_run_id")
    values = {
        "id": uuid4().hex,
        "suite_run_id": normalized_suite_run_id,
        "case_id": normalized_case_id,
        "status": "running",
        "agent_run_id": "",
        "session_id": "",
        "trace_id": "",
        "agno_eval_run_ids": [],
        "error_type": "",
        "error_summary": "",
        "replay_of_case_run_id": "",
        "definition_snapshot": normalize_case_run_definition_snapshot(
            definition_snapshot
        ),
        "execution_provenance": normalize_case_run_execution_provenance(
            execution_provenance
        ),
    }
    claimed = await claim_suite_case_run_row_async(
        values,
        job_id=execution_lease.job_id,
        lease_epoch=execution_lease.lease_epoch,
    )
    if claimed is None:
        return None
    row, acquired = claimed
    private_row = _normalize_case_run_private(row)
    existing_definition = private_row.get("definition_snapshot")
    if existing_definition != values["definition_snapshot"]:
        raise ValueError(
            "fenced CaseRun definition does not match the frozen Suite execution"
        )
    existing_provenance = private_row.get("execution_provenance")
    requested_target = values["execution_provenance"].get("target")
    existing_target = (
        existing_provenance.get("target")
        if isinstance(existing_provenance, Mapping)
        else None
    )
    if existing_target != requested_target:
        raise ValueError(
            "fenced CaseRun target does not match the frozen Suite execution"
        )
    return SuiteCaseRunClaim(
        case_run=private_row,
        acquired=acquired,
    )


async def get_case_run(case_run_id: str) -> dict[str, Any] | None:
    row = await get_case_run_row_async(case_run_id)
    return normalize_case_run(row) if row is not None else None


async def get_case_run_private(case_run_id: str) -> dict[str, Any] | None:
    """Return frozen CaseRun evidence for internal replay logic only."""
    row = await get_case_run_row_async(case_run_id)
    return _normalize_case_run_private(row) if row is not None else None


async def list_suite_run_case_work_items_private(
    suite_run_id: str,
) -> list[dict[str, Any]]:
    """Return one SuiteRun's pre-created CaseRun work items in frozen order.

    These rows are the sole durable owner of selected Case definitions.  The
    strict index and identity checks turn a missing/corrupt work item into an
    execution invariant failure instead of falling back to editable Case rows.
    """
    rows = await list_suite_run_case_work_item_rows_async(suite_run_id)
    work_items = [_normalize_case_run_private(row) for row in rows]
    if not work_items:
        return []
    seen_case_ids: set[str] = set()
    for expected_index, work_item in enumerate(work_items):
        work_item_index = work_item.get("work_item_index")
        case_id = _string(work_item.get("case_id")).strip()
        definition = work_item.get("definition_snapshot")
        if work_item_index != expected_index or not case_id:
            raise ValueError("SuiteRun CaseRun work items have invalid frozen order")
        if case_id in seen_case_ids:
            raise ValueError("SuiteRun CaseRun work items contain duplicate Cases")
        if (
            not isinstance(definition, Mapping)
            or _string(definition.get("id")).strip() != case_id
        ):
            raise ValueError("SuiteRun CaseRun work item definition does not match its Case")
        seen_case_ids.add(case_id)
    return work_items


async def list_suite_run_case_result_lites(
    suite_run_id: str,
) -> list[dict[str, Any]]:
    """Return ordered, privacy-safe CaseResult-lite rows for one SuiteRun.

    Every result field and its ordering are derived from the pre-created
    CaseRun work item, rather than a mutable ``SuiteRun.summary`` cache or a
    duplicate SuiteRun snapshot of the selected Cases.
    """
    results: list[dict[str, Any]] = []
    for case_run in await list_suite_run_case_work_items_private(suite_run_id):
        result = suite_case_result_lite(case_run)
        if result is not None:
            results.append(result)
    return results


async def list_case_runs_by_agno_eval_run_ids(
    eval_run_ids: list[str],
) -> dict[str, dict[str, Any]]:
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


async def mark_case_run(
    case_run_id: str,
    status: str,
    values: dict[str, Any],
    *,
    execution_lease: SuiteRunExecutionLease | None = None,
) -> dict[str, Any] | None:
    terminal_checkpoint = values.get("terminal_checkpoint")
    if terminal_checkpoint is not None:
        # Keep a stable runner-facing write seam while ensuring terminal
        # evidence cannot take the generic, overwrite-capable update path.
        complete_kwargs: dict[str, Any] = {
            "terminal_checkpoint": terminal_checkpoint,
        }
        if execution_lease is not None:
            complete_kwargs["execution_lease"] = execution_lease
        return await complete_case_run(
            case_run_id,
            status,
            {key: value for key, value in values.items() if key != "terminal_checkpoint"},
            **complete_kwargs,
        )
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
    if execution_lease is None:
        row = await update_case_run_row_async(case_run_id, update_values)
    else:
        row = await update_case_run_row_if_execution_lease_async(
            case_run_id,
            job_id=execution_lease.job_id,
            lease_epoch=execution_lease.lease_epoch,
            values=update_values,
        )
    return normalize_case_run(row) if row is not None else None


async def complete_case_run(
    case_run_id: str,
    status: str,
    values: Mapping[str, Any],
    *,
    terminal_checkpoint: Mapping[str, Any],
    execution_lease: SuiteRunExecutionLease | None = None,
) -> dict[str, Any] | None:
    """Atomically persist a terminal CaseRun and its private recovery record.

    Unlike ``mark_case_run``, this is intentionally a one-way lifecycle
    operation.  It is the only service-layer path allowed to write the
    checkpoint, and delegates to a database compare-and-set so a late worker
    cannot replace already committed evaluator evidence.
    """
    normalized_status = _normalize_status(status, "queued")
    if normalized_status not in _TERMINAL_CASE_RUN_STATUSES:
        raise ValueError("terminal checkpoint requires a terminal CaseRun status")
    checkpoint = normalize_case_run_terminal_checkpoint(terminal_checkpoint)
    if checkpoint["status"] != normalized_status:
        raise ValueError("terminal_checkpoint.status must match CaseRun status")
    update_values = _project_update(
        dict(values),
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
    update_values["status"] = normalized_status
    completed_at = _completed_at(normalized_status)
    if completed_at is not None:
        update_values["completed_at"] = completed_at
    row = await complete_case_run_row_if_queued_async(
        case_run_id,
        values=update_values,
        terminal_checkpoint=checkpoint,
        **(
            {
                "job_id": execution_lease.job_id,
                "lease_epoch": execution_lease.lease_epoch,
            }
            if execution_lease is not None
            else {}
        ),
    )
    return normalize_case_run(row) if row is not None else None


async def mark_suite_run(
    suite_run_id: str,
    status: str,
    summary: dict[str, Any],
    error_summary: str = "",
    *,
    expected_statuses: tuple[str, ...],
    execution_lease: SuiteRunExecutionLease,
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
    row = await update_suite_run_row_if_execution_lease_async(
        suite_run_id,
        expected_statuses=expected_statuses,
        job_id=execution_lease.job_id,
        lease_epoch=execution_lease.lease_epoch,
        values=values,
    )
    return normalize_suite_run(row) if row is not None else None
