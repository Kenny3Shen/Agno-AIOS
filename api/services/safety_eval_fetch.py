"""Fetch, normalize, sample, and inventory safety eval packs from HF / local cache.

Data layout (gitignored under ``eval_packs/``)::

    eval_packs/_cache/<pack_id>/<pack_version>/
        raw/                 # optional HF snapshot / dataset export
        full.jsonl           # full normalized intermediate (all rows)
        cases.jsonl          # curated subset for DB import (seeded sample)
        manifest.json        # checksums, counts, source/revision, license, seed

Gate: set ``TAIS_EVAL_PACKS_ALLOW_HARMFUL=1`` (or pass ``allow_harmful=True``)
before downloading packs marked harmful / non-fixture.

Never commit ``_cache/`` or ``_imported/`` full dumps.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

from api.services.safety_eval_pack_service import (
    get_pack_entry,
    load_registry,
    normalize_pack_records,
    packs_root,
)

ALLOW_HARMFUL_ENV = "TAIS_EVAL_PACKS_ALLOW_HARMFUL"
CACHE_DIRNAME = "_cache"
IMPORTED_DIRNAME = "_imported"

# Packs that are internal fixtures / already in git — never require harmful gate.
SAFE_LOCAL_PACKS = frozenset(
    {
        "fixture-synthetic",
        "soc-custom-v1",
        "guardrail-regression-v1",
    }
)

# Curated quick-start baseline: one compact public pack per L1/L2/L3 layer.
# Keep this intentionally small so it can be run interactively before a broader
# regression suite. The exact sample sizes and versions live in registry.yaml.
PUBLIC_LITE_PACK_IDS = (
    "do-not-answer",
    "advbench-sample",
    "prompt-injections",
)

# NC licenses require explicit research flag (same env as harmful for MVP).
NC_LICENSE_MARKERS = ("cc-by-nc", "non-commercial", "nc-4.0", "nc-sa")
_IMMUTABLE_REVISION_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")


def cache_root(root: Path | str | None = None) -> Path:
    return packs_root(root) / CACHE_DIRNAME


def imported_root(root: Path | str | None = None) -> Path:
    return packs_root(root) / IMPORTED_DIRNAME


def pack_cache_dir(
    pack_id: str,
    pack_version: str = "",
    *,
    root: Path | str | None = None,
) -> Path:
    version = (pack_version or "latest").strip() or "latest"
    # filesystem-safe
    safe_ver = re.sub(r"[^\w.\-]+", "_", version)
    return cache_root(root) / pack_id / safe_ver


def allow_harmful_fetch(*, allow_harmful: bool | None = None) -> bool:
    if allow_harmful is not None:
        return bool(allow_harmful)
    raw = str(os.environ.get(ALLOW_HARMFUL_ENV) or "").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def pack_requires_harmful_gate(entry: Mapping[str, Any]) -> bool:
    pack_id = str(entry.get("id") or "").strip()
    if pack_id in SAFE_LOCAL_PACKS:
        return False
    license_text = str(entry.get("license") or "").strip().lower()
    if any(m in license_text for m in NC_LICENSE_MARKERS):
        return True
    # Any HF/github planned pack with no local source.path is treated as harmful-capable.
    source = entry.get("source")
    if isinstance(source, Mapping):
        if source.get("path") and not source.get("hf") and not source.get("github"):
            return False
        if source.get("hf") or source.get("github"):
            return True
    status = str(entry.get("status") or "").strip().lower()
    return status in {"planned", "cached", "ready"} and pack_id not in SAFE_LOCAL_PACKS


def assert_fetch_allowed(
    entry: Mapping[str, Any], *, allow_harmful: bool | None = None
) -> None:
    if not pack_requires_harmful_gate(entry):
        return
    if allow_harmful_fetch(allow_harmful=allow_harmful):
        return
    pack_id = entry.get("id")
    raise PermissionError(
        f"Fetching pack {pack_id!r} requires opt-in: set {ALLOW_HARMFUL_ENV}=1 "
        "(or pass allow_harmful=True). Full harmful dumps stay out of git."
    )


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(dict(row), ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.is_file():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        item = json.loads(text)
        if isinstance(item, Mapping):
            rows.append(dict(item))
    return rows


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    """Read a cache artifact strictly so malformed records cannot be imported."""
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            item = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path.name}:{line_no}: invalid JSON ({exc.msg})") from exc
        if not isinstance(item, Mapping):
            raise ValueError(f"{path.name}:{line_no}: record must be a JSON object")
        rows.append(dict(item))
    return rows


def write_manifest(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_manifest(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return dict(data) if isinstance(data, Mapping) else None


def sample_records(
    records: Sequence[Mapping[str, Any]],
    *,
    sample_size: int | None,
    seed: int = 42,
) -> list[dict[str, Any]]:
    """Deterministic sample; sample_size None or >= len keeps all (stable order)."""
    items = [dict(r) for r in records]
    if sample_size is None or sample_size <= 0 or sample_size >= len(items):
        return items
    rng = random.Random(int(seed))
    # Sample without replacement, then sort by original index for stable JSONL.
    indices = list(range(len(items)))
    chosen = sorted(rng.sample(indices, sample_size))
    return [items[i] for i in chosen]


# ---------------------------------------------------------------------------
# Source adapters: HF row → intermediate pack JSONL shape
# ---------------------------------------------------------------------------

AdapterFn = Callable[[Mapping[str, Any], int, Mapping[str, Any]], dict[str, Any] | None]


@dataclass(frozen=True)
class FetchedRecords:
    """Normalized records together with the source that actually supplied them."""

    records: list[dict[str, Any]]
    source_kind: str
    source_id: str
    source_revision: str = ""
    source_sha256: str = ""


def _first_str(row: Mapping[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        if key not in row:
            continue
        val = row[key]
        if val is None:
            continue
        text = str(val).strip()
        if text:
            return text
    return ""


def adapter_generic(
    row: Mapping[str, Any],
    index: int,
    entry: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Best-effort map for unknown HF schemas."""
    input_text = _first_str(
        row,
        (
            "input",
            "prompt",
            "question",
            "query",
            "text",
            "goal",
            "behavior",
            "instruction",
            "adversarial",
            "forbidden_prompt",
            "user",
            "content",
        ),
    )
    if not input_text:
        return None
    external_id = (
        _first_str(row, ("id", "external_id", "uuid", "uid")) or f"row-{index}"
    )
    pack_id = str(entry.get("id") or "pack")
    expected = str(entry.get("expected_behavior") or "refuse").strip().lower()
    benign = expected in {"answer", "benign_ok", "help"}
    return {
        "external_id": f"{pack_id}-{external_id}",
        "name": f"{pack_id}/{external_id}",
        "layer": str(entry.get("layer") or ""),
        "language": _first_str(row, ("language", "lang")) or "en",
        "benign": benign,
        "expected_behavior": "answer" if benign else expected or "refuse",
        "category": _first_str(row, ("category", "risk_area", "type", "topic")),
        "input": input_text,
        "metadata": {
            "source_row": index,
            "adapter": "generic",
        },
    }


def adapter_do_not_answer(
    row: Mapping[str, Any],
    index: int,
    entry: Mapping[str, Any],
) -> dict[str, Any] | None:
    question = _first_str(row, ("question", "prompt", "input", "text"))
    if not question:
        return None
    rid = _first_str(row, ("id", "qid")) or f"dna-{index}"
    return {
        "external_id": f"dna-{rid}",
        "name": f"do-not-answer/{rid}",
        "layer": "L1",
        "language": "en",
        "benign": False,
        "expected_behavior": "refuse",
        "category": _first_str(row, ("types_of_harm", "risk_area", "category")),
        "input": question,
        "judge_rubric_id": "refusal-v1",
        "metadata": {"adapter": "do-not-answer", "source_row": index},
    }


def adapter_strongreject(
    row: Mapping[str, Any],
    index: int,
    entry: Mapping[str, Any],
) -> dict[str, Any] | None:
    prompt = _first_str(
        row,
        ("forbidden_prompt", "prompt", "goal", "input", "question", "text"),
    )
    if not prompt:
        return None
    rid = _first_str(row, ("id", "key")) or f"sr-{index}"
    return {
        "external_id": f"sr-{rid}",
        "name": f"strongreject/{rid}",
        "layer": "L2",
        "language": "en",
        "benign": False,
        "expected_behavior": "refuse",
        "category": _first_str(row, ("category", "source")),
        "attack_type": "jailbreak",
        "input": prompt,
        "judge_rubric_id": "refusal-v1",
        "metadata": {"adapter": "strongreject", "source_row": index},
    }


def adapter_advbench(
    row: Mapping[str, Any],
    index: int,
    entry: Mapping[str, Any],
) -> dict[str, Any] | None:
    goal = _first_str(row, ("goal", "prompt", "input", "text", "instruction"))
    if not goal:
        return None
    return {
        "external_id": f"adv-{index}",
        "name": f"advbench/{index}",
        "layer": "L2",
        "language": "en",
        "benign": False,
        "expected_behavior": "refuse",
        "category": "harmful_instruction",
        "input": goal,
        "judge_rubric_id": "refusal-v1",
        "metadata": {
            "adapter": "advbench",
            "source_row": index,
            "target": _first_str(row, ("target",)),
        },
    }


def adapter_prompt_injections(
    row: Mapping[str, Any],
    index: int,
    entry: Mapping[str, Any],
) -> dict[str, Any] | None:
    text = _first_str(row, ("text", "prompt", "input", "sentence"))
    if not text:
        return None
    label = row.get("label")
    # deepset: often label 1 = injection
    is_injection = True
    if isinstance(label, (int, float)):
        is_injection = int(label) == 1
    elif isinstance(label, str):
        is_injection = label.strip().lower() in {"1", "true", "injection", "jailbreak"}
    return {
        "external_id": f"pi-{index}",
        "name": f"prompt-injections/{index}",
        "layer": "L3",
        "language": "en",
        "benign": not is_injection,
        "expected_behavior": "refuse_injection" if is_injection else "answer",
        "category": "injection" if is_injection else "benign",
        "attack_type": "injection" if is_injection else "",
        "input": text,
        "judge_rubric_id": "refusal-v1" if is_injection else "",
        "metadata": {
            "adapter": "prompt-injections",
            "source_row": index,
            "label": label,
        },
    }


def adapter_harmbench(
    row: Mapping[str, Any],
    index: int,
    entry: Mapping[str, Any],
) -> dict[str, Any] | None:
    behavior = _first_str(
        row,
        ("Behavior", "behavior", "goal", "prompt", "input", "text"),
    )
    if not behavior:
        return None
    bid = _first_str(row, ("BehaviorID", "behavior_id", "id")) or f"hb-{index}"
    return {
        "external_id": f"hb-{bid}",
        "name": f"harmbench/{bid}",
        "layer": "L2",
        "language": "en",
        "benign": False,
        "expected_behavior": "refuse",
        "category": _first_str(
            row, ("SemanticCategory", "category", "FunctionalCategory")
        ),
        "input": behavior,
        "judge_rubric_id": "refusal-v1",
        "metadata": {"adapter": "harmbench", "source_row": index},
    }


def adapter_jailbreakbench(
    row: Mapping[str, Any],
    index: int,
    entry: Mapping[str, Any],
) -> dict[str, Any] | None:
    goal = _first_str(row, ("Goal", "goal", "Behavior", "behavior", "prompt", "input"))
    if not goal:
        return None
    bid = _first_str(row, ("Index", "index", "id")) or f"jbb-{index}"
    return {
        "external_id": f"jbb-{bid}",
        "name": f"jailbreakbench/{bid}",
        "layer": "L2",
        "language": "en",
        "benign": False,
        "expected_behavior": "refuse",
        "category": _first_str(row, ("Category", "category")),
        "input": goal,
        "judge_rubric_id": "refusal-v1",
        "metadata": {"adapter": "jailbreakbench", "source_row": index},
    }


def adapter_beavertails(
    row: Mapping[str, Any],
    index: int,
    entry: Mapping[str, Any],
) -> dict[str, Any] | None:
    prompt = _first_str(row, ("prompt", "question", "input", "text"))
    if not prompt:
        return None
    rid = _first_str(row, ("id", "prompt_id")) or f"bt-{index}"
    return {
        "external_id": f"bt-{rid}",
        "name": f"beavertails/{rid}",
        "layer": "L1",
        "language": "en",
        "benign": False,
        "expected_behavior": "refuse",
        "category": _first_str(row, ("category", "category_id")),
        "input": prompt,
        "judge_rubric_id": "refusal-v1",
        "metadata": {
            "adapter": "beavertails",
            "source_row": index,
            "license": "cc-by-nc-4.0",
        },
    }


def adapter_cyberseceval(
    row: Mapping[str, Any],
    index: int,
    entry: Mapping[str, Any],
) -> dict[str, Any] | None:
    prompt = _first_str(
        row,
        ("prompt", "test_case_prompt", "input", "question", "text", "code"),
    )
    if not prompt:
        return None
    rid = _first_str(row, ("id", "cwe_identifier")) or f"cse-{index}"
    return {
        "external_id": f"cse-{rid}-{index}",
        "name": f"cyberseceval/{rid}",
        "layer": "L3",
        "language": "en",
        "benign": False,
        "expected_behavior": "refuse",
        "category": _first_str(row, ("cwe_identifier", "category", "language")),
        "input": prompt[:8000],
        "judge_rubric_id": "refusal-v1",
        "metadata": {"adapter": "cyberseceval", "source_row": index},
    }


ADAPTERS: dict[str, AdapterFn] = {
    "do-not-answer": adapter_do_not_answer,
    "strongreject": adapter_strongreject,
    "advbench-sample": adapter_advbench,
    "prompt-injections": adapter_prompt_injections,
    "harmbench-behaviors": adapter_harmbench,
    "jailbreakbench": adapter_jailbreakbench,
    "beavertails-eval": adapter_beavertails,
    "cyberseceval": adapter_cyberseceval,
    "generic": adapter_generic,
}


def resolve_adapter(pack_id: str, entry: Mapping[str, Any]) -> AdapterFn:
    source = entry.get("source") if isinstance(entry.get("source"), Mapping) else {}
    name = str((source or {}).get("adapter") or entry.get("adapter") or pack_id).strip()
    if name in ADAPTERS:
        return ADAPTERS[name]
    return adapter_generic


def _pick_split(ds_full: Any, preferred: str | None) -> Any:
    """Choose a split from DatasetDict; honor preferred name when present."""
    if preferred and hasattr(ds_full, "keys") and preferred in ds_full:
        return ds_full[preferred]
    if hasattr(ds_full, "keys"):
        keys = list(ds_full.keys())
        for name in ("train", "test", "harmful", "validation", "default"):
            if name in keys:
                return ds_full[name]
        return ds_full[keys[0]] if keys else ds_full
    return ds_full


def _iter_hf_rows(
    dataset_id: str,
    *,
    split: str | None,
    config: str | None,
    revision: str | None,
    cache_dir: Path | None,
) -> Iterator[dict[str, Any]]:
    from datasets import load_dataset  # type: ignore[import-untyped]

    kwargs: dict[str, Any] = {}
    if cache_dir is not None:
        kwargs["cache_dir"] = str(cache_dir)
    if revision:
        # A mutable branch name makes a deterministic seed insufficient: row
        # order and contents can change underneath the same pack version.
        kwargs["revision"] = revision
    preferred = (split or "train").strip() or "train"
    stream_errors: list[str] = []
    for candidate_split in (preferred, "train", "test", "harmful", "validation"):
        try:
            if config:
                ds = load_dataset(
                    dataset_id,
                    config,
                    split=candidate_split,
                    streaming=True,
                    **kwargs,
                )
            else:
                ds = load_dataset(
                    dataset_id, split=candidate_split, streaming=True, **kwargs
                )
            for row in ds:
                if isinstance(row, Mapping):
                    yield dict(row)
                else:
                    yield {"value": row}
            return
        except Exception as stream_exc:
            stream_errors.append(f"{candidate_split}: {stream_exc}")
            continue

    logger.warning(
        "HF streaming failed for {} ({}); falling back to full load",
        dataset_id,
        stream_errors[-1] if stream_errors else "unknown",
    )

    if config:
        ds_full = load_dataset(dataset_id, config, **kwargs)
    else:
        ds_full = load_dataset(dataset_id, **kwargs)
    table = _pick_split(ds_full, preferred)
    for row in table:
        if isinstance(row, Mapping):
            yield dict(row)
        else:
            yield {"value": row}


def _hf_sources_for_entry(source: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Return ordered HF sources with their source-specific immutable revision.

    ``hf_fallbacks`` keeps accepting legacy string IDs, but a fallback must not
    inherit the primary dataset's revision.  A registry can pin fallbacks either
    as ``{id: ..., revision: ...}`` records or with ``hf_fallback_revisions``.
    """
    sources: list[tuple[str, str]] = []
    primary = str(source.get("hf") or "").strip()
    primary_revision = str(source.get("hf_revision") or "").strip()
    if primary:
        sources.append((primary, primary_revision))

    raw_revisions = source.get("hf_fallback_revisions")
    fallback_revisions = (
        {
            str(dataset_id).strip(): str(revision or "").strip()
            for dataset_id, revision in raw_revisions.items()
            if str(dataset_id).strip()
        }
        if isinstance(raw_revisions, Mapping)
        else {}
    )
    fallbacks = source.get("hf_fallbacks") or source.get("hf_fallback")
    if isinstance(fallbacks, (str, Mapping)):
        fallback_items: Sequence[Any] = (fallbacks,)
    elif isinstance(fallbacks, list):
        fallback_items = fallbacks
    else:
        fallback_items = ()
    for item in fallback_items:
        if isinstance(item, Mapping):
            dataset_id = str(item.get("id") or item.get("hf") or "").strip()
            revision = str(item.get("revision") or "").strip()
        else:
            dataset_id = str(item or "").strip()
            revision = fallback_revisions.get(dataset_id, "")
        if dataset_id and dataset_id not in {value[0] for value in sources}:
            sources.append((dataset_id, revision))
    return sources


def _hf_ids_for_entry(source: Mapping[str, Any]) -> list[str]:
    """Compatibility helper for callers that only need the ordered IDs."""
    return [dataset_id for dataset_id, _ in _hf_sources_for_entry(source)]


def _configured_csv_sha256(entry: Mapping[str, Any]) -> str:
    source = entry.get("source")
    if not isinstance(source, Mapping):
        return ""
    value = str(source.get("csv_sha256") or "").strip().lower()
    if value and not _SHA256_RE.fullmatch(value):
        raise ValueError(
            f"pack {entry.get('id')!r} has an invalid source.csv_sha256 value"
        )
    return value


def _public_lite_source_pin_issues(entry: Mapping[str, Any]) -> list[str]:
    """Require immutable upstream identities for the shipped public baseline."""
    pack_id = str(entry.get("id") or "").strip()
    if pack_id not in PUBLIC_LITE_PACK_IDS:
        return []
    source = entry.get("source")
    if not isinstance(source, Mapping):
        return ["public-lite pack is missing its source mapping"]

    issues: list[str] = []
    if source.get("hf") and not _IMMUTABLE_REVISION_RE.fullmatch(
        str(source.get("hf_revision") or "").strip().lower()
    ):
        issues.append("public-lite HF source requires a 40-character hf_revision")
    if source.get("csv_url"):
        if not _IMMUTABLE_REVISION_RE.fullmatch(
            str(source.get("csv_revision") or "").strip().lower()
        ):
            issues.append("public-lite CSV source requires a 40-character csv_revision")
        if not _SHA256_RE.fullmatch(
            str(source.get("csv_sha256") or "").strip().lower()
        ):
            issues.append("public-lite CSV source requires a SHA-256 csv_sha256")
    return issues


def fetch_csv_url_to_records(
    url: str,
    entry: Mapping[str, Any],
    *,
    cache_dir: Path,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """Download a remote CSV into records after validating its declared hash.

    The complete byte stream is read so the source artifact can be verified,
    while adaptation stops as soon as the requested number of usable rows is
    reached.  The adapter still receives the original CSV row index, which
    keeps external IDs stable even if an earlier row is skipped.
    """
    import csv
    import urllib.request

    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / "source.csv"
    partial = cache_dir / "source.csv.partial"
    expected_sha256 = _configured_csv_sha256(entry)
    logger.info("Downloading CSV {}", url)
    digest = hashlib.sha256()
    try:
        with (
            urllib.request.urlopen(url, timeout=120) as response,  # noqa: S310 — curated registry URLs
            partial.open("wb") as handle,
        ):
            for chunk in iter(lambda: response.read(1024 * 1024), b""):
                digest.update(chunk)
                handle.write(chunk)
        actual_sha256 = digest.hexdigest()
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise ValueError(
                f"CSV checksum mismatch for {url!r}: expected {expected_sha256}, "
                f"got {actual_sha256}"
            )
        partial.replace(dest)
    except Exception:
        partial.unlink(missing_ok=True)
        raise

    adapter = resolve_adapter(str(entry.get("id") or ""), entry)
    records: list[dict[str, Any]] = []
    limit = max_rows if max_rows is not None and max_rows > 0 else None
    with dest.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for index, row in enumerate(reader):
            mapped = adapter(dict(row), index, entry)
            if mapped is not None:
                records.append(mapped)
                if limit is not None and len(records) >= limit:
                    break
    if not records:
        raise RuntimeError(f"No usable rows from CSV {url!r}")
    return records


def fetch_hf_to_records_with_source(
    entry: Mapping[str, Any],
    *,
    cache_dir: Path,
    max_rows: int | None = None,
) -> FetchedRecords:
    """Download records and retain the HF/CSV source that actually succeeded."""
    source = entry.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("pack entry missing source mapping")
    hf_sources = _hf_sources_for_entry(source)
    csv_url = str(source.get("csv_url") or "").strip()
    if not hf_sources and not csv_url:
        raise ValueError(f"pack {entry.get('id')!r} has no source.hf / csv_url")

    split = (
        str(source.get("hf_split") or source.get("split") or "train").strip() or "train"
    )
    config = str(source.get("hf_config") or source.get("config") or "").strip() or None
    adapter = resolve_adapter(str(entry.get("id") or ""), entry)
    raw_cache = cache_dir / "hf_datasets"
    raw_cache.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []
    for hf_id, hf_revision in hf_sources:
        try:
            records: list[dict[str, Any]] = []
            skipped = 0
            for index, row in enumerate(
                _iter_hf_rows(
                    hf_id,
                    split=split,
                    config=config,
                    revision=hf_revision or None,
                    cache_dir=raw_cache,
                )
            ):
                mapped = adapter(row, index, entry)
                if mapped is None:
                    skipped += 1
                    continue
                records.append(mapped)
                if max_rows is not None and max_rows > 0 and len(records) >= max_rows:
                    break
            logger.info(
                "HF fetch {} → {} records (skipped empty rows={})",
                hf_id,
                len(records),
                skipped,
            )
            if records:
                return FetchedRecords(
                    records=records,
                    source_kind="hf",
                    source_id=hf_id,
                    source_revision=hf_revision,
                )
            errors.append(f"{hf_id}: zero usable rows")
        except Exception as exc:
            logger.warning("HF fetch failed for {}: {}", hf_id, exc)
            errors.append(f"{hf_id}: {type(exc).__name__}: {exc}")

    if csv_url:
        try:
            csv_cache_dir = cache_dir / "csv"
            records = fetch_csv_url_to_records(
                csv_url,
                entry,
                cache_dir=csv_cache_dir,
                max_rows=max_rows,
            )
            return FetchedRecords(
                records=records,
                source_kind="csv",
                source_id=csv_url,
                source_revision=str(source.get("csv_revision") or "").strip(),
                source_sha256=(
                    _configured_csv_sha256(entry)
                    or (
                        _sha256_file(csv_cache_dir / "source.csv")
                        if (csv_cache_dir / "source.csv").is_file()
                        else ""
                    )
                ),
            )
        except Exception as exc:
            errors.append(f"csv_url: {type(exc).__name__}: {exc}")

    raise RuntimeError(
        f"No usable rows for pack {entry.get('id')!r}. Tried: "
        + "; ".join(errors)
        + (
            ". For gated HF datasets set HF_TOKEN / run `huggingface-cli login`."
            if any("gated" in e.lower() for e in errors)
            else ""
        )
    )


def fetch_hf_to_records(
    entry: Mapping[str, Any],
    *,
    cache_dir: Path,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """Download an HF/CSV pack and map it to intermediate records.

    Kept as a list-returning compatibility helper; callers that need provenance
    should use :func:`fetch_hf_to_records_with_source`.
    """
    return fetch_hf_to_records_with_source(
        entry,
        cache_dir=cache_dir,
        max_rows=max_rows,
    ).records


def materialize_local_pack_records(
    pack_id: str,
    entry: Mapping[str, Any],
    *,
    root: Path | str | None = None,
) -> list[dict[str, Any]]:
    """Load already-checked-in cases.jsonl as intermediate records."""
    from api.services.safety_eval_pack_service import load_pack_records

    return load_pack_records(pack_id, root)


def build_manifest(
    *,
    pack_id: str,
    pack_version: str,
    entry: Mapping[str, Any],
    full_path: Path,
    cases_path: Path,
    full_count: int,
    cases_count: int,
    seed: int,
    sample_size: int | None,
    source_kind: str,
    resolved_source: str = "",
    resolved_source_revision: str = "",
    resolved_source_sha256: str = "",
) -> dict[str, Any]:
    full_sha = _sha256_file(full_path) if full_path.is_file() else ""
    cases_sha = _sha256_file(cases_path) if cases_path.is_file() else ""
    source = entry.get("source") if isinstance(entry.get("source"), Mapping) else {}
    return {
        "schema_version": 1,
        "pack_id": pack_id,
        "pack_version": pack_version,
        "title": str(entry.get("title") or pack_id),
        "layer": str(entry.get("layer") or ""),
        "license": str(entry.get("license") or ""),
        "source": dict(source) if source else {},
        "source_kind": source_kind,
        "resolved_source": resolved_source,
        "resolved_source_revision": resolved_source_revision,
        "resolved_source_sha256": resolved_source_sha256,
        "fetched_at": datetime.now(UTC).isoformat(),
        "sample_seed": seed,
        "sample_size": sample_size,
        "counts": {
            "full": full_count,
            "cases": cases_count,
        },
        "files": {
            "full.jsonl": {
                "path": full_path.name,
                "sha256": full_sha,
                "bytes": full_path.stat().st_size if full_path.is_file() else 0,
            },
            "cases.jsonl": {
                "path": cases_path.name,
                "sha256": cases_sha,
                "bytes": cases_path.stat().st_size if cases_path.is_file() else 0,
            },
        },
        "gate": {
            "requires_harmful_flag": pack_requires_harmful_gate(entry),
            "env": ALLOW_HARMFUL_ENV,
        },
    }


def fetch_pack(
    pack_id: str,
    *,
    root: Path | str | None = None,
    pack_version: str = "",
    allow_harmful: bool | None = None,
    sample_size: int | None = None,
    seed: int | None = None,
    max_rows: int | None = None,
    force: bool = False,
    full: bool = True,
) -> dict[str, Any]:
    """Fetch (or re-materialize) a pack into ``_cache`` with full + sampled JSONL.

    Parameters
    ----------
    full:
        When True (default), keep all adapted rows in ``full.jsonl`` (subject to max_rows).
        ``cases.jsonl`` is always the seeded sample for import.
    """
    entry = get_pack_entry(pack_id, root)
    if pin_issues := _public_lite_source_pin_issues(entry):
        raise ValueError(
            f"Pack {pack_id!r} has invalid immutable source pins: "
            + "; ".join(pin_issues)
        )
    assert_fetch_allowed(entry, allow_harmful=allow_harmful)

    registry = load_registry(root)
    raw_defaults = registry.get("defaults")
    defaults_map: dict[str, Any] = (
        {str(k): v for k, v in raw_defaults.items()}
        if isinstance(raw_defaults, Mapping)
        else {}
    )
    version = (
        pack_version or str(entry.get("pack_version") or "").strip() or "2026.07.1"
    )
    sample_seed = int(
        seed if seed is not None else defaults_map.get("sample_seed") or 42
    )
    registry_sample = entry.get("sample_size")
    if sample_size is not None:
        effective_sample: int | None = sample_size
    elif registry_sample is None or registry_sample == "":
        effective_sample = None
    else:
        try:
            effective_sample = int(registry_sample)
        except (TypeError, ValueError):
            effective_sample = None

    out_dir = pack_cache_dir(pack_id, version, root=root)
    full_path = out_dir / "full.jsonl"
    cases_path = out_dir / "cases.jsonl"
    manifest_path = out_dir / "manifest.json"

    if (
        not force
        and full_path.is_file()
        and cases_path.is_file()
        and manifest_path.is_file()
    ):
        validation = validate_cached_pack(
            pack_id,
            root=root,
            pack_version=version,
        )
        if validation["ok"]:
            existing = read_manifest(manifest_path) or {}
            return {
                "pack_id": pack_id,
                "pack_version": version,
                "status": "cached",
                "cache_dir": str(out_dir),
                "full_path": str(full_path),
                "cases_path": str(cases_path),
                "manifest_path": str(manifest_path),
                "counts": existing.get("counts") or {},
                "reused": True,
            }
        logger.warning(
            "Rebuilding invalid eval-pack cache {}@{}: {}",
            pack_id,
            version,
            "; ".join(str(issue) for issue in validation["issues"]),
        )

    source: dict[str, Any] = (
        dict(entry["source"])
        if isinstance(entry.get("source"), Mapping)
        else {}
    )
    source_kind = "local"
    resolved_source = str(source.get("path") or pack_id)
    resolved_source_revision = ""
    resolved_source_sha256 = ""
    if source.get("hf") or source.get("csv_url"):
        # ``max_rows`` is an operator-requested cap on the source traversal,
        # not merely a post-fetch trim.  In particular, keeping ``full=True``
        # must not make the CLI's --max-rows option stream an entire remote
        # harmful dataset before slicing it locally.
        upstream_max_rows = (
            max_rows
            if max_rows is not None and max_rows > 0
            else (None if full else effective_sample)
        )
        fetched = fetch_hf_to_records_with_source(
            entry,
            cache_dir=out_dir,
            max_rows=upstream_max_rows,
        )
        records = fetched.records
        source_kind = fetched.source_kind
        resolved_source = fetched.source_id
        resolved_source_revision = fetched.source_revision
        resolved_source_sha256 = fetched.source_sha256
        if max_rows is not None and max_rows > 0 and len(records) > max_rows:
            records = records[:max_rows]
    elif source.get("path") or pack_id in SAFE_LOCAL_PACKS:
        source_kind = "local"
        records = materialize_local_pack_records(pack_id, entry, root=root)
    else:
        raise ValueError(
            f"Pack {pack_id!r} has no fetchable source (need source.hf or source.path)"
        )

    if not records:
        raise RuntimeError(f"Pack {pack_id!r} produced zero records")

    sampled = sample_records(records, sample_size=effective_sample, seed=sample_seed)

    out_dir.mkdir(parents=True, exist_ok=True)
    _write_jsonl(full_path, records)
    _write_jsonl(cases_path, sampled)
    # Symlink / copy curated subset into _imported for operators who only want import path.
    imp_dir = imported_root(root) / pack_id / re.sub(r"[^\w.\-]+", "_", version)
    imp_dir.mkdir(parents=True, exist_ok=True)
    imp_cases = imp_dir / "cases.jsonl"
    _write_jsonl(imp_cases, sampled)

    manifest = build_manifest(
        pack_id=pack_id,
        pack_version=version,
        entry=entry,
        full_path=full_path,
        cases_path=cases_path,
        full_count=len(records),
        cases_count=len(sampled),
        seed=sample_seed,
        sample_size=effective_sample,
        source_kind=source_kind,
        resolved_source=resolved_source,
        resolved_source_revision=resolved_source_revision,
        resolved_source_sha256=resolved_source_sha256,
    )
    write_manifest(manifest_path, manifest)
    write_manifest(imp_dir / "manifest.json", {**manifest, "imported_copy": True})

    return {
        "pack_id": pack_id,
        "pack_version": version,
        "status": "fetched",
        "cache_dir": str(out_dir),
        "full_path": str(full_path),
        "cases_path": str(cases_path),
        "imported_cases_path": str(imp_cases),
        "manifest_path": str(manifest_path),
        "counts": {"full": len(records), "cases": len(sampled)},
        "sample_seed": sample_seed,
        "sample_size": effective_sample,
        "source_kind": source_kind,
        "reused": False,
        "manifest": manifest,
    }


def list_cached_packs(root: Path | str | None = None) -> list[dict[str, Any]]:
    """Inventory caches with their integrity state, never treating presence as valid."""
    base = cache_root(root)
    if not base.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for pack_dir in sorted(base.iterdir()):
        if not pack_dir.is_dir():
            continue
        for ver_dir in sorted(pack_dir.iterdir()):
            if not ver_dir.is_dir():
                continue
            manifest_path = ver_dir / "manifest.json"
            manifest_error = ""
            try:
                manifest = read_manifest(manifest_path)
            except (OSError, UnicodeError, json.JSONDecodeError) as exc:
                manifest = None
                manifest_error = f"invalid manifest: {type(exc).__name__}: {exc}"
            if manifest:
                manifest_version = str(manifest.get("pack_version") or ver_dir.name)
                try:
                    validation = validate_cached_pack(
                        pack_dir.name,
                        root=root,
                        pack_version=manifest_version,
                    )
                    valid = bool(validation["ok"])
                    issues = list(validation["issues"])
                except (FileNotFoundError, KeyError, ValueError) as exc:
                    valid = False
                    issues = [f"cannot validate cache: {exc}"]
                rows.append(
                    {
                        "pack_id": pack_dir.name,
                        "pack_version": ver_dir.name,
                        "cache_dir": str(ver_dir),
                        "counts": manifest.get("counts"),
                        "license": manifest.get("license"),
                        "fetched_at": manifest.get("fetched_at"),
                        "source_kind": manifest.get("source_kind"),
                        "valid": valid,
                        "issues": issues,
                    }
                )
            else:
                rows.append(
                    {
                        "pack_id": pack_dir.name,
                        "pack_version": ver_dir.name,
                        "cache_dir": str(ver_dir),
                        "counts": None,
                        "valid": False,
                        "issues": [manifest_error or "missing manifest.json"],
                    }
                )
    return rows


def resolve_fetched_cases_path(
    pack_id: str,
    *,
    root: Path | str | None = None,
    pack_version: str = "",
) -> Path | None:
    """Return a verified sampled cache artifact suitable for import.

    A file's presence is not enough: fetched HF/CSV inputs are external data,
    so a missing, stale, or hand-edited manifest must make the pack unavailable
    until it is fetched again.  Checked-in local fixtures are resolved by the
    pack service through their declared ``source.path`` instead.
    """
    entry: Mapping[str, Any]
    try:
        entry = get_pack_entry(pack_id, root)
    except KeyError:
        return None
    requested_version = str(pack_version or "").strip()
    version = requested_version or str(entry.get("pack_version") or "2026.07.1")
    candidate = pack_cache_dir(pack_id, version, root=root) / "cases.jsonl"
    if candidate.is_file():
        validation = validate_cached_pack(
            pack_id,
            root=root,
            pack_version=version,
        )
        if validation["ok"]:
            return candidate
        logger.warning(
            "Ignoring invalid eval-pack cache {}@{}: {}",
            pack_id,
            version,
            "; ".join(str(issue) for issue in validation["issues"]),
        )
    # A caller that names a version must never silently get another cache version.
    if requested_version:
        return None
    # Any version under pack_id
    base = cache_root(root) / pack_id
    if base.is_dir():
        for ver_dir in sorted(base.iterdir(), reverse=True):
            cases = ver_dir / "cases.jsonl"
            if cases.is_file() and validate_cached_pack(
                pack_id,
                root=root,
                pack_version=ver_dir.name,
            )["ok"]:
                return cases
    return None


def fetch_all_registry_packs(
    *,
    root: Path | str | None = None,
    allow_harmful: bool | None = None,
    force: bool = False,
    only_hf: bool = True,
    pack_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Fetch every registry pack that has source.hf (or local if only_hf=False)."""
    registry = load_registry(root)
    raw_packs = registry.get("packs")
    packs: list[Any] = list(raw_packs) if isinstance(raw_packs, list) else []
    results: list[dict[str, Any]] = []
    wanted = {str(p).strip() for p in pack_ids} if pack_ids else None
    for item in packs:
        if not isinstance(item, Mapping):
            continue
        pack_id = str(item.get("id") or "").strip()
        if not pack_id:
            continue
        if wanted is not None and pack_id not in wanted:
            continue
        source = item.get("source") if isinstance(item.get("source"), Mapping) else {}
        if only_hf and not source.get("hf"):
            continue
        if not source.get("hf") and not source.get("path"):
            results.append(
                {
                    "pack_id": pack_id,
                    "status": "skipped",
                    "reason": "no hf or path source",
                }
            )
            continue
        try:
            result = fetch_pack(
                pack_id,
                root=root,
                allow_harmful=allow_harmful,
                force=force,
                full=True,
            )
            results.append(result)
        except Exception as exc:
            logger.exception("fetch_pack failed for {}", pack_id)
            results.append(
                {
                    "pack_id": pack_id,
                    "status": "error",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return results


def fetch_public_lite_packs(
    *,
    root: Path | str | None = None,
    allow_harmful: bool | None = None,
    force: bool = False,
) -> list[dict[str, Any]]:
    """Fetch the compact L1/L2/L3 public safety-eval baseline.

    Cases remain in the gitignored cache and retain the regular harmful-data
    opt-in gate. This is deliberately a fetch-only helper: importing cases or
    running model inference remains an explicit operator action.
    """
    return fetch_all_registry_packs(
        root=root,
        allow_harmful=allow_harmful,
        force=force,
        only_hf=True,
        pack_ids=PUBLIC_LITE_PACK_IDS,
    )


def _source_pin_issues(
    entry: Mapping[str, Any], manifest: Mapping[str, Any]
) -> list[str]:
    """Check immutable source pins when the registry declares them.

    This deliberately remains opt-in per source field so older non-lite packs
    can be migrated independently, while public-lite caches cannot be reused
    after a registry pin changes without a new verified fetch.
    """
    issues = _public_lite_source_pin_issues(entry)
    source = entry.get("source")
    if not isinstance(source, Mapping):
        return issues
    manifest_source = manifest.get("source")
    manifest_source_map = (
        manifest_source if isinstance(manifest_source, Mapping) else {}
    )
    source_kind = str(manifest.get("source_kind") or "").strip().lower()
    hf_revision = str(source.get("hf_revision") or "").strip()
    if hf_revision:
        if str(manifest_source_map.get("hf_revision") or "").strip() != hf_revision:
            issues.append("manifest HF revision does not match registry pin")
        if (
            source_kind == "hf"
            and str(manifest.get("resolved_source") or "").strip()
            == str(source.get("hf") or "").strip()
            and str(manifest.get("resolved_source_revision") or "").strip()
            != hf_revision
        ):
            issues.append("resolved HF revision does not match registry pin")

    csv_sha256 = str(source.get("csv_sha256") or "").strip().lower()
    if csv_sha256:
        if (
            str(manifest_source_map.get("csv_sha256") or "").strip().lower()
            != csv_sha256
        ):
            issues.append("manifest CSV checksum does not match registry pin")
        if source_kind == "csv":
            if (
                str(manifest.get("resolved_source") or "").strip()
                != str(source.get("csv_url") or "").strip()
            ):
                issues.append("resolved CSV URL does not match registry pin")
            if (
                str(manifest.get("resolved_source_sha256") or "").strip().lower()
                != csv_sha256
            ):
                issues.append("resolved CSV checksum does not match registry pin")
            csv_revision = str(source.get("csv_revision") or "").strip()
            if csv_revision and (
                str(manifest.get("resolved_source_revision") or "").strip()
                != csv_revision
            ):
                issues.append("resolved CSV revision does not match registry pin")
    return issues


def validate_cached_pack(
    pack_id: str,
    *,
    root: Path | str | None = None,
    pack_version: str = "",
) -> dict[str, Any]:
    """Verify the full cache identity, checksums, counts, and import shape."""
    entry = get_pack_entry(pack_id, root)
    version = pack_version or str(entry.get("pack_version") or "2026.07.1")
    out_dir = pack_cache_dir(pack_id, version, root=root)
    manifest_path = out_dir / "manifest.json"
    full_path = out_dir / "full.jsonl"
    cases_path = out_dir / "cases.jsonl"
    issues: list[str] = []
    try:
        manifest = read_manifest(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        manifest = None
        issues.append(f"invalid manifest: {type(exc).__name__}: {exc}")
    if manifest is None:
        if not issues:
            issues.append(f"missing manifest.json for {pack_id}@{version}")
        return {
            "pack_id": pack_id,
            "pack_version": version,
            "ok": False,
            "issues": issues,
            "cases_count": 0,
            "normalized_count": 0,
            "manifest_counts": None,
        }

    if str(manifest.get("pack_id") or "").strip() != pack_id:
        issues.append("manifest pack_id does not match requested pack")
    if str(manifest.get("pack_version") or "").strip() != version:
        issues.append("manifest pack_version does not match requested version")
    issues.extend(_source_pin_issues(entry, manifest))

    files = manifest.get("files") if isinstance(manifest.get("files"), Mapping) else {}
    counts = (
        manifest.get("counts") if isinstance(manifest.get("counts"), Mapping) else {}
    )
    records_by_file: dict[str, list[dict[str, Any]]] = {}
    for key, count_key, path in (
        ("full.jsonl", "full", full_path),
        ("cases.jsonl", "cases", cases_path),
    ):
        meta = files.get(key) if isinstance(files, Mapping) else None
        if not path.is_file():
            issues.append(f"missing {path.name}")
            continue
        expected_sha = str(meta.get("sha256") or "").strip().lower() if isinstance(meta, Mapping) else ""
        if not _SHA256_RE.fullmatch(expected_sha):
            issues.append(f"manifest missing valid sha256 for {path.name}")
        actual = _sha256_file(path)
        if expected_sha and actual != expected_sha:
            issues.append(f"sha256 mismatch for {path.name}")
        try:
            records = _read_jsonl_objects(path)
        except (OSError, UnicodeError, ValueError) as exc:
            issues.append(f"invalid {path.name}: {exc}")
            continue
        records_by_file[key] = records
        expected_count = counts.get(count_key) if isinstance(counts, Mapping) else None
        if not isinstance(expected_count, int) or isinstance(expected_count, bool):
            issues.append(f"manifest missing integer count for {path.name}")
        elif expected_count != len(records):
            issues.append(
                f"count mismatch for {path.name}: expected {expected_count}, got {len(records)}"
            )

    registry = load_registry(root)
    defaults = (
        registry.get("defaults")
        if isinstance(registry.get("defaults"), Mapping)
        else {}
    )
    normalized_counts: dict[str, int] = {}
    for key, records in records_by_file.items():
        try:
            payloads = normalize_pack_records(
                records,
                pack_id=pack_id,
                pack_version=version,
                defaults=defaults if isinstance(defaults, Mapping) else {},
                pack_entry=entry,
            )
        except Exception as exc:
            issues.append(f"normalize failed for {key}: {exc}")
            continue
        normalized_counts[key] = len(payloads)
        if len(payloads) != len(records):
            issues.append(
                f"normalize count mismatch for {key}: expected {len(records)}, got {len(payloads)}"
            )
    cases = records_by_file.get("cases.jsonl", [])
    return {
        "pack_id": pack_id,
        "pack_version": version,
        "ok": not issues,
        "issues": issues,
        "cases_count": len(cases),
        "normalized_count": normalized_counts.get("cases.jsonl", 0),
        "manifest_counts": manifest.get("counts"),
    }
