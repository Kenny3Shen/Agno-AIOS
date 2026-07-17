"""Collect bulk reparse / stats unit tests (no DB)."""

from __future__ import annotations

import inspect

from api.persistence import collect_articles
from api.routes import collect as collect_routes
from api.services import collect_service


def test_list_error_ids_and_stats_helpers_exist():
    assert callable(collect_articles.list_error_collect_article_ids)
    assert callable(collect_articles.count_collect_articles_by_status)
    assert callable(collect_articles.list_collect_source_stats)


def test_reparse_failed_articles_signature():
    sig = inspect.signature(collect_service.reparse_failed_articles)
    assert "limit" in sig.parameters
    assert "source_domain" in sig.parameters


def test_bulk_reparse_route_registered_before_article_id():
    source = inspect.getsource(collect_routes)
    bulk_at = source.find("/articles/reparse-failed")
    id_at = source.find("/articles/{article_id}")
    assert bulk_at > 0
    assert id_at > 0
    assert bulk_at < id_at
