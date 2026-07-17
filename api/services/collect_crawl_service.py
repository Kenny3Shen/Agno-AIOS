"""Crawl configured security-news sites and persist articles for Collect."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from api.persistence.collect_articles import (
    bulk_upsert_collect_articles,
    ensure_collect_articles_table,
    list_existing_ok_urls,
)
from api.services.url2md_service import (
    UnsafeUrlError,
    _get_public_url,
    fetch_and_parse_url,
)
from api.utils.url2md_utils import (
    active_domain_rules,
    resolve_domain_rule_key,
)

# Prefer HTTPS home pages for each active domain rule.
SOURCE_HOME_URLS: dict[str, str] = {
    domain: f"https://{domain}/" for domain in active_domain_rules()
}

# Extra seeds when home alone is thin (optional list pages).
SOURCE_EXTRA_SEEDS: dict[str, list[str]] = {
    "thehackernews.com": ["https://thehackernews.com/"],
    "cybersecuritynews.com": ["https://cybersecuritynews.com/"],
    "www.freebuf.com": ["https://www.freebuf.com/"],
    "www.anquanke.com": ["https://www.anquanke.com/"],
    "securityaffairs.com": ["https://securityaffairs.com/"],
    "hackread.com": ["https://www.hackread.com/"],
    "securityonline.info": ["https://securityonline.info/"],
    "thecyberexpress.com": ["https://thecyberexpress.com/"],
    "www.csoonline.com": ["https://www.csoonline.com/"],
    "dailydarkweb.net": ["https://dailydarkweb.net/"],
    "mp.weixin.qq.com": [],  # WeChat articles need explicit URLs; home is not listable
}

# Concurrent HTTP/parse workers for article body fetch.
FETCH_CONCURRENCY = 6
DISCOVER_CONCURRENCY = 4

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}

SKIP_PATH_MARKERS = (
    "/tag/",
    "/tags/",
    "/category/",
    "/author/",
    "/page/",
    "/login",
    "/search",
    "/feed",
    "/rss",
    "/wp-json",
    "/cdn-cgi",
    "#",
    "javascript:",
    "mailto:",
)

ARTICLE_PATH_HINTS = re.compile(
    r"(/\d{4}/|/20\d{2}/|/news/|/post/|/posts/|/article|/articles|"
    r"/story/|/vulnerabilit|/threat|/malware|/advisory|/blog/|/content/)",
    re.I,
)


def configured_source_domains() -> list[str]:
    return sorted(active_domain_rules().keys())


def _normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    # Drop fragments; keep query for sites that need it sparingly
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    clean = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{path}"
    if parsed.query and len(parsed.query) < 120:
        clean = f"{clean}?{parsed.query}"
    return clean


def _domain_of(url: str) -> str:
    rule_key = resolve_domain_rule_key(url)
    if rule_key:
        return rule_key
    return (urlsplit(url).hostname or "").lower()


def _is_same_source(url: str, source_domain: str) -> bool:
    raw_host = (urlsplit(url).hostname or "").lower()
    if not raw_host:
        return False
    source = source_domain.lower()
    rule_key = resolve_domain_rule_key(url) or ""
    for host in {raw_host, rule_key}:
        if not host:
            continue
        if host == source or host.endswith("." + source) or source.endswith("." + host):
            return True
    return False


def _looks_like_article(url: str, source_domain: str) -> bool:
    if not _is_same_source(url, source_domain):
        return False
    lower = url.lower()
    if any(marker in lower for marker in SKIP_PATH_MARKERS):
        return False
    path = urlsplit(url).path or ""
    if path in {"", "/"}:
        return False
    # WeChat permanent links
    if source_domain == "mp.weixin.qq.com":
        return "mp.weixin.qq.com/s" in lower
    # Generic: deep enough path or dated / news-like path
    depth = len([p for p in path.split("/") if p])
    if depth >= 2:
        return True
    if ARTICLE_PATH_HINTS.search(path):
        return True
    # Single segment slug with hyphen often is a post
    slug = path.strip("/")
    return bool(slug) and ("-" in slug or "_" in slug) and len(slug) > 12


def _title_from_markdown(markdown: str) -> str:
    for line in (markdown or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()[:500]
    return ""


def _summary_from_markdown(markdown: str, limit: int = 280) -> str:
    lines: list[str] = []
    for line in (markdown or "").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("```") or stripped.startswith("|"):
            continue
        lines.append(stripped)
        if sum(len(item) for item in lines) >= limit:
            break
    text = " ".join(lines).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def extract_article_links(html: str, base_url: str, source_domain: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        absolute = _normalize_url(urljoin(base_url, href))
        if not absolute or absolute in seen:
            continue
        if not _looks_like_article(absolute, source_domain):
            continue
        seen.add(absolute)
        found.append(absolute)
    return found




def select_urls_round_robin(
    discovered: dict[str, list[str]],
    *,
    max_articles_total: int,
    exclude: set[str] | None = None,
) -> list[str]:
    """Fairly interleave per-source URLs up to *max_articles_total*.

    Skips URLs in *exclude* (e.g. already stored successfully) without
    starving later sources the way a sorted concat + hard slice would.
    """
    if max_articles_total <= 0 or not discovered:
        return []
    blocked = exclude or set()
    queues: dict[str, list[str]] = {}
    for domain, links in discovered.items():
        kept = [url for url in links if url and url not in blocked]
        if kept:
            queues[domain] = kept
    if not queues:
        return []
    domains = sorted(queues.keys())
    indices = {domain: 0 for domain in domains}
    selected: list[str] = []
    while len(selected) < max_articles_total:
        progressed = False
        for domain in domains:
            idx = indices[domain]
            links = queues[domain]
            if idx >= len(links):
                continue
            selected.append(links[idx])
            indices[domain] = idx + 1
            progressed = True
            if len(selected) >= max_articles_total:
                break
        if not progressed:
            break
    return selected


class CollectCrawlAlreadyRunningError(RuntimeError):
    """Raised when another collect crawl is already in progress."""


_CRAWL_LOCK = asyncio.Lock()


async def _discover_one_domain(
    client: httpx.AsyncClient,
    domain: str,
    *,
    max_links_per_source: int,
    semaphore: asyncio.Semaphore,
) -> tuple[str, list[str]]:
    active = active_domain_rules()
    if domain not in active:
        return domain, []
    seeds = list(SOURCE_EXTRA_SEEDS.get(domain) or [])
    home = SOURCE_HOME_URLS.get(domain)
    if home and home not in seeds:
        seeds.insert(0, home)
    links: list[str] = []
    seen: set[str] = set()
    async with semaphore:
        for seed in seeds:
            try:
                resp = await _get_public_url(client, seed)
                if resp.status_code != 200:
                    logger.warning("collect crawl seed HTTP {}: {}", resp.status_code, seed)
                    continue
                for link in extract_article_links(resp.text, str(resp.url), domain):
                    if link in seen:
                        continue
                    seen.add(link)
                    links.append(link)
                    if len(links) >= max_links_per_source:
                        break
            except (UnsafeUrlError, httpx.HTTPError) as exc:
                logger.warning("collect crawl seed failed {}: {}", seed, exc)
            if len(links) >= max_links_per_source:
                break
    logger.info("collect crawl discovered {} links for {}", len(links), domain)
    return domain, links


async def discover_article_urls(
    *,
    domains: list[str] | None = None,
    max_links_per_source: int = 25,
) -> dict[str, list[str]]:
    """Fetch list pages for each source and collect article URLs."""
    active = set(active_domain_rules())
    selected = [d for d in (domains or configured_source_domains()) if d in active]
    if not selected:
        return {}
    semaphore = asyncio.Semaphore(DISCOVER_CONCURRENCY)
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=25,
        follow_redirects=False,
    ) as client:
        pairs = await asyncio.gather(
            *[
                _discover_one_domain(
                    client,
                    domain,
                    max_links_per_source=max_links_per_source,
                    semaphore=semaphore,
                )
                for domain in selected
            ]
        )
    return {domain: links for domain, links in pairs}


async def fetch_article_record(url: str) -> dict[str, Any]:
    """Parse one URL into a collect_articles row payload."""
    domain = _domain_of(url)
    now = datetime.now(UTC)
    try:
        markdowns = await fetch_and_parse_url([url])
        markdown = (markdowns[0] if markdowns else "").strip()
        if not markdown or markdown.startswith(
            ("HTTP error", "Network error", "Unexpected error", "Content too short", "Restricted access")
        ):
            return {
                "url": _normalize_url(url) or url,
                "source_domain": domain,
                "title": "",
                "markdown": "",
                "summary": "",
                "status": "error",
                "error_message": markdown[:2000] if markdown else "empty content",
                "fetched_at": now,
            }
        title = _title_from_markdown(markdown) or domain
        return {
            "url": _normalize_url(url) or url,
            "source_domain": domain,
            "title": title,
            "markdown": markdown,
            "summary": _summary_from_markdown(markdown),
            "status": "ok",
            "error_message": "",
            "fetched_at": now,
        }
    except Exception as exc:  # noqa: BLE001 — persist failure row
        logger.exception("collect fetch failed {}", url)
        return {
            "url": _normalize_url(url) or url,
            "source_domain": domain,
            "title": "",
            "markdown": "",
            "summary": "",
            "status": "error",
            "error_message": str(exc)[:2000],
            "fetched_at": now,
        }


async def crawl_and_persist(
    *,
    domains: list[str] | None = None,
    max_links_per_source: int = 20,
    max_articles_total: int = 80,
    skip_existing: bool = True,
    fetch_concurrency: int = FETCH_CONCURRENCY,
) -> dict[str, Any]:
    """Discover, fetch, and upsert articles. Returns crawl stats.

    URL selection is round-robin across sources so early alphabetical domains
    cannot consume the whole ``max_articles_total`` budget. When
    ``skip_existing`` is set, already-ok URLs are excluded *before* selection
    so the budget is filled with new work.
    """
    if _CRAWL_LOCK.locked():
        raise CollectCrawlAlreadyRunningError("Collect crawl is already running")

    async with _CRAWL_LOCK:
        return await _crawl_and_persist_locked(
            domains=domains,
            max_links_per_source=max_links_per_source,
            max_articles_total=max_articles_total,
            skip_existing=skip_existing,
            fetch_concurrency=fetch_concurrency,
        )


async def _crawl_and_persist_locked(
    *,
    domains: list[str] | None,
    max_links_per_source: int,
    max_articles_total: int,
    skip_existing: bool,
    fetch_concurrency: int,
) -> dict[str, Any]:
    await ensure_collect_articles_table()
    discovered = await discover_article_urls(
        domains=domains,
        max_links_per_source=max_links_per_source,
    )
    discovered_total = sum(len(links) for links in discovered.values())
    all_urls = [url for links in discovered.values() for url in links]

    existing: set[str] = set()
    if skip_existing and all_urls:
        existing = await list_existing_ok_urls(all_urls)
    skipped = sum(1 for url in all_urls if url in existing)

    urls = select_urls_round_robin(
        discovered,
        max_articles_total=max_articles_total,
        exclude=existing if skip_existing else None,
    )
    selected_by_source: dict[str, int] = {}
    for url in urls:
        domain = _domain_of(url)
        selected_by_source[domain] = selected_by_source.get(domain, 0) + 1

    semaphore = asyncio.Semaphore(max(1, int(fetch_concurrency or FETCH_CONCURRENCY)))

    async def _bounded(url: str) -> dict[str, Any]:
        async with semaphore:
            return await fetch_article_record(url)

    records: list[dict[str, Any]] = []
    if urls:
        records = list(await asyncio.gather(*[_bounded(url) for url in urls]))

    ok = sum(1 for record in records if record.get("status") == "ok")
    err = len(records) - ok
    saved = await bulk_upsert_collect_articles(records)
    stats = {
        "sources": len(discovered),
        "discovered": discovered_total,
        "skipped_existing": skipped,
        "selected": len(urls),
        "fetched": len(records),
        "saved": saved,
        "ok": ok,
        "error": err,
        "by_source_discovered": {k: len(v) for k, v in discovered.items()},
        "by_source_selected": selected_by_source,
        # Backward-compatible alias (discovered counts).
        "by_source": {k: len(v) for k, v in discovered.items()},
    }
    logger.info("collect crawl finished: {}", stats)
    return stats


async def parse_and_store_url(url: str) -> dict[str, Any]:
    """On-demand parse used by /url2md/parse — still persists for Collect library."""
    from api.persistence.collect_articles import upsert_collect_article

    await ensure_collect_articles_table()
    record = await fetch_article_record(url)
    stored = await upsert_collect_article(record)
    return {**stored, "saved": True}
