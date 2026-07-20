import pytest

from api.services.collect_crawl_service import (
    _looks_like_article,
    _summary_from_markdown,
    _title_from_markdown,
    configured_source_domains,
    extract_article_links,
    extract_list_page_links,
    _list_page_seed_urls,
    _is_transient_fetch_failure,
    select_urls_round_robin,
)
from api.utils.url2md_utils import active_domain_rules


def test_configured_sources_match_domain_rules():
    domains = configured_source_domains()
    assert domains
    assert set(domains) == set(active_domain_rules().keys())
    assert "botcrawl.com" not in domains
    assert "go.theregister.com" not in domains
    assert "www.securitylab.ru" not in domains


def test_looks_like_article_filters_noise():
    assert _looks_like_article(
        "https://thehackernews.com/2024/01/example-threat-report.html",
        "thehackernews.com",
    )
    assert not _looks_like_article(
        "https://thehackernews.com/tag/malware/",
        "thehackernews.com",
    )
    assert not _looks_like_article(
        "https://evil.example/post",
        "thehackernews.com",
    )


@pytest.mark.parametrize(
    ("url", "source_domain", "expected"),
    [
        ("https://hackread.com/submit-press-release/", "hackread.com", False),
        ("https://therecord.media/news/leadership", "therecord.media", False),
        ("https://therecord.media/news/cybercrime", "therecord.media", False),
        ("https://therecord.media/news/nation-state", "therecord.media", False),
        (
            "https://therecord.media/news/influence-operations",
            "therecord.media",
            False,
        ),
        ("https://therecord.media/news/technology", "therecord.media", False),
        (
            "https://therecord.media/a-long-security-news-story",
            "therecord.media",
            True,
        ),
        ("https://thehackernews.com/expert-insights/", "thehackernews.com", False),
        (
            "https://thehackernews.com/p/upcoming-hacker-news-webinars.html",
            "thehackernews.com",
            False,
        ),
        (
            "https://thehackernews.com/expert-insights/2026/07/a-real-story.html",
            "thehackernews.com",
            True,
        ),
        ("https://xlab.tencent.com/en/about/", "xlab.tencent.com", False),
        ("https://xlab.tencent.com/en/policy/", "xlab.tencent.com", False),
        ("https://xlab.tencent.com/en/archives/2026/07", "xlab.tencent.com", False),
        (
            "https://xlab.tencent.com/en/2026/07/17/a-real-post",
            "xlab.tencent.com",
            True,
        ),
    ],
)
def test_looks_like_article_applies_source_path_policy(
    url: str,
    source_domain: str,
    expected: bool,
):
    assert _looks_like_article(url, source_domain) is expected


def test_extract_article_links_from_list_html():
    html = """
    <html><body>
      <a href="/2024/05/serious-bug-found.html">A</a>
      <a href="/tag/cve/">Tag</a>
      <a href="https://thehackernews.com/2024/05/other-story.html">B</a>
    </body></html>
    """
    links = extract_article_links(html, "https://thehackernews.com/", "thehackernews.com")
    assert any("serious-bug-found" in link for link in links)
    assert all("/tag/" not in link for link in links)


def test_extract_article_links_skips_navigation_chrome():
    html = """
    <html><body>
      <header class="site-header">
        <a href="/another-long-security-story">Navigation story-like link</a>
      </header>
      <div role="navigation">
        <a href="/role-navigation-security-story">Role navigation link</a>
      </div>
      <article>
        <header>
          <a href="/a-real-long-security-story">Article</a>
        </header>
      </article>
    </body></html>
    """
    links = extract_article_links(html, "https://hackread.com/", "hackread.com")
    assert links == ["https://hackread.com/a-real-long-security-story"]


def test_title_and_summary_from_markdown():
    md = "# Sample Title\n\nFirst paragraph with enough text.\n\nSecond line."
    assert _title_from_markdown(md) == "Sample Title"
    assert "First paragraph" in _summary_from_markdown(md)


def test_select_urls_round_robin_fairness():
    discovered = {
        "aaa.example": [f"https://aaa.example/a{i}" for i in range(10)],
        "zzz.example": [f"https://zzz.example/z{i}" for i in range(10)],
    }
    selected = select_urls_round_robin(discovered, max_articles_total=4)
    assert len(selected) == 4
    # Alphabetical concat would take only aaa.*; round-robin must interleave.
    assert any("zzz.example" in url for url in selected)
    assert any("aaa.example" in url for url in selected)


def test_select_urls_round_robin_excludes_existing_before_budget():
    discovered = {
        "aaa.example": [
            "https://aaa.example/old-1",
            "https://aaa.example/old-2",
            "https://aaa.example/new-1",
        ],
        "zzz.example": [
            "https://zzz.example/old-z",
            "https://zzz.example/new-z",
        ],
    }
    existing = {
        "https://aaa.example/old-1",
        "https://aaa.example/old-2",
        "https://zzz.example/old-z",
    }
    selected = select_urls_round_robin(
        discovered,
        max_articles_total=2,
        exclude=existing,
    )
    assert selected == [
        "https://aaa.example/new-1",
        "https://zzz.example/new-z",
    ]


def test_select_urls_round_robin_empty_when_all_existing():
    discovered = {"a.com": ["https://a.com/1"]}
    selected = select_urls_round_robin(
        discovered,
        max_articles_total=10,
        exclude={"https://a.com/1"},
    )
    assert selected == []


def test_transient_fetch_failure_classifier():
    assert _is_transient_fetch_failure("Network error for https://x: timeout")
    assert _is_transient_fetch_failure("HTTP error for https://x: status code 503")
    assert _is_transient_fetch_failure("Unexpected error for https://x: connect timeout")
    assert not _is_transient_fetch_failure("Content too short for https://x")
    assert not _is_transient_fetch_failure("HTTP error for https://x: status code 404")
    assert not _is_transient_fetch_failure("Restricted access")


def test_list_page_seed_urls_builds_pagination():
    seeds = _list_page_seed_urls("https://thehackernews.com/", max_pages=3)
    assert seeds == [
        "https://thehackernews.com/page/2/",
        "https://thehackernews.com/page/3/",
    ]


def test_extract_list_page_links_finds_next_and_page():
    html = """
    <html><body>
      <a href="/page/2/">Next</a>
      <a rel="next" href="https://thehackernews.com/page/3/">older</a>
      <a href="/2024/05/serious-bug-found.html">Article</a>
    </body></html>
    """
    links = extract_list_page_links(html, "https://thehackernews.com/", "thehackernews.com")
    assert any("/page/2" in link for link in links)
    assert any("/page/3" in link for link in links)
    assert all("serious-bug" not in link for link in links)



def test_discover_filters_inactive_and_unknown_domains():
    """Unknown/disabled domains must not be crawled (returns empty without HTTP)."""
    import asyncio

    from api.services.collect_crawl_service import discover_article_urls

    result = asyncio.run(
        discover_article_urls(
            domains=["botcrawl.com", "not-a-real-source.example"],
            max_links_per_source=5,
        )
    )
    assert result == {}
