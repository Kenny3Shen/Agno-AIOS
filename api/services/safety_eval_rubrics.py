"""Versioned safety judge rubrics for AgentAsJudge criteria.

Rubric files live under eval_packs/rubrics/rubrics.yaml. Historical identity uses
``id@version`` so text edits under a new version do not rewrite old judge_id strings.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RUBRICS_PATH = REPO_ROOT / "eval_packs" / "rubrics" / "rubrics.yaml"


def rubrics_path(path: Path | str | None = None) -> Path:
    return Path(path) if path is not None else DEFAULT_RUBRICS_PATH


@lru_cache(maxsize=4)
def _load_rubrics_file(path_str: str) -> dict[str, Any]:
    path = Path(path_str)
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return {}
    rubrics = data.get("rubrics")
    if not isinstance(rubrics, dict):
        return {}
    return {str(k): v for k, v in rubrics.items() if isinstance(v, Mapping)}


def clear_rubric_cache() -> None:
    _load_rubrics_file.cache_clear()


def load_rubric(
    rubric_id: str,
    *,
    path: Path | str | None = None,
) -> dict[str, Any]:
    rid = str(rubric_id or "").strip()
    if not rid:
        raise KeyError("rubric_id is required")
    table = _load_rubrics_file(str(rubrics_path(path).resolve()))
    entry = table.get(rid)
    if entry is None:
        raise KeyError(f"Unknown rubric: {rid}")
    version = str(entry.get("version") or "0").strip() or "0"
    criteria = str(entry.get("criteria") or "").strip()
    if not criteria:
        raise ValueError(f"Rubric {rid!r} has empty criteria")
    return {
        "id": rid,
        "version": version,
        "title": str(entry.get("title") or rid),
        "expected_behavior": str(entry.get("expected_behavior") or "").strip(),
        "criteria": criteria,
        "identity": f"{rid}@{version}",
    }


def format_judge_id(
    *,
    rubric_identity: str = "",
    inline: bool = False,
    model_config_id: str = "",
    scoring_strategy: str = "binary",
    threshold: int = 7,
    additional_guidelines: Sequence[str] | None = None,
) -> str:
    """Build a stable, complete Agent-as-Judge contract identity.

    The selected judge model alone is not enough for a comparable safety
    baseline: binary/numeric mode, numeric threshold, and extra evaluator
    instructions can all change a verdict.  Include each semantic choice in
    the persisted identifier; guideline text itself remains private and is
    represented by a deterministic short SHA-256 fingerprint.
    """
    if rubric_identity:
        base = f"agent_as_judge:{rubric_identity}"
    elif inline:
        base = "agent_as_judge:inline"
    else:
        base = "mvp:status+metadata.safety_expected"

    strategy = str(scoring_strategy or "").strip().lower()
    if strategy not in {"numeric", "binary"}:
        strategy = "binary"
    try:
        numeric_threshold = int(threshold)
    except (TypeError, ValueError):
        numeric_threshold = 7
    numeric_threshold = min(max(numeric_threshold, 1), 10)

    parts = [base, f"mode:{strategy}"]
    if strategy == "numeric":
        parts.append(f"threshold:{numeric_threshold}")

    guidelines = [
        str(guideline).strip()
        for guideline in (additional_guidelines or ())
        if str(guideline).strip()
    ]
    if guidelines:
        encoded = json.dumps(
            guidelines,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        parts.append(f"guidelines:{sha256(encoded).hexdigest()[:16]}")

    model_part = str(model_config_id or "").strip() or "default"
    parts.append(f"model:{model_part}")
    return "+".join(parts)


def resolve_case_judge_criteria(
    case: Mapping[str, Any],
    *,
    rubrics_file: Path | str | None = None,
    judge_model_config_id: str = "",
) -> dict[str, Any]:
    """Resolve criteria text + judge_id for a case.

    Preference: metadata.judge_rubric_id → versioned registry; else case.criteria (inline).
    """
    raw_meta = case.get("metadata")
    meta: dict[str, Any] = dict(raw_meta) if isinstance(raw_meta, Mapping) else {}
    rubric_id = str(
        meta.get("judge_rubric_id")
        or meta.get("rubric_id")
        or case.get("judge_rubric_id")
        or ""
    ).strip()
    threshold = case.get("threshold", 7)
    try:
        threshold_int = int(threshold)
    except (TypeError, ValueError):
        threshold_int = 7

    # Agno Case.judge_mode is a first-class field.  Do not infer evaluator
    # behavior from arbitrary metadata: an absent mode deliberately means the
    # documented binary default, while numeric makes ``threshold`` meaningful.
    raw_mode = str(case.get("judge_mode") or "").strip().lower()
    scoring_strategy = raw_mode if raw_mode in {"numeric", "binary"} else "binary"

    raw_guidelines = case.get("additional_guidelines")
    additional_guidelines = (
        [
            str(guideline).strip()
            for guideline in raw_guidelines
            if isinstance(guideline, str) and guideline.strip()
        ]
        if isinstance(raw_guidelines, list)
        else []
    )

    if rubric_id:
        rubric = load_rubric(rubric_id, path=rubrics_file)
        return {
            "criteria": rubric["criteria"],
            "threshold": threshold_int,
            "scoring_strategy": scoring_strategy,
            "additional_guidelines": additional_guidelines,
            "rubric_id": rubric["id"],
            "rubric_version": rubric["version"],
            "judge_id": format_judge_id(
                rubric_identity=rubric["identity"],
                model_config_id=judge_model_config_id,
                scoring_strategy=scoring_strategy,
                threshold=threshold_int,
                additional_guidelines=additional_guidelines,
            ),
            "source": "rubric",
        }

    criteria = str(case.get("criteria") or "").strip()
    return {
        "criteria": criteria,
        "threshold": threshold_int,
        "scoring_strategy": scoring_strategy,
        "additional_guidelines": additional_guidelines,
        "rubric_id": "",
        "rubric_version": "",
        "judge_id": format_judge_id(
            inline=True,
            model_config_id=judge_model_config_id,
            scoring_strategy=scoring_strategy,
            threshold=threshold_int,
            additional_guidelines=additional_guidelines,
        ),
        "source": "inline" if criteria else "mvp",
    }


def eval_profile_from_metadata(metadata: Mapping[str, Any] | None) -> str:
    """Return ``tools_off`` or ``full`` (default full)."""
    if not isinstance(metadata, Mapping):
        return "full"
    raw = metadata.get("profile") or metadata.get("eval_profile")
    text = str(raw or "").strip().lower()
    if text in {"tools_off", "toolsoff", "no_tools", "agent.tools_off"}:
        return "tools_off"
    if text in {"full", "agent.full", "tools_on", "tools-on"}:
        return "full"
    return "full"
