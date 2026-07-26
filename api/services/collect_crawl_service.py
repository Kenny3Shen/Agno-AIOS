"""Crawl configured security-news sites and persist articles for Collect.

Discovery walks home + optional seed list pages, round-robins URLs across
sources, and upserts Markdown into ``collect_articles``. CVE IDs are
extracted from title/body for intel linking (not a separate store).
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Mapping
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
    create_url2md_http_client,
    fetch_and_parse_url,
    fetch_and_parse_url_with_client,
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
    "www.bleepingcomputer.com": ["https://www.bleepingcomputer.com/news/"],
    "krebsonsecurity.com": ["https://krebsonsecurity.com/"],
    "www.securityweek.com": ["https://www.securityweek.com/"],
    "www.darkreading.com": ["https://www.darkreading.com/"],
    "therecord.media": ["https://therecord.media/"],
    "unit42.paloaltonetworks.com": ["https://unit42.paloaltonetworks.com/"],
    "blog.cloudflare.com": ["https://blog.cloudflare.com/tag/security/"],
    "mp.weixin.qq.com": [],  # WeChat articles need explicit URLs; home is not listable
}

# Concurrent HTTP/parse workers for article body fetch.
FETCH_CONCURRENCY = 6
DISCOVER_CONCURRENCY = 4
# Extra list pages to walk after home (page/2 …) when the home feed is thin.
MAX_LIST_PAGES = 3

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
}


# CVE identifiers surfaced on article cards / preview (order preserved, de-duped).
# The CVE Program permits sequence values longer than seven digits.
CVE_ID_RE = re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE)


def extract_cve_ids(*parts: str, limit: int = 24) -> list[str]:
    """Collect unique canonical CVE IDs from free text (title, summary, body)."""
    seen: list[str] = []
    for part in parts:
        if not part:
            continue
        for match in CVE_ID_RE.finditer(part):
            cve_id = match.group(0).upper()
            if cve_id not in seen:
                seen.append(cve_id)
            if len(seen) >= limit:
                return seen
    return seen


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

# Fetching these assets through the HTML parser cannot produce an article body.
NON_ARTICLE_PATH_SUFFIXES = (
    ".pdf",
    ".xml",
    ".json",
    ".zip",
)

# Some sources expose article dates in every real post URL.  Requiring that
# shape avoids pulling their navigation, policy, archive, and landing pages.
_DATED_ARTICLE_SOURCE_PATHS: dict[str, re.Pattern[str]] = {
    "thehackernews.com": re.compile(r"/20\d{2}/\d{2}/", re.I),
    "xlab.tencent.com": re.compile(r"/en/20\d{2}/\d{2}/\d{2}/", re.I),
}

_NAVIGATION_ANCESTOR_TAGS = frozenset({"nav", "aside"})
_CHROME_BOUNDARY_TAGS = frozenset({"header", "footer"})
_NAVIGATION_COMPONENT_RE = re.compile(
    r"^(?:(?:site|cs)-)?(?:header|footer|nav|menu)(?:[-_]|$)",
    re.I,
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
    # Drop fragments and normalize an optional trailing slash so existing rows
    # are consistently recognized on later crawls.
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


def _matches_source_article_path(path: str, source_domain: str) -> bool:
    """Apply source-specific URL shapes before treating a link as an article."""
    normalized_path = path.rstrip("/") or "/"
    source = source_domain.lower()

    # The Record uses /news/<topic> for section landing pages; current article
    # URLs are top-level slugs.  Do not spend a crawl slot on those listings.
    if source == "therecord.media" and re.fullmatch(r"/news/[^/]+", normalized_path):
        return False

    dated_path = _DATED_ARTICLE_SOURCE_PATHS.get(source)
    if dated_path is not None:
        return bool(dated_path.search(path))

    # These are static pages at Hackread that otherwise look like article
    # slugs under the generic heuristic below.
    if source == "hackread.com" and normalized_path in {
        "/about-us",
        "/privacy-policy",
        "/submit-press-release",
    }:
        return False

    return True


def _is_navigation_anchor(anchor: Any) -> bool:
    """Return whether an anchor belongs to chrome rather than page content."""
    is_inside_article = any(
        str(getattr(ancestor, "name", "") or "").lower() == "article"
        for ancestor in anchor.parents
    )
    for ancestor in anchor.parents:
        name = str(getattr(ancestor, "name", "") or "").lower()
        if name in _NAVIGATION_ANCESTOR_TAGS:
            return True
        if name in _CHROME_BOUNDARY_TAGS and not is_inside_article:
            return True
        attrs = getattr(ancestor, "attrs", {})
        if not isinstance(attrs, Mapping):
            continue
        if str(attrs.get("role") or "").lower() == "navigation":
            return True
        classes = attrs.get("class") or []
        components = [*classes, attrs.get("id")]
        if any(
            _NAVIGATION_COMPONENT_RE.match(str(component or ""))
            for component in components
        ):
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
    if path.lower().endswith(NON_ARTICLE_PATH_SUFFIXES):
        return False
    if not _matches_source_article_path(path, source_domain):
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



def _is_list_path(url: str) -> bool:
    """True for category/tag/pagination list pages (not article bodies)."""
    lower = url.lower()
    path = urlsplit(url).path or ""
    if any(marker in lower for marker in ("/tag/", "/tags/", "/category/", "/author/", "/search")):
        return True
    if re.search(r"/page/\d+/?$", path) or re.search(r"[?&]page=\d+", lower):
        return True
    return False


def _list_page_seed_urls(home: str, *, max_pages: int = MAX_LIST_PAGES) -> list[str]:
    """Build common WordPress-style list pagination URLs from a home seed."""
    if max_pages <= 1 or not home:
        return []
    base = home.rstrip("/") + "/"
    seeds: list[str] = []
    for page in range(2, max_pages + 1):
        seeds.append(f"{base}page/{page}/")
    return seeds


def extract_list_page_links(html: str, base_url: str, source_domain: str) -> list[str]:
    """Collect same-source list/pagination links for deeper discovery."""
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
        if not _is_same_source(absolute, source_domain):
            continue
        rel = " ".join(anchor.get("rel") or []).lower()
        text = anchor.get_text(" ", strip=True).lower()
        if "next" in rel or text in {"next", "older", "下一页", "下页", "»", "›"}:
            if absolute not in seen:
                seen.add(absolute)
                found.append(absolute)
            continue
        if _is_list_path(absolute):
            seen.add(absolute)
            found.append(absolute)
    return found


def extract_article_links(html: str, base_url: str, source_domain: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        if _is_navigation_anchor(anchor):
            continue
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

ProgressCallback = Callable[[Mapping[str, Any]], Awaitable[None] | None]


async def _emit_progress(
    on_progress: ProgressCallback | None,
    *,
    stage: str,
    status: str = "running",
    message: str = "",
    **extra: Any,
) -> None:
    if on_progress is None:
        return
    payload: dict[str, Any] = {
        "stage": stage,
        "status": status,
        "message": message,
        **extra,
    }
    result = on_progress(payload)
    if asyncio.iscoroutine(result):
        await result


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
    # Walk common list pagination after the home feed when still under quota.
    for page_seed in _list_page_seed_urls(home or "", max_pages=MAX_LIST_PAGES):
        if page_seed not in seeds:
            seeds.append(page_seed)
    links: list[str] = []
    seen: set[str] = set()
    visited_seeds: set[str] = set()
    queue = list(seeds)
    async with semaphore:
        while queue and len(links) < max_links_per_source:
            seed = queue.pop(0)
            normalized_seed = _normalize_url(seed) or seed
            if normalized_seed in visited_seeds:
                continue
            visited_seeds.add(normalized_seed)
            try:
                resp = None
                last_exc: Exception | None = None
                for attempt in range(2):
                    try:
                        resp = await _get_public_url(client, seed)
                        if resp.status_code in {429, 500, 502, 503, 504} and attempt == 0:
                            await asyncio.sleep(0.5)
                            continue
                        break
                    except httpx.HTTPError as exc:
                        last_exc = exc
                        if attempt == 0:
                            await asyncio.sleep(0.5)
                            continue
                        raise
                if resp is None:
                    if last_exc:
                        raise last_exc
                    continue
                if resp.status_code != 200:
                    logger.warning("collect crawl seed HTTP {}: {}", resp.status_code, seed)
                    continue
                final_url = str(resp.url)
                for link in extract_article_links(resp.text, final_url, domain):
                    if link in seen:
                        continue
                    seen.add(link)
                    links.append(link)
                    if len(links) >= max_links_per_source:
                        break
                # Enqueue same-source list pages (bounded) for deeper discovery.
                if len(links) < max_links_per_source and len(visited_seeds) < MAX_LIST_PAGES + 2:
                    for list_link in extract_list_page_links(resp.text, final_url, domain):
                        norm = _normalize_url(list_link) or list_link
                        if norm in visited_seeds:
                            continue
                        if norm not in {_normalize_url(item) or item for item in queue}:
                            queue.append(list_link)
            except (UnsafeUrlError, httpx.HTTPError) as exc:
                logger.warning("collect crawl seed failed {}: {}", seed, exc)
    logger.info("collect crawl discovered {} links for {}", len(links), domain)
    return domain, links


async def discover_article_urls(
    *,
    domains: list[str] | None = None,
    max_links_per_source: int = 25,
    on_progress: ProgressCallback | None = None,
) -> dict[str, list[str]]:
    """Fetch list pages for each source and collect article URLs."""
    active = set(active_domain_rules())
    selected = [d for d in (domains or configured_source_domains()) if d in active]
    if not selected:
        return {}
    semaphore = asyncio.Semaphore(DISCOVER_CONCURRENCY)
    discovered: dict[str, list[str]] = {}
    source_total = len(selected)
    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=25,
        follow_redirects=False,
    ) as client:
        tasks = [
            asyncio.create_task(
                _discover_one_domain(
                    client,
                    domain,
                    max_links_per_source=max_links_per_source,
                    semaphore=semaphore,
                ),
                name=f"collect-discover-{domain}",
            )
            for domain in selected
        ]
        completed = 0
        try:
            for finished in asyncio.as_completed(tasks):
                domain, links = await finished
                discovered[domain] = links
                completed += 1
                await _emit_progress(
                    on_progress,
                    stage="discover",
                    message=f"发现源站 {domain}（{len(links)} 篇链接）",
                    source=domain,
                    source_index=completed,
                    source_total=source_total,
                    discovered=sum(len(v) for v in discovered.values()),
                )
        except asyncio.CancelledError:
            # Client abort: cancel sibling discovers before closing the shared client.
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise
    return discovered



_TRANSIENT_HTTP_MARKERS = (
    "status code 408",
    "status code 425",
    "status code 429",
    "status code 500",
    "status code 502",
    "status code 503",
    "status code 504",
)


def _is_transient_fetch_failure(message: str) -> bool:
    """True when a fetch failure is worth retrying once or twice."""
    text = (message or "").strip()
    if not text:
        return True
    lower = text.lower()
    if text.startswith("Network error"):
        return True
    if text.startswith("HTTP error") and any(marker in lower for marker in _TRANSIENT_HTTP_MARKERS):
        return True
    if "timeout" in lower or "timed out" in lower or "temporar" in lower:
        return True
    if text.startswith("Unexpected error") and any(
        token in lower for token in ("timeout", "connect", "reset", "temporarily")
    ):
        return True
    return False


async def _fetch_markdown_with_retries(
    url: str,
    *,
    attempts: int = 3,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Call the URL parser with short backoff on transient failures."""
    delays = (0.35, 0.9, 1.8)
    last = ""
    tries = max(1, int(attempts))
    for attempt in range(tries):
        try:
            if client is None:
                # Reparse one stored Collect article with a short-lived client.
                markdowns = await fetch_and_parse_url([url])
            else:
                markdowns = await fetch_and_parse_url_with_client(client, [url])
            markdown = (markdowns[0] if markdowns else "").strip()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — classify then maybe retry
            markdown = f"Unexpected error for {url}: {exc}"
            logger.warning(
                "collect fetch attempt {}/{} raised for {}: {}",
                attempt + 1,
                tries,
                url,
                exc,
            )
        last = markdown
        if markdown and not markdown.startswith(
            ("HTTP error", "Network error", "Unexpected error", "Content too short", "Restricted access")
        ):
            return markdown
        if attempt + 1 >= tries or not _is_transient_fetch_failure(markdown):
            return markdown
        delay = delays[min(attempt, len(delays) - 1)]
        logger.info(
            "collect fetch retry {}/{} for {} after {:.2f}s ({})",
            attempt + 2,
            tries,
            url,
            delay,
            (markdown or "")[:120],
        )
        await asyncio.sleep(delay)
    return last


async def fetch_article_record(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Parse one URL into a collect_articles row payload.

    Transient network / 5xx / timeout failures are retried with short backoff
    before persisting an error row.
    """
    domain = _domain_of(url)
    now = datetime.now(UTC)
    try:
        markdown = (await _fetch_markdown_with_retries(url, client=client)).strip()
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
                "cve_ids": [],
            }
        title = _title_from_markdown(markdown) or domain
        summary = _summary_from_markdown(markdown)
        return {
            "url": _normalize_url(url) or url,
            "source_domain": domain,
            "title": title,
            "markdown": markdown,
            "summary": summary,
            "status": "ok",
            "error_message": "",
            "fetched_at": now,
            "cve_ids": extract_cve_ids(title, summary, markdown),
        }
    except asyncio.CancelledError:
        raise
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
            "cve_ids": [],
        }


async def crawl_and_persist(
    *,
    domains: list[str] | None = None,
    max_links_per_source: int = 20,
    max_articles_total: int = 80,
    skip_existing: bool = True,
    fetch_concurrency: int = FETCH_CONCURRENCY,
    on_progress: ProgressCallback | None = None,
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
            on_progress=on_progress,
        )


async def _crawl_and_persist_locked(
    *,
    domains: list[str] | None,
    max_links_per_source: int,
    max_articles_total: int,
    skip_existing: bool,
    fetch_concurrency: int,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    await ensure_collect_articles_table()
    await _emit_progress(
        on_progress,
        stage="start",
        message="开始同步源站",
    )
    await _emit_progress(
        on_progress,
        stage="discover",
        message="发现文章链接…",
    )
    discovered = await discover_article_urls(
        domains=domains,
        max_links_per_source=max_links_per_source,
        on_progress=on_progress,
    )
    discovered_total = sum(len(links) for links in discovered.values())
    all_urls = [url for links in discovered.values() for url in links]

    await _emit_progress(
        on_progress,
        stage="select",
        message=f"筛选待抓取链接（发现 {discovered_total}）",
        discovered=discovered_total,
    )
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

    await _emit_progress(
        on_progress,
        stage="select",
        status="completed",
        message=f"将抓取 {len(urls)} 篇（跳过已入库 {skipped}）",
        discovered=discovered_total,
        selected=len(urls),
        skipped_existing=skipped,
    )

    semaphore = asyncio.Semaphore(max(1, int(fetch_concurrency or FETCH_CONCURRENCY)))

    async def _bounded(
        url: str,
        client: httpx.AsyncClient,
    ) -> dict[str, Any]:
        async with semaphore:
            return await fetch_article_record(url, client=client)

    records: list[dict[str, Any]] = []
    fetch_total = len(urls)
    if urls:
        await _emit_progress(
            on_progress,
            stage="fetch",
            message=f"抓取文章 0/{fetch_total}",
            fetched=0,
            selected=fetch_total,
        )
        # A single client is shared across all bounded workers, preserving the
        # URL parser's redirect/SSRF checks while reusing its connection pool.
        async with create_url2md_http_client() as client:
            tasks = [
                asyncio.create_task(
                    _bounded(url, client),
                    name=f"collect-fetch-{index}",
                )
                for index, url in enumerate(urls)
            ]
            done_count = 0
            ok_running = 0
            err_running = 0
            try:
                for finished in asyncio.as_completed(tasks):
                    record = await finished
                    records.append(record)
                    done_count += 1
                    if record.get("status") == "ok":
                        ok_running += 1
                    else:
                        err_running += 1
                    if (
                        fetch_total <= 12
                        or done_count == fetch_total
                        or done_count % 2 == 0
                    ):
                        await _emit_progress(
                            on_progress,
                            stage="fetch",
                            message=f"抓取文章 {done_count}/{fetch_total}",
                            fetched=done_count,
                            selected=fetch_total,
                            ok=ok_running,
                            error=err_running,
                        )
            except asyncio.CancelledError:
                # Client abort / worker cancel: stop sibling fetches so lock can release.
                for task in tasks:
                    if not task.done():
                        task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise

    ok = sum(1 for record in records if record.get("status") == "ok")
    err = len(records) - ok
    await _emit_progress(
        on_progress,
        stage="database",
        message=f"写入数据库（成功 {ok}，失败 {err}）",
        ok=ok,
        error=err,
        selected=len(urls),
    )
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
    }
    await _emit_progress(
        on_progress,
        stage="done",
        status="completed",
        message=(
            f"同步完成：发现 {discovered_total}，抓取 {len(urls)}，"
            f"成功 {ok}，写入 {saved}"
        ),
        **stats,
    )
    logger.info("collect crawl finished: {}", stats)
    return stats


async def refresh_collect_article_url(url: str) -> dict[str, Any]:
    """Re-fetch and persist one URL that already belongs to the Collect library."""
    from api.persistence.collect_articles import upsert_collect_article

    await ensure_collect_articles_table()
    record = await fetch_article_record(url)
    stored = await upsert_collect_article(record)
    return {**stored, "saved": True}
