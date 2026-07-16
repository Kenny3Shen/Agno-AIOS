"""Crawl configured security-news sites and persist articles for Collect."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup
from loguru import logger

from api.persistence.collect_articles import bulk_upsert_collect_articles, ensure_collect_articles_table
from api.services.url2md_service import (
    UnsafeUrlError,
    _get_public_url,
    fetch_and_parse_url,
)
from api.utils.url2md_utils import domain_rules

# Prefer HTTPS home pages for each configured domain rule.
SOURCE_HOME_URLS: dict[str, str] = {
    domain: f"https://{domain}/" for domain in domain_rules
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
    "go.theregister.com": ["https://www.theregister.com/security/"],
    "mp.weixin.qq.com": [],  # WeChat articles need explicit URLs; home is not listable
}

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
    return sorted(domain_rules.keys())


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
    host = (urlsplit(url).hostname or "").lower()
    return host


def _is_same_source(url: str, source_domain: str) -> bool:
    host = _domain_of(url)
    if not host:
        return False
    source = source_domain.lower()
    return host == source or host.endswith("." + source) or source.endswith("." + host)


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


async def discover_article_urls(
    *,
    domains: list[str] | None = None,
    max_links_per_source: int = 25,
) -> dict[str, list[str]]:
    """Fetch list pages for each source and collect article URLs."""
    selected = domains or configured_source_domains()
    result: dict[str, list[str]] = {}
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=25,
        follow_redirects=False,
    ) as client:
        for domain in selected:
            if domain not in domain_rules:
                continue
            seeds = list(SOURCE_EXTRA_SEEDS.get(domain) or [])
            home = SOURCE_HOME_URLS.get(domain)
            if home and home not in seeds:
                seeds.insert(0, home)
            links: list[str] = []
            seen: set[str] = set()
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
            result[domain] = links
            logger.info("collect crawl discovered {} links for {}", len(links), domain)
    return result


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
) -> dict[str, Any]:
    """Discover, fetch, and upsert articles. Returns crawl stats."""
    await ensure_collect_articles_table()
    discovered = await discover_article_urls(
        domains=domains,
        max_links_per_source=max_links_per_source,
    )
    urls: list[str] = []
    for domain in sorted(discovered.keys()):
        for link in discovered[domain]:
            urls.append(link)
            if len(urls) >= max_articles_total:
                break
        if len(urls) >= max_articles_total:
            break

    records: list[dict[str, Any]] = []
    ok = 0
    err = 0
    for url in urls:
        record = await fetch_article_record(url)
        records.append(record)
        if record.get("status") == "ok":
            ok += 1
        else:
            err += 1

    saved = await bulk_upsert_collect_articles(records)
    stats = {
        "sources": len(discovered),
        "discovered": sum(len(v) for v in discovered.values()),
        "fetched": len(records),
        "saved": saved,
        "ok": ok,
        "error": err,
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
