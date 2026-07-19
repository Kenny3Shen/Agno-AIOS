from __future__ import annotations

import asyncio

from api.tasks.benchmark_runtime import BenchmarkSample, _metric_summary, iter_sse_events


async def _lines(values: list[str]):
    for value in values:
        yield value


def test_iter_sse_events_handles_comments_multiline_data_and_eof() -> None:
    async def collect():
        return [
            event
            async for event in iter_sse_events(
                _lines(
                    [
                        ": ping",
                        "event: content.delta",
                        "data: first",
                        "data: second",
                        "",
                        "event: run.completed",
                        "data: {\"run_id\":\"run-1\"}",
                    ]
                )
            )
        ]

    events = asyncio.run(collect())

    assert [(event.event, event.data) for event in events] == [
        ("content.delta", "first\nsecond"),
        ("run.completed", '{"run_id":"run-1"}'),
    ]


def test_metric_summary_reports_percentiles_failures_and_terminal_events() -> None:
    samples = [
        BenchmarkSample(
            scenario="chat",
            request_index=1,
            status_code=200,
            response_started_ms=10.0,
            first_content_ms=20.0,
            total_ms=40.0,
            event_count=3,
            terminal_event="run.completed",
            error=None,
        ),
        BenchmarkSample(
            scenario="chat",
            request_index=2,
            status_code=200,
            response_started_ms=20.0,
            first_content_ms=40.0,
            total_ms=80.0,
            event_count=4,
            terminal_event="run.failed",
            error="terminal event run.failed",
        ),
    ]

    summary = _metric_summary(samples)

    assert summary["requests"] == 2
    assert summary["failures"] == 1
    assert summary["failure_rate"] == 0.5
    assert summary["ttft_ms"] == {"p50": 30.0, "p95": 39.0}
    assert summary["total_ms"] == {"p50": 60.0, "p95": 78.0}
    assert summary["events"] == {
        "total": 7,
        "terminal": {"run.completed": 1, "run.failed": 1},
    }
