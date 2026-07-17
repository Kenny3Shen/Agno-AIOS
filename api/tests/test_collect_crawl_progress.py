"""Collect crawl progress callback / SSE wiring (no network)."""

from __future__ import annotations

import inspect

from api.routes import collect as collect_routes
from api.services import collect_crawl_service


def test_crawl_and_persist_accepts_on_progress():
    sig = inspect.signature(collect_crawl_service.crawl_and_persist)
    assert "on_progress" in sig.parameters


def test_discover_accepts_on_progress():
    sig = inspect.signature(collect_crawl_service.discover_article_urls)
    assert "on_progress" in sig.parameters


def test_crawl_route_supports_stream_query():
    source = inspect.getsource(collect_routes.crawl_collect_sources)
    assert "stream" in source
    assert "_crawl_collect_stream" in source
    assert "EventSourceResponse" in inspect.getsource(collect_routes)


def test_emit_progress_helper_exists():
    assert callable(collect_crawl_service._emit_progress)
