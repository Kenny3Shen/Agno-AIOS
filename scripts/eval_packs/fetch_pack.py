#!/usr/bin/env python3
"""Fetch safety eval packs into eval_packs/_cache (full + sampled JSONL + manifest).

Examples:

  # Inventory registry
  uv run python scripts/eval_packs/fetch_pack.py --list

  # Full pull of one HF pack (opt-in)
  TAIS_EVAL_PACKS_ALLOW_HARMFUL=1 uv run python scripts/eval_packs/fetch_pack.py \\
      --pack strongreject

  # Full pull of all HF packs in registry
  TAIS_EVAL_PACKS_ALLOW_HARMFUL=1 uv run python scripts/eval_packs/fetch_pack.py --all

  # Compact public L1/L2/L3 baseline (60 curated cases total)
  TAIS_EVAL_PACKS_ALLOW_HARMFUL=1 uv run python scripts/eval_packs/fetch_pack.py --public-lite

  # List cached packs + validate checksums
  uv run python scripts/eval_packs/fetch_pack.py --cached
  uv run python scripts/eval_packs/fetch_pack.py --validate --pack strongreject

Data stays under eval_packs/_cache (gitignored). Import uses cases.jsonl sample.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.services.safety_eval_fetch import (  # noqa: E402
    ALLOW_HARMFUL_ENV,
    fetch_all_registry_packs,
    fetch_pack,
    fetch_public_lite_packs,
    list_cached_packs,
    validate_cached_pack,
)
from api.services.safety_eval_pack_service import load_registry  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fetch / inventory safety eval packs")
    p.add_argument("--pack", default=None, help="pack id from registry.yaml")
    p.add_argument("--root", default=None, help="override eval_packs root")
    p.add_argument("--pack-version", default="", help="override pack_version")
    p.add_argument("--sample-size", type=int, default=None, help="override sample size")
    p.add_argument(
        "--seed", type=int, default=None, help="sample seed (default registry)"
    )
    p.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="cap full download rows (debug); default unlimited",
    )
    p.add_argument("--force", action="store_true", help="re-fetch even if cache exists")
    p.add_argument(
        "--allow-harmful",
        action="store_true",
        help=f"opt-in harmful/NC packs (or set {ALLOW_HARMFUL_ENV}=1)",
    )
    p.add_argument("--all", action="store_true", help="fetch all HF packs in registry")
    p.add_argument(
        "--public-lite",
        action="store_true",
        help="fetch the compact public L1/L2/L3 safety baseline",
    )
    p.add_argument("--list", action="store_true", help="list registry packs")
    p.add_argument("--cached", action="store_true", help="list packs under _cache")
    p.add_argument(
        "--validate",
        action="store_true",
        help="validate cached pack checksums + normalize",
    )
    p.add_argument(
        "--include-local",
        action="store_true",
        help="with --all, also materialize local path packs into cache",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    root = args.root

    if args.list:
        registry = load_registry(root)
        packs = registry.get("packs") or []
        for item in packs:
            if not isinstance(item, dict):
                continue
            source = item.get("source") if isinstance(item.get("source"), dict) else {}
            hf = source.get("hf") or ""
            path = source.get("path") or ""
            print(
                f"{item.get('id')}\t{item.get('status')}\t"
                f"sample={item.get('sample_size')}\t"
                f"hf={hf or '-'}\tpath={path or '-'}"
            )
        return 0

    if args.cached:
        rows = list_cached_packs(root)
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        return 0

    if args.validate:
        if not args.pack:
            parser.error("--validate requires --pack")
        result = validate_cached_pack(
            args.pack, root=root, pack_version=args.pack_version
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") else 2

    allow = True if args.allow_harmful else None

    if args.all and args.public_lite:
        parser.error("--all and --public-lite cannot be used together")
    if args.pack and (args.all or args.public_lite):
        parser.error("--pack cannot be combined with --all or --public-lite")

    if args.all:
        results = fetch_all_registry_packs(
            root=root,
            allow_harmful=allow,
            force=args.force,
            only_hf=not args.include_local,
        )
        print(json.dumps(results, ensure_ascii=False, indent=2))
        errors = [r for r in results if r.get("status") == "error"]
        return 1 if errors else 0

    if args.public_lite:
        results = fetch_public_lite_packs(
            root=root,
            allow_harmful=allow,
            force=args.force,
        )
        print(json.dumps(results, ensure_ascii=False, indent=2))
        errors = [r for r in results if r.get("status") == "error"]
        return 1 if errors else 0

    if not args.pack:
        parser.error("--pack is required unless --list/--cached/--all/--public-lite")

    result = fetch_pack(
        args.pack,
        root=root,
        pack_version=args.pack_version,
        allow_harmful=allow,
        sample_size=args.sample_size,
        seed=args.seed,
        max_rows=args.max_rows,
        force=args.force,
        full=True,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
