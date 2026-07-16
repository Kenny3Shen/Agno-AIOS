from api.services.collect_crawl_service import (
    _looks_like_article,
    _summary_from_markdown,
    _title_from_markdown,
    configured_source_domains,
    extract_article_links,
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


def test_title_and_summary_from_markdown():
    md = "# Sample Title\n\nFirst paragraph with enough text.\n\nSecond line."
    assert _title_from_markdown(md) == "Sample Title"
    assert "First paragraph" in _summary_from_markdown(md)
