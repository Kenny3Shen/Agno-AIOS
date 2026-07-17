"""Domain rule resolution and multi-class content extraction."""

from __future__ import annotations

from bs4 import BeautifulSoup

from api.services.url2md_service import (
    _find_content_container,
    _find_generic_content_container,
    get_markdown_text,
)
from api.services.collect_crawl_service import configured_source_domains
from api.utils.url2md_utils import (
    DISABLED_COLLECT_DOMAINS,
    active_domain_rules,
    content_host_candidates,
    domain_rules,
    resolve_domain_rule_key,
)


def test_disabled_sources_not_in_active_rules():
    assert "botcrawl.com" not in domain_rules
    assert "go.theregister.com" not in domain_rules
    assert "www.securitylab.ru" not in domain_rules
    for domain in ("botcrawl.com", "go.theregister.com", "www.securitylab.ru"):
        assert domain not in active_domain_rules()
        assert domain not in configured_source_domains()


def test_configured_sources_match_active_rules():
    assert set(configured_source_domains()) == set(active_domain_rules().keys())
    assert "cybersecuritynews.com" in configured_source_domains()
    assert "dailydarkweb.net" in configured_source_domains()


def test_content_host_candidates_strips_www():
    assert content_host_candidates("www.cybersecuritynews.com")[0] == "www.cybersecuritynews.com"
    assert "cybersecuritynews.com" in content_host_candidates("www.cybersecuritynews.com")
    assert "www.dailydarkweb.net" in content_host_candidates("dailydarkweb.net")


def test_resolve_domain_rule_key_aliases():
    assert resolve_domain_rule_key("https://cybersecuritynews.com/some-post/") == "cybersecuritynews.com"
    assert (
        resolve_domain_rule_key("https://www.cybersecuritynews.com/some-post/")
        == "cybersecuritynews.com"
    )
    assert resolve_domain_rule_key("https://dailydarkweb.net/post/") == "dailydarkweb.net"
    assert resolve_domain_rule_key("https://www.dailydarkweb.net/post/") == "dailydarkweb.net"
    assert resolve_domain_rule_key("https://thehackernews.com/2024/01/x.html") == "thehackernews.com"
    assert resolve_domain_rule_key("https://unknown-news.example/a") is None


def test_resolve_skips_disabled_hosts():
    for host in ("botcrawl.com", "www.botcrawl.com", "go.theregister.com", "www.securitylab.ru"):
        assert resolve_domain_rule_key(f"https://{host}/article") is None
    # DISABLED set documents intentional skips
    assert "botcrawl.com" in DISABLED_COLLECT_DOMAINS


def test_find_content_container_multi_class():
    html = """
    <html><body>
      <div class="td-post-content tagdiv-type">
        <p>""" + ("Security research content. " * 20) + """</p>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    container = _find_content_container(soup, "td-post-content tagdiv-type")
    assert container is not None
    assert "Security research" in container.get_text()


def test_get_markdown_text_uses_multi_class_rule():
    body = ("Detailed threat analysis paragraph with enough length. " * 8)
    html = f"""
    <html><head><title>CN Sample CVE Report</title></head>
    <body>
      <div class="td-post-content tagdiv-type">
        <p>{body}</p>
        <p>{body}</p>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    md = get_markdown_text(soup, "https://www.cybersecuritynews.com/sample-cve/")
    assert md.startswith("# CN Sample CVE Report")
    assert "threat analysis" in md


def test_get_markdown_text_dailydarkweb_multi_class():
    body = ("Dark web marketplace report with enough characters. " * 8)
    html = f"""
    <html><head><title>DDW Leak Notice</title></head>
    <body>
      <div class="entry-content no-share">
        <p>{body}</p>
        <p>{body}</p>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    md = get_markdown_text(soup, "https://dailydarkweb.net/leak-notice/")
    assert md.startswith("# DDW Leak Notice")
    assert "marketplace report" in md



def test_find_generic_content_container_prefers_article():
    body = ("Incident response notes with enough characters for extract. " * 8)
    html = f"""
    <html><body>
      <nav class="menu">Home About</nav>
      <article>
        <h1>Generic Post</h1>
        <p>{body}</p>
        <p>{body}</p>
      </article>
      <aside class="sidebar related">More stories</aside>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    container = _find_generic_content_container(soup)
    assert container is not None
    assert container.name == "article"
    assert "Incident response" in container.get_text()


def test_get_markdown_text_generic_article_fallback():
    """Unknown domain still extracts from semantic article containers."""
    body = ("Vendor advisory detail with sufficient length for markdown. " * 8)
    html = f"""
    <html><head><title>Unknown Source Advisory</title></head>
    <body>
      <header>Site chrome</header>
      <article class="post">
        <p>{body}</p>
        <p>{body}</p>
      </article>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    md = get_markdown_text(soup, "https://unknown-news.example/a/post")
    assert md.startswith("# Unknown Source Advisory")
    assert "Vendor advisory" in md


def test_get_markdown_text_falls_back_when_domain_class_missing():
    """Configured domain whose CMS class drifted still recovers via generic selectors."""
    body = ("Class drift recovery paragraph with enough text content. " * 8)
    html = f"""
    <html><head><title>THN Drifted Markup</title></head>
    <body>
      <div class="entry-content">
        <p>{body}</p>
        <p>{body}</p>
      </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    # thehackernews rule expects articlebody clear cf — missing here.
    md = get_markdown_text(soup, "https://thehackernews.com/2024/01/example.html")
    assert md.startswith("# THN Drifted Markup")
    assert "Class drift recovery" in md



def test_get_markdown_text_returns_empty_when_no_usable_body():
    html = "<html><head><title>Empty</title></head><body><nav>only nav</nav></body></html>"
    soup = BeautifulSoup(html, "html.parser")
    assert get_markdown_text(soup, "https://unknown-news.example/empty") == ""


def test_find_content_container_accepts_article_tag():
    """Class rules should match semantic article tags, not only div."""
    body = "Security research content with enough length. " * 10
    html = f"""
    <html><body>
      <article class="td-post-content tagdiv-type">
        <p>{body}</p>
      </article>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    container = _find_content_container(soup, "td-post-content tagdiv-type")
    assert container is not None
    assert container.name == "article"
    assert "Security research" in container.get_text()


def test_get_markdown_text_domain_rule_on_article_tag():
    body = ("Threat analysis on article tag with enough length. " * 8)
    html = f"""
    <html><head><title>Article Tag CVE</title></head>
    <body>
      <article class="td-post-content tagdiv-type">
        <p>{body}</p>
        <p>{body}</p>
      </article>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    md = get_markdown_text(soup, "https://cybersecuritynews.com/article-tag/")
    assert md.startswith("# Article Tag CVE")
    assert "Threat analysis" in md



def test_get_markdown_text_retries_generic_when_domain_body_too_short():
    """Domain class may match a teaser; prefer longer generic article body."""
    teaser = "Short teaser."
    body = ("Full incident write-up with enough characters for extract. " * 8)
    html = f"""
    <html><head><title>Teaser vs Body</title></head>
    <body>
      <div class="articlebody clear cf"><p>{teaser}</p></div>
      <article class="entry-content">
        <p>{body}</p>
        <p>{body}</p>
      </article>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    # thehackernews rule matches articlebody clear cf (short teaser only)
    md = get_markdown_text(soup, "https://thehackernews.com/2024/01/teaser.html")
    assert md.startswith("# Teaser vs Body")
    assert "Full incident write-up" in md
    assert "Short teaser" not in md or "Full incident" in md
