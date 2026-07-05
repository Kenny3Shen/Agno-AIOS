import importlib
import re

import httpx
from bs4 import BeautifulSoup
from api.utils.url2md_utils import domain_rules, title_suffixes

USE_PLAYWRIGHT = False  # 是否使用 Playwright 绕过 WAF


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


def get_markdown_text(soup: BeautifulSoup, url: str) -> str:
    """
    从 HTML 中提取标题和主要文本内容，转换为 Markdown 格式。

    Args:
        soup: BeautifulSoup 对象
        url: 页面 URL，用于匹配域名规则

    Returns:
        包含标题和正文的 Markdown 格式文本
    """
    # 提取标题
    title = _get_title_text(soup)
    tags_to_extract = ["h2", "h3", "p", "strong", "li", "table", "code"]

    domain_pattern = re.compile(r"https?://([^/]+)/")
    match = domain_pattern.search(url)
    domain = match.group(1) if match else ""
    container = None
    truncate_marker = ""  # 截断标记

    if domain in domain_rules:
        rule = domain_rules[domain]
        main_class_name, exclude_classes, truncate_marker = rule[0], rule[1], rule[2]
        container = soup.find("div", class_=main_class_name)

    if container:
        # 排除不需要的标签
        for exclude_class in exclude_classes:
            for elem in container.find_all(class_=exclude_class):
                elem.decompose()
        if domain == "www.anquanke.com":
            tags_to_extract.append("div")
        elements = container.find_all(tags_to_extract)
    # 未设置规则时，仅提取 <p> 标签
    else:
        print(f"Rules not found for domain: {domain}")
        elements = soup.find_all(["p"])

    # 使用提取函数转换为 Markdown，跳过与标题相同的标签
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
        follow_redirects=True,
    ) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                body = resp.text
                waf_features = [
                    "aliyun_waf",
                ]
                waf_blocked = any(feature in body.lower() for feature in waf_features)
                # 如果被 WAF 拦截，使用 patchright 获取
                if waf_blocked and USE_PLAYWRIGHT:
                    body = await _fetch_with_playwright(url)

                # 检查状态码（WAF 绕过后不再检查原始状态码）
                if not waf_blocked and resp.status_code != 200:
                    results.append(f"HTTP error for {url}: status code {resp.status_code}")
                    continue

                soup = BeautifulSoup(body, "html.parser")

                if len(soup.get_text()) < 500:
                    results.append(f"Content too short for {url}: page may be inaccessible")
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
                        f"Restricted access for {url}: page requires special permissions"
                    )
                    continue

                markdown_text = get_markdown_text(soup, url)

                results.append(markdown_text)

            except httpx.HTTPError as e:
                results.append(f"Network error for {url}: {e}")
                continue
            except Exception as e:
                results.append(f"Unexpected error for {url}: {e}")
                continue

    return results
