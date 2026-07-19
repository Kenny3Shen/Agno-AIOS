"""Standalone PostgreSQL durable-job worker.

Run it independently from the API process, for example:

    uv run python -m api.tasks.job_worker --concurrency 4

The worker only dispatches code registered in a trusted Python handler factory;
database payloads never control imports or commands.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import signal
from typing import Any

from loguru import logger

from api.persistence.migrations import ensure_control_plane_schema_current
from api.services.durable_job_service import (
    DurableJobRegistry,
    DurableJobWorker,
    DurableJobWorkerOptions,
)

DEFAULT_HANDLER_FACTORY = (
    "api.services.durable_job_handlers:build_durable_job_registry"
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the standalone PostgreSQL durable-job worker."
    )
    parser.add_argument(
        "--worker-id",
        default=None,
        help="Stable lease-owner id (defaults to hostname plus a UUID).",
    )
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--lease-seconds", type=float, default=60.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    parser.add_argument("--retry-base-seconds", type=float, default=5.0)
    parser.add_argument("--retry-max-seconds", type=float, default=300.0)
    parser.add_argument(
        "--handler-factory",
        default=DEFAULT_HANDLER_FACTORY,
        help=(
            "Trusted Python factory in module:attribute form. It must return "
            "a DurableJobRegistry."
        ),
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Claim and finish at most one concurrency-sized batch, then exit.",
    )
    return parser


def load_handler_registry(factory_path: str) -> DurableJobRegistry:
    """Load the operator-selected, trusted handler factory."""
    module_name, separator, attribute = factory_path.partition(":")
    if not separator or not module_name or not attribute:
        raise ValueError("handler factory must use module:attribute form")
    module = importlib.import_module(module_name)
    factory: Any = getattr(module, attribute, None)
    if not callable(factory):
        raise ValueError(f"handler factory {factory_path!r} is not callable")
    registry = factory()
    if not isinstance(registry, DurableJobRegistry):
        raise ValueError(
            f"handler factory {factory_path!r} must return DurableJobRegistry"
        )
    return registry


def _install_stop_signals(stop_event: asyncio.Event) -> None:
    """Request graceful lease release for SIGINT/SIGTERM where supported."""
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except (NotImplementedError, RuntimeError):
            # The CLI also runs under environments whose event loops do not
            # expose signal handlers.  ``asyncio.run`` still handles Ctrl-C.
            logger.debug("Signal handlers are unavailable for {}", sig.name)


def _worker_options(args: argparse.Namespace) -> DurableJobWorkerOptions:
    return DurableJobWorkerOptions(
        concurrency=args.concurrency,
        lease_seconds=args.lease_seconds,
        poll_interval_seconds=args.poll_interval_seconds,
        retry_base_seconds=args.retry_base_seconds,
        retry_max_seconds=args.retry_max_seconds,
    )


async def main(args: argparse.Namespace) -> int:
    # Workers mutate the same repository-owned tables as the API.  Refuse to
    # claim work until the release migration has completed, rather than making
    # a partially migrated deployment fail later inside a handler.
    await ensure_control_plane_schema_current()
    registry = load_handler_registry(args.handler_factory)
    worker = DurableJobWorker(
        registry=registry,
        worker_id=args.worker_id,
        options=_worker_options(args),
    )
    if args.once:
        claimed = await worker.run_once()
        logger.info("Durable job worker once-mode processed {} job(s)", claimed)
        return claimed
    stop_event = asyncio.Event()
    _install_stop_signals(stop_event)
    await worker.run_forever(stop_event)
    return 0


def run() -> None:
    args = _parser().parse_args()
    asyncio.run(main(args))


if __name__ == "__main__":
    run()
