"""Read-side service for Collect articles stored in Postgres."""

from __future__ import annotations

from typing import Any

from api.persistence.collect_articles import (
    get_collect_article,
    list_collect_source_domains,
    search_collect_articles,
)
from api.services.collect_crawl_service import configured_source_domains, crawl_and_persist
from api.utils.url2md_utils import active_domain_rules


async def search_articles(
    *,
    query: str = "",
    source_domain: str | None = None,
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    return await search_collect_articles(
        query=query,
        source_domain=source_domain,
        page=page,
        size=size,
    )


async def get_article(article_id: int) -> dict[str, Any] | None:
    return await get_collect_article(article_id)


async def list_sources() -> list[dict[str, Any]]:
    """Configured crawl sources + counts from DB when available."""
    domains_in_db = set(await list_collect_source_domains())
    items: list[dict[str, Any]] = []
    for domain in configured_source_domains():
        items.append(
            {
                "domain": domain,
                "has_rule": domain in active_domain_rules(),
                "has_articles": domain in domains_in_db,
            }
        )
    return items


async def run_crawl(
    *,
    domains: list[str] | None = None,
    max_links_per_source: int = 20,
    max_articles_total: int = 80,
) -> dict[str, Any]:
    return await crawl_and_persist(
        domains=domains,
        max_links_per_source=max_links_per_source,
        max_articles_total=max_articles_total,
    )
