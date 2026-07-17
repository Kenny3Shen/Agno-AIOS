"""Collect search payload / status filter unit tests (no DB)."""

from __future__ import annotations

import inspect

from api.persistence import collect_articles
from api.services import collect_service


def test_search_collect_articles_signature_has_status_and_slim_default():
    sig = inspect.signature(collect_articles.search_collect_articles)
    assert "status" in sig.parameters
    assert sig.parameters["status"].default == "ok"
    assert sig.parameters["include_markdown"].default is False


def test_search_articles_service_forwards_status():
    sig = inspect.signature(collect_service.search_articles)
    assert "status" in sig.parameters
    assert sig.parameters["status"].default == "ok"


def test_reparse_article_helper_exists():
    assert callable(collect_service.reparse_article)
