from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock

import httpx
import pytest

from api.services import collect_crawl_service, url2md_service


class _ClientContext:
    def __init__(self, client: object) -> None:
        self.client = client
        self.entered = 0
        self.exited = 0

    async def __aenter__(self) -> object:
        self.entered += 1
        return self.client

    async def __aexit__(self, *_args: object) -> None:
        self.exited += 1


@pytest.mark.asyncio
async def test_crawl_reuses_one_parser_client_for_all_articles(monkeypatch) -> None:
    shared_client = object()
    context = _ClientContext(shared_client)
    urls = [
        "https://one.example/articles/one",
        "https://two.example/articles/two",
    ]
    received_clients: list[object] = []

    async def fake_fetch(url: str, *, client: object | None = None) -> dict[str, object]:
        received_clients.append(client)
        return {
            "url": url,
            "source_domain": url.split("/")[2],
            "title": "Article",
            "markdown": "# Article\n\nBody",
            "summary": "Body",
            "cve_ids": ["CVE-2024-1234"],
            "status": "ok",
        }

    monkeypatch.setattr(
        collect_crawl_service,
        "ensure_collect_articles_table",
        AsyncMock(),
    )
    monkeypatch.setattr(
        collect_crawl_service,
        "discover_article_urls",
        AsyncMock(
            return_value={
                "one.example": [urls[0]],
                "two.example": [urls[1]],
            }
        ),
    )
    monkeypatch.setattr(
        collect_crawl_service,
        "create_url2md_http_client",
        lambda: context,
    )
    monkeypatch.setattr(collect_crawl_service, "fetch_article_record", fake_fetch)
    monkeypatch.setattr(
        collect_crawl_service,
        "bulk_upsert_collect_articles",
        AsyncMock(return_value=2),
    )

    stats = await collect_crawl_service.crawl_and_persist(
        max_articles_total=2,
        skip_existing=False,
        fetch_concurrency=2,
    )

    assert stats["saved"] == 2
    assert received_clients == [shared_client, shared_client]
    assert context.entered == 1
    assert context.exited == 1


@pytest.mark.asyncio
async def test_fetch_article_record_uses_supplied_client(monkeypatch) -> None:
    shared_client = cast(httpx.AsyncClient, object())
    calls: list[tuple[object, list[str]]] = []

    async def fake_parse(client: object, urls: list[str]) -> list[str]:
        calls.append((client, urls))
        return ["# CVE article\n\nDetails for CVE-2024-1234."]

    monkeypatch.setattr(
        collect_crawl_service,
        "fetch_and_parse_url_with_client",
        fake_parse,
    )

    record = await collect_crawl_service.fetch_article_record(
        "https://example.test/articles/cve",
        client=shared_client,
    )

    assert calls == [(shared_client, ["https://example.test/articles/cve"])]
    assert record["status"] == "ok"
    assert record["cve_ids"] == ["CVE-2024-1234"]


@pytest.mark.asyncio
async def test_legacy_url_parser_api_creates_a_client_and_delegates(monkeypatch) -> None:
    client = object()
    context = _ClientContext(client)
    calls: list[tuple[object, list[str]]] = []

    async def fake_parse(client_arg: object, urls: list[str]) -> list[str]:
        calls.append((client_arg, urls))
        return ["# Parsed"]

    monkeypatch.setattr(url2md_service, "create_url2md_http_client", lambda: context)
    monkeypatch.setattr(url2md_service, "fetch_and_parse_url_with_client", fake_parse)

    assert await url2md_service.fetch_and_parse_url(["https://example.test/a"]) == [
        "# Parsed"
    ]
    assert calls == [(client, ["https://example.test/a"])]
    assert context.entered == 1
    assert context.exited == 1
