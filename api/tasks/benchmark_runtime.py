"""Opt-in staging benchmarks for real HTTP/SSE runtime traffic.

The benchmark deliberately does not know application passwords or model
credentials.  An operator supplies a short-lived bearer token and an explicit
staging URL, for example::

    uv run benchmark-runtime \
      --url https://staging.example.test \
      --token "$TAIS_BENCHMARK_TOKEN" \
      --model-id configured-model \
      --requests 12 --concurrency 3 --scenario both \
      --output .logs/benchmarks/runtime.json

It sends real ``/api/chat`` SSE requests (optionally multipart with a document)
and/or ``/api/overview`` reads, then emits JSON that is safe to attach to a
performance decision: tokens and response content are never persisted.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from collections import Counter
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import httpx

Scenario = Literal["chat", "overview"]
_TERMINAL_CHAT_EVENTS = frozenset(
    {"run.completed", "run.failed", "run.cancelled", "run.paused"}
)


@dataclass(frozen=True, slots=True)
class SseEvent:
    """One decoded server-sent event."""

    event: str
    data: str


@dataclass(frozen=True, slots=True)
class BenchmarkSample:
    """One real request measurement with no request/response payloads."""

    scenario: Scenario
    request_index: int
    status_code: int | None
    response_started_ms: float | None
    first_content_ms: float | None
    total_ms: float
    event_count: int
    terminal_event: str | None
    error: str | None


def _percentile(values: Iterable[float], percentile: float) -> float | None:
    """Return a linear-interpolated percentile, or ``None`` for no values."""
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * percentile
    lower = math.floor(rank)
    upper = math.ceil(rank)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (rank - lower)


def _metric_summary(samples: Iterable[BenchmarkSample]) -> dict[str, object]:
    """Produce stable p50/p95 summary data without retaining chat content."""
    rows = list(samples)
    total_ms = [sample.total_ms for sample in rows]
    response_started_ms = [
        sample.response_started_ms
        for sample in rows
        if sample.response_started_ms is not None
    ]
    first_content_ms = [
        sample.first_content_ms
        for sample in rows
        if sample.first_content_ms is not None
    ]
    failures = [sample for sample in rows if sample.error is not None]
    terminal_events = Counter(
        sample.terminal_event for sample in rows if sample.terminal_event is not None
    )
    return {
        "requests": len(rows),
        "failures": len(failures),
        "failure_rate": len(failures) / len(rows) if rows else 0.0,
        "response_started_ms": {
            "p50": _percentile(response_started_ms, 0.5),
            "p95": _percentile(response_started_ms, 0.95),
        },
        "ttft_ms": {
            "p50": _percentile(first_content_ms, 0.5),
            "p95": _percentile(first_content_ms, 0.95),
        },
        "total_ms": {
            "p50": _percentile(total_ms, 0.5),
            "p95": _percentile(total_ms, 0.95),
        },
        "events": {
            "total": sum(sample.event_count for sample in rows),
            "terminal": dict(sorted(terminal_events.items())),
        },
    }


async def iter_sse_events(lines: AsyncIterator[str]) -> AsyncIterator[SseEvent]:
    """Parse the subset of SSE used by the workbench without buffering a stream."""
    event = "message"
    data: list[str] = []
    async for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        if not line:
            if data:
                yield SseEvent(event=event, data="\n".join(data))
            event = "message"
            data = []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if not separator:
            continue
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            event = value or "message"
        elif field == "data":
            data.append(value)
    if data:
        yield SseEvent(event=event, data="\n".join(data))


def _short_error(value: object, *, limit: int = 400) -> str:
    text = str(value).strip().replace("\n", " ")
    return text[:limit] if text else type(value).__name__


def _chat_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "text/event-stream",
    }


async def _chat_sample(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    request_index: int,
    message: str,
    model_id: str | None,
    agent_id: str | None,
    enable_tools: bool,
    file_payload: tuple[str, bytes, str] | None,
) -> BenchmarkSample:
    started = time.perf_counter()
    response_started_ms: float | None = None
    first_content_ms: float | None = None
    event_count = 0
    terminal_event: str | None = None
    status_code: int | None = None
    error: str | None = None
    session_id = str(uuid4())
    payload = {
        "message": message,
        "session_id": session_id,
        "model_id": model_id,
        "agent_id": agent_id,
        "enable_tools": enable_tools,
        "search_knowledge": False,
        "live_search": False,
    }
    try:
        request_kwargs: dict[str, Any]
        if file_payload is None:
            request_kwargs = {"json": payload}
        else:
            file_name, data, media_type = file_payload
            request_kwargs = {
                "data": {
                    key: str(value).lower() if isinstance(value, bool) else value
                    for key, value in payload.items()
                    if value is not None
                },
                "files": {"files": (file_name, data, media_type)},
            }
        async with client.stream(
            "POST",
            f"{base_url}/api/chat",
            headers=_chat_headers(token),
            **request_kwargs,
        ) as response:
            status_code = response.status_code
            response_started_ms = (time.perf_counter() - started) * 1_000
            if response.status_code >= 400:
                error = f"HTTP {response.status_code}: {_short_error((await response.aread()).decode(errors='replace'))}"
            else:
                async for event in iter_sse_events(response.aiter_lines()):
                    event_count += 1
                    if event.event == "content.delta" and first_content_ms is None:
                        first_content_ms = (time.perf_counter() - started) * 1_000
                    if event.event in _TERMINAL_CHAT_EVENTS:
                        terminal_event = event.event
                        if event.event != "run.completed":
                            error = f"terminal event {event.event}"
                        break
                if terminal_event is None:
                    error = "SSE stream ended before a terminal event"
    except httpx.HTTPError as exc:
        error = _short_error(exc)
    total_ms = (time.perf_counter() - started) * 1_000
    return BenchmarkSample(
        scenario="chat",
        request_index=request_index,
        status_code=status_code,
        response_started_ms=response_started_ms,
        first_content_ms=first_content_ms,
        total_ms=total_ms,
        event_count=event_count,
        terminal_event=terminal_event,
        error=error,
    )


async def _overview_sample(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    token: str,
    request_index: int,
) -> BenchmarkSample:
    started = time.perf_counter()
    status_code: int | None = None
    response_started_ms: float | None = None
    error: str | None = None
    try:
        response = await client.get(
            f"{base_url}/api/overview",
            params={"range": "24h", "timezone": "UTC"},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
        status_code = response.status_code
        response_started_ms = (time.perf_counter() - started) * 1_000
        if response.status_code >= 400:
            error = f"HTTP {response.status_code}: {_short_error(response.text)}"
    except httpx.HTTPError as exc:
        error = _short_error(exc)
    total_ms = (time.perf_counter() - started) * 1_000
    return BenchmarkSample(
        scenario="overview",
        request_index=request_index,
        status_code=status_code,
        response_started_ms=response_started_ms,
        first_content_ms=None,
        total_ms=total_ms,
        event_count=0,
        terminal_event=None,
        error=error,
    )


async def _run_concurrently(
    *,
    requests: int,
    concurrency: int,
    run_one: Callable[[int], Awaitable[BenchmarkSample]],
) -> list[BenchmarkSample]:
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded(index: int) -> BenchmarkSample:
        async with semaphore:
            return await run_one(index)

    return await asyncio.gather(*(bounded(index) for index in range(1, requests + 1)))


def _load_file(path: Path | None) -> tuple[str, bytes, str] | None:
    if path is None:
        return None
    resolved = path.expanduser().resolve()
    if not resolved.is_file():
        raise ValueError(f"--file must reference a readable file: {resolved}")
    # The app itself applies its own upload limits; cap the benchmark helper as
    # an additional guard against accidentally retaining a huge file in memory.
    data = resolved.read_bytes()
    if len(data) > 64 * 1024 * 1024:
        raise ValueError("--file must not exceed 64 MiB")
    mime = "application/octet-stream"
    if resolved.suffix.lower() == ".txt":
        mime = "text/plain"
    elif resolved.suffix.lower() == ".md":
        mime = "text/markdown"
    return resolved.name, data, mime


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run opt-in real HTTP/SSE staging benchmarks without logging tokens or content."
    )
    parser.add_argument("--url", default=os.getenv("TAIS_BENCHMARK_URL", ""))
    parser.add_argument("--token", default=os.getenv("TAIS_BENCHMARK_TOKEN", ""))
    parser.add_argument(
        "--scenario",
        choices=("chat", "overview", "both"),
        default="both",
    )
    parser.add_argument("--model-id", default=os.getenv("TAIS_BENCHMARK_MODEL_ID"))
    parser.add_argument("--agent-id", default="security-operations")
    parser.add_argument(
        "--message",
        default="Reply with exactly: benchmark-ok",
        help="A safe, short benchmark prompt. Its content is not written to the report.",
    )
    parser.add_argument("--file", type=Path, default=None)
    parser.add_argument("--requests", type=_positive_int, default=6)
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--concurrency", type=_positive_int, default=1)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--enable-tools",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Off by default to isolate model/SSE latency from tool calls.",
    )
    return parser


def _validated_args(args: argparse.Namespace) -> tuple[str, str]:
    base_url = str(args.url or "").strip().rstrip("/")
    token = str(args.token or "").strip()
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("--url (or TAIS_BENCHMARK_URL) must start with http:// or https://")
    if not token:
        raise ValueError("--token (or TAIS_BENCHMARK_TOKEN) is required")
    if args.warmup < 0:
        raise ValueError("--warmup must be zero or greater")
    if args.concurrency > args.requests:
        raise ValueError("--concurrency must not exceed --requests")
    if args.timeout_seconds <= 0:
        raise ValueError("--timeout-seconds must be positive")
    return base_url, token


async def main(args: argparse.Namespace) -> dict[str, object]:
    """Run configured scenarios and return a content-free JSON report."""
    base_url, token = _validated_args(args)
    file_payload = _load_file(args.file)
    timeout = httpx.Timeout(args.timeout_seconds, connect=min(30.0, args.timeout_seconds))
    limits = httpx.Limits(
        max_connections=max(args.concurrency * 2, 4),
        max_keepalive_connections=max(args.concurrency, 1),
    )
    all_samples: list[BenchmarkSample] = []
    async with httpx.AsyncClient(timeout=timeout, limits=limits, follow_redirects=False) as client:
        scenarios: list[Scenario] = []
        if args.scenario in {"chat", "both"}:
            scenarios.append("chat")
        if args.scenario in {"overview", "both"}:
            scenarios.append("overview")

        for scenario in scenarios:
            if scenario == "chat":
                async def run_chat(index: int) -> BenchmarkSample:
                    return await _chat_sample(
                        client,
                        base_url=base_url,
                        token=token,
                        request_index=index,
                        message=args.message,
                        model_id=args.model_id,
                        agent_id=args.agent_id,
                        enable_tools=bool(args.enable_tools),
                        file_payload=file_payload,
                    )

                run_one = run_chat
            else:
                async def run_overview(index: int) -> BenchmarkSample:
                    return await _overview_sample(
                        client,
                        base_url=base_url,
                        token=token,
                        request_index=index,
                    )

                run_one = run_overview

            for warmup_index in range(1, args.warmup + 1):
                await run_one(-warmup_index)
            all_samples.extend(
                await _run_concurrently(
                    requests=args.requests,
                    concurrency=args.concurrency,
                    run_one=run_one,
                )
            )

    by_scenario = {
        scenario: _metric_summary(
            sample for sample in all_samples if sample.scenario == scenario
        )
        for scenario in ("chat", "overview")
        if any(sample.scenario == scenario for sample in all_samples)
    }
    return {
        "kind": "tais-runtime-benchmark-v1",
        "target": base_url,
        "configuration": {
            "scenario": args.scenario,
            "requests_per_scenario": args.requests,
            "warmup_per_scenario": args.warmup,
            "concurrency": args.concurrency,
            "enable_tools": bool(args.enable_tools),
            "has_file": file_payload is not None,
            "model_id": args.model_id or None,
            "agent_id": args.agent_id or None,
        },
        "summary": by_scenario,
        "samples": [asdict(sample) for sample in all_samples],
    }


def run() -> None:
    args = _parser().parse_args()
    report = asyncio.run(main(args))
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        destination = args.output.expanduser()
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    run()
