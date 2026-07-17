import importlib
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import anyio
import httpx
from bs4 import BeautifulSoup
from api.utils.url2md_utils import (
    domain_rules,
    resolve_domain_rule_key,
    title_suffixes,
)
from loguru import logger

USE_PLAYWRIGHT = False  # 是否使用 Playwright 绕过 WAF
MAX_REDIRECTS = 5


class UnsafeUrlError(ValueError):
    """Raised when a URL could access a non-public network address."""


async def _resolve_public_host(hostname: str, port: int | None) -> None:
    """Require every address returned for *hostname* to be globally routable.

    Checking every answer (rather than accepting one public answer) avoids a
    hostname with mixed public/private DNS records selecting an internal
    address.  It also rejects literal IP addresses before making a request.
    """
    try:
        addresses = await anyio.getaddrinfo(
            hostname,
            port or 443,
            type=socket.SOCK_STREAM,
        )
    except socket.gaierror as exc:
        raise UnsafeUrlError("URL host cannot be resolved") from exc

    if not addresses:
        raise UnsafeUrlError("URL host cannot be resolved")
    for _family, _type, _proto, _canonname, sockaddr in addresses:
        address = ipaddress.ip_address(sockaddr[0])
        if not address.is_global:
            raise UnsafeUrlError("URL host must resolve only to public IP addresses")


async def validate_public_http_url(url: str) -> str:
    """Validate an outbound URL before each request, including redirects."""
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise UnsafeUrlError("URL scheme must be http or https")
    if parsed.username is not None or parsed.password is not None:
        raise UnsafeUrlError("URL credentials are not allowed")
    if not parsed.hostname:
        raise UnsafeUrlError("URL must include a host")
    try:
        port = parsed.port
    except ValueError as exc:
        raise UnsafeUrlError("URL port is invalid") from exc
    await _resolve_public_host(parsed.hostname, port)
    return url


async def _get_public_url(client: httpx.AsyncClient, url: str) -> httpx.Response:
    """Fetch a URL without allowing httpx to follow unchecked redirects."""
    current_url = await validate_public_http_url(url)
    for _ in range(MAX_REDIRECTS + 1):
        response = await client.get(current_url, follow_redirects=False)
        if response.status_code not in {301, 302, 303, 307, 308}:
            return response
        location = response.headers.get("location")
        if not location:
            return response
        await response.aclose()
        current_url = await validate_public_http_url(urljoin(current_url, location))
    raise UnsafeUrlError(f"URL exceeded the maximum of {MAX_REDIRECTS} redirects")


def _get_title_text(soup: BeautifulSoup) -> str:
    """提取页面标题的纯文本"""
    title = None
    if soup.title:
        title = soup.title.get_text(strip=True)
    if not title:
        h1 = soup.find("h1")
        title = h1.get_text(strip=True) if h1 else "No Title"

    for suffix in title_suffixes:
        if title.endswith(suffix):
            title = title[: -len(suffix)].strip()
            break

    return title


def _table_to_markdown(table_tag) -> str:
    """将 HTML table 转换为 Markdown 表格"""
    rows = table_tag.find_all("tr")
    if not rows:
        return ""

    md_lines = []
    for i, row in enumerate(rows):
        cells = row.find_all(["th", "td"])
        cell_texts = [cell.get_text(strip=True).replace("|", "\\|") for cell in cells]

        if not cell_texts:
            continue

        md_lines.append("| " + " | ".join(cell_texts) + " |")

        # 在第一行（表头）后添加分隔符 |---|---|
        if i == 0:
            md_lines.append("| " + " | ".join(["---"] * len(cell_texts)) + " |")

    return "\n".join(md_lines)


def parse_to_markdown(elements, truncate_marker: str = "", skip_title: str = "") -> str:
    """
    将 HTML 元素列表转换为 Markdown 格式文本。

    Args:
        elements: BeautifulSoup 元素列表
        truncate_marker: 截断标记，遇到包含该文本的元素时停止提取
        skip_title: 跳过与此标题相同的标签（避免重复）

    Returns:
        Markdown 格式文本
    """
    element_set = set(elements)
    markdown_lines = []
    prev_tag_name = None

    for tag in elements:
        # Avoid duplicates: skip if parent is also in the selected elements
        if set(tag.parents) & element_set:
            continue

        # 使用 separator=" " 保留内联元素（如 <a>）之间的空格
        text = tag.get_text(separator=" ", strip=True)
        # 压缩连续空格为单个空格
        text = re.sub(r"\s+", " ", text).strip()

        if not text:
            continue

        # 跳过与标题相同的标签（避免重复标题）
        if skip_title and text == skip_title:
            continue

        # 检查截断标记：如果遇到包含截断文本的元素，停止提取
        if truncate_marker and truncate_marker in text:
            break

        if tag.name == "h2":
            text = f"\n## {text}\n\n"
        elif tag.name == "h3":
            text = f"\n### {text}\n\n"
        elif tag.name == "p":
            if prev_tag_name == "li":
                text = f"\n{text}\n"
            else:
                text = f"{text}\n\n"
        elif tag.name == "strong":
            text = f"**{text}**"
        elif tag.name == "li":
            text = f"- {text}\n"
        elif tag.name == "table":
            text = f"\n{_table_to_markdown(tag)}\n\n"
        elif tag.name == "code":
            if tag.parent and tag.parent.name == "pre":
                text = f"\n```\n{text}\n```\n\n"
            else:
                text = f"`{text}`"
        elif tag.name == "div":
            text = f"{text}\n\n"

        markdown_lines.append(text)
        prev_tag_name = tag.name

    return "".join(markdown_lines).strip()


def _class_tokens(class_spec: str) -> list[str]:
    """Split a space-separated HTML class list into tokens for BS4 matching."""
    return [part for part in (class_spec or "").split() if part]


def _class_set(value: object) -> set[str]:
    """Normalize BS4 class attribute (str | list | None) to a token set."""
    if value is None or value is False:
        return set()
    if isinstance(value, str):
        return {part for part in value.split() if part}
    if isinstance(value, (list, tuple, set)):
        return {str(part) for part in value if part}
    return {str(value)}


def _find_content_container(soup: BeautifulSoup, main_class_name: str):
    """Locate the article body div using multi-class-safe matching."""
    tokens = _class_tokens(main_class_name)
    if not tokens:
        return None
    if len(tokens) == 1:
        return soup.find("div", class_=tokens[0])
    # Multi-class: require all tokens present on the same element
    return soup.find(
        "div",
        class_=lambda value, t=tokens: bool(value) and set(t).issubset(_class_set(value)),
    )


# Prefer semantic / CMS body containers when domain rules miss or class drifts.
_GENERIC_CONTAINER_SELECTORS: tuple[str, ...] = (
    "article",
    "main",
    "[role=main]",
    ".post-content",
    ".entry-content",
    ".article-content",
    ".article-body",
    ".td-post-content",
    ".content-detail",
    ".single-post-content",
    "#content",
    ".content",
)

_GENERIC_NOISE_CLASS_HINTS = frozenset(
    {
        "nav",
        "menu",
        "sidebar",
        "footer",
        "header",
        "comment",
        "share",
        "related",
        "breadcrumb",
        "widget",
        "promo",
        "advert",
        "cookie",
    }
)


def _element_text_len(node) -> int:
    if node is None:
        return 0
    return len(node.get_text(" ", strip=True) or "")


def _looks_like_noise_container(node) -> bool:
    classes = {part.lower() for part in _class_set(node.get("class"))}
    node_id = str(node.get("id") or "").lower()
    haystack = " ".join(classes | ({node_id} if node_id else set()))
    return any(token in haystack for token in _GENERIC_NOISE_CLASS_HINTS)


def _find_generic_content_container(soup: BeautifulSoup):
    """Best-effort article body when domain rule is missing or container drifted.

    Scores candidates by visible text length and prefers semantic tags
    (``article`` / ``main``) over generic ``div`` dumps.
    """
    candidates: list[tuple[int, int, object]] = []
    seen: set[int] = set()
    for index, selector in enumerate(_GENERIC_CONTAINER_SELECTORS):
        try:
            matches = soup.select(selector)
        except Exception:  # noqa: BLE001 — bad selector should not break parse
            continue
        for node in matches:
            if id(node) in seen:
                continue
            seen.add(id(node))
            if _looks_like_noise_container(node):
                continue
            length = _element_text_len(node)
            if length < 200:
                continue
            # Prefer earlier (more specific) selectors slightly.
            score = length * 10 - index
            if getattr(node, "name", None) in {"article", "main"}:
                score += 500
            candidates.append((score, length, node))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][2]


def _exclude_by_class(container, exclude_classes: list[str]) -> None:
    for exclude_class in exclude_classes:
        tokens = _class_tokens(exclude_class)
        if not tokens:
            continue
        if len(tokens) == 1:
            for elem in container.find_all(class_=tokens[0]):
                elem.decompose()
            continue
        for elem in container.find_all(
            class_=lambda value, t=tokens: bool(value) and set(t).issubset(_class_set(value))
        ):
            elem.decompose()


def get_markdown_text(soup: BeautifulSoup, url: str) -> str:
    """
    从 HTML 中提取标题和主要文本内容，转换为 Markdown 格式。

    Args:
        soup: BeautifulSoup 对象
        url: 页面 URL，用于匹配域名规则

    Returns:
        包含标题和正文的 Markdown 格式文本
    """
    title = _get_title_text(soup)
    tags_to_extract = ["h2", "h3", "p", "strong", "li", "table", "code"]

    domain_key = resolve_domain_rule_key(url)
    container = None
    truncate_marker = ""
    exclude_classes: list[str] = []

    if domain_key:
        main_class_name, exclude_classes, truncate_marker = domain_rules[domain_key]
        container = _find_content_container(soup, main_class_name)
        if container is None:
            logger.debug(
                "Content container not found for domain={} url={} class={!r}",
                domain_key,
                url,
                main_class_name,
            )
    else:
        host = (urlsplit(url).hostname or "").lower()
        logger.debug("Rules not found for domain: {} url={}", host, url)

    if container is None:
        container = _find_generic_content_container(soup)
        if container is not None:
            logger.debug(
                "Using generic content container tag={} classes={} url={}",
                getattr(container, "name", "?"),
                container.get("class"),
                url,
            )

    if container is not None:
        _exclude_by_class(container, exclude_classes)
        if domain_key == "www.anquanke.com":
            tags_to_extract.append("div")
        elements = container.find_all(tags_to_extract)
    else:
        # Last resort: whole-document paragraphs (noisy but better than empty).
        elements = soup.find_all(["p", "li", "h2", "h3"])

    main_paragraphs = parse_to_markdown(elements, truncate_marker, title)

    if len(main_paragraphs) < 200:
        return ""
    if len(main_paragraphs) > 5000:
        main_paragraphs = main_paragraphs[:5000]

    return f"# {title}\n\n{main_paragraphs}"


async def _fetch_with_playwright(url: str) -> str:
    try:
        async_playwright = importlib.import_module("patchright.async_api").async_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("patchright is required when USE_PLAYWRIGHT is enabled") from exc

    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir="/home/shenss/.config/patchright-chrome",
            channel="chrome",
            headless=False,
            no_viewport=True,
        )
        try:
            page = context.pages[0] if context.pages else await context.new_page()
            await page.goto(url)
            await page.wait_for_timeout(5000)
            return await page.content()
        finally:
            await context.close()


async def fetch_and_parse_url(urls: list[str]) -> list[str]:
    """
    使用 async HTTP client 获取 URL 内容，检测 WAF 拦截时可使用 async browser fallback。

    Args:
        urls: URL 列表

    Returns:
        解析后的 Markdown 文本列表
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36 Edg/142.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7",
        "Accept-Encoding": "gzip, deflate",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1",
        "Cache-Control": "max-age=0",
    }

    results = []

    async with httpx.AsyncClient(
        headers=headers,
        timeout=30,
        follow_redirects=False,
    ) as client:
        for url in urls:
            try:
                resp = await _get_public_url(client, url)
                fetched_url = str(resp.url)
                body = resp.text
                waf_features = [
                    "aliyun_waf",
                ]
                waf_blocked = any(feature in body.lower() for feature in waf_features)
                # 如果被 WAF 拦截，使用 patchright 获取
                if waf_blocked and USE_PLAYWRIGHT:
                    body = await _fetch_with_playwright(fetched_url)

                # 检查状态码（WAF 绕过后不再检查原始状态码）
                if not waf_blocked and resp.status_code != 200:
                    results.append(f"HTTP error for {fetched_url}: status code {resp.status_code}")
                    continue

                soup = BeautifulSoup(body, "html.parser")

                if len(soup.get_text()) < 500:
                    results.append(f"Content too short for {fetched_url}: page may be inaccessible")
                    continue

                tags_to_remove = [
                    "header",
                    "footer",
                    "nav",
                    "aside",
                    "script",
                    "style",
                    "form",
                    "iframe",
                ]

                for tag_name in tags_to_remove:
                    for tag in soup.find_all(tag_name):
                        tag.decompose()

                text = soup.get_text(separator="\n", strip=True)
                restricted_markers = [
                    "access to this vulnerability report requires support",
                    "verified supporters only",
                    "请进行验证",
                ]
                lowered = text.lower()
                if any(marker in lowered for marker in restricted_markers):
                    results.append(
                        f"Restricted access for {fetched_url}: page requires special permissions"
                    )
                    continue

                markdown_text = get_markdown_text(soup, fetched_url)

                results.append(markdown_text)

            except httpx.HTTPError as e:
                results.append(f"Network error for {url}: {e}")
                continue
            except Exception as e:
                results.append(f"Unexpected error for {url}: {e}")
                continue

    return results
