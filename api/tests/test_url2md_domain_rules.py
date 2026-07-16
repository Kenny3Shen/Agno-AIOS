"""Domain rule resolution and multi-class content extraction."""

from __future__ import annotations

from bs4 import BeautifulSoup

from api.services.url2md_service import (
    _find_content_container,
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
