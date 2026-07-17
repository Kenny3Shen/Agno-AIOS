"""Read-side service for Collect articles stored in Postgres.

List/detail responses attach derived ``cve_ids`` from title/summary/(body)
without a separate DB column — keeps the schema simple while enabling CVE
deep-links from the security news library.
"""

from __future__ import annotations

import asyncio
from typing import Any

from api.persistence.collect_articles import (
    count_collect_articles_by_status,
    get_collect_article,
    list_collect_source_domains,
    list_collect_source_stats,
    list_error_collect_article_ids,
    search_collect_articles,
)
from api.services.collect_crawl_service import (
    configured_source_domains,
    crawl_and_persist,
    extract_cve_ids,
    parse_and_store_url,
)
from api.utils.url2md_utils import active_domain_rules


def _with_cve_ids(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Attach derived CVE ids for UI without a separate DB column."""
    if not row:
        return row
    out = dict(row)
    existing = out.get("cve_ids")
    if isinstance(existing, list) and existing:
        out["cve_ids"] = [str(item).upper() for item in existing if item]
        return out
    out["cve_ids"] = extract_cve_ids(
        str(out.get("title") or ""),
        str(out.get("summary") or ""),
        str(out.get("markdown") or ""),
    )
    return out


async def search_articles(
    *,
    query: str = "",
    source_domain: str | None = None,
    status: str | None = "ok",
    page: int = 1,
    size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    rows, total = await search_collect_articles(
        query=query,
        source_domain=source_domain,
        status=status,
        page=page,
        size=size,
        include_markdown=False,
    )
    # List payloads omit body; CVE tags come from title/summary only.
    return [item for item in (_with_cve_ids(row) for row in rows) if item is not None], total


async def get_article(article_id: int) -> dict[str, Any] | None:
    row = await get_collect_article(article_id)
    return _with_cve_ids(row)


async def list_sources() -> list[dict[str, Any]]:
    """Configured crawl sources + ok/error health counts from DB."""
    stats_rows = await list_collect_source_stats()
    stats_by_domain = {str(row["domain"]): row for row in stats_rows}
    domains_in_db = set(stats_by_domain) | set(await list_collect_source_domains())
    items: list[dict[str, Any]] = []
    for domain in configured_source_domains():
        stats = stats_by_domain.get(domain) or {}
        items.append(
            {
                "domain": domain,
                "has_rule": domain in active_domain_rules(),
                "has_articles": domain in domains_in_db or int(stats.get("total") or 0) > 0,
                "ok_count": int(stats.get("ok") or 0),
                "error_count": int(stats.get("error") or 0),
                "total_count": int(stats.get("total") or 0),
            }
        )
    return items


async def run_crawl(
    *,
    domains: list[str] | None = None,
    max_links_per_source: int = 20,
    max_articles_total: int = 80,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    return await crawl_and_persist(
        domains=domains,
        max_links_per_source=max_links_per_source,
        max_articles_total=max_articles_total,
        on_progress=on_progress,
    )


async def reparse_article(article_id: int) -> dict[str, Any]:
    """Re-fetch a single stored URL and return the refreshed row."""
    existing = await get_collect_article(article_id)
    if not existing:
        raise LookupError(f"article {article_id} not found")
    url = str(existing.get("url") or "").strip()
    if not url:
        raise ValueError("article has no URL")
    record = await parse_and_store_url(url)
    # parse_and_store returns DB row without cve_ids — re-attach for clients.
    return _with_cve_ids(record) or record


async def reparse_failed_articles(
    *,
    source_domain: str | None = None,
    limit: int = 10,
    concurrency: int = 3,
) -> dict[str, Any]:
    """Re-fetch up to *limit* failed articles (newest first)."""
    ids = await list_error_collect_article_ids(
        source_domain=source_domain,
        limit=limit,
    )
    if not ids:
        return {
            "requested": 0,
            "ok": 0,
            "error": 0,
            "results": [],
        }

    semaphore = asyncio.Semaphore(max(1, min(int(concurrency or 3), 6)))

    async def _one(article_id: int) -> dict[str, Any]:
        async with semaphore:
            try:
                record = await reparse_article(article_id)
                return {
                    "id": article_id,
                    "url": record.get("url"),
                    "status": record.get("status"),
                    "error_message": record.get("error_message") or "",
                }
            except Exception as exc:  # noqa: BLE001 — per-item failure
                return {
                    "id": article_id,
                    "url": "",
                    "status": "error",
                    "error_message": str(exc)[:500],
                }

    results = list(await asyncio.gather(*[_one(item) for item in ids]))
    ok = sum(1 for item in results if item.get("status") == "ok")
    return {
        "requested": len(ids),
        "ok": ok,
        "error": len(results) - ok,
        "results": results,
    }


async def library_status_counts(
    *,
    source_domain: str | None = None,
) -> dict[str, int]:
    counts = await count_collect_articles_by_status(source_domain=source_domain)
    return {
        "ok": int(counts.get("ok") or 0),
        "error": int(counts.get("error") or 0),
        "total": sum(int(v or 0) for v in counts.values()),
    }
