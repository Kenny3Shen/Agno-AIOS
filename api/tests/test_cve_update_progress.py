"""CVE update progress callback / SSE wiring (no network)."""

from __future__ import annotations

import inspect

from api.routes import cve as cve_routes
from api.tasks import update_cve


def test_main_accepts_on_progress():
    sig = inspect.signature(update_cve.main)
    assert "on_progress" in sig.parameters


def test_update_route_supports_stream_query():
    source = inspect.getsource(cve_routes.update_cve_database)
    assert "stream" in source
    assert "_update_cve_stream" in source
    assert "EventSourceResponse" in inspect.getsource(cve_routes)


def test_emit_progress_helper_exists():
    assert callable(update_cve._emit_progress)
