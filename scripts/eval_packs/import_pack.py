#!/usr/bin/env python3
"""Import a local safety eval pack into agent_eval suites/cases (idempotent).

Examples:

  uv run python scripts/eval_packs/import_pack.py --pack fixture-synthetic
  uv run python scripts/eval_packs/import_pack.py --pack soc-custom-v1

Requires a running control-plane DB (same env as the API). Uses a synthetic
actor id for created_by when --actor is omitted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

# Allow `uv run python scripts/eval_packs/import_pack.py` from repo root.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.services.safety_eval_pack_service import import_pack, load_registry  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Import safety eval pack into DB")
    parser.add_argument(
        "--pack",
        default=None,
        help="pack id from eval_packs/registry.yaml (required unless --list)",
    )
    parser.add_argument(
        "--root", default=None, help="override eval_packs root directory"
    )
    parser.add_argument("--cases", default=None, help="optional path to cases.jsonl")
    parser.add_argument("--pack-version", default="", help="override pack_version")
    parser.add_argument(
        "--actor", default="safety-eval-import", help="created_by actor id"
    )
    parser.add_argument(
        "--list", action="store_true", help="list registry packs and exit"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list:
        registry = load_registry(args.root)
        packs = registry.get("packs") or []
        for item in packs:
            if isinstance(item, dict):
                print(
                    f"{item.get('id')}\t{item.get('status')}\t{item.get('suite_name')}"
                )
        return 0

    if not args.pack:
        parser.error("--pack is required unless --list is set")

    actor = SimpleNamespace(id=args.actor, email=f"{args.actor}@local", role="admin")

    async def _run() -> dict:
        return await import_pack(
            args.pack,
            actor,
            root=args.root,
            cases_path=args.cases,
            pack_version=args.pack_version,
        )

    result = asyncio.run(_run())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
