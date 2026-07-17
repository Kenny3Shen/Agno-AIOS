"""Collect content-domain rules and host normalization helpers.

``domain_rules`` maps hostname → (body CSS class, skip classes, truncate marker).
Parsing falls back to semantic containers (article/main) when a rule misses or
yields a too-short body. Disabled domains are never offered as crawl sources.
"""

from __future__ import annotations

domain_rules: dict[str, tuple[str, list[str], str]] = {

    "cybersecuritynews.com": (
        "td-post-content tagdiv-type",
        ["has-text-align-center has-background"],
        "",
    ),
    "www.redhotcyber.com": ("elementor-shortcode", ["tag-list", "table"], ""),
    "dailydarkweb.net": ("entry-content no-share", [], ""),
    "securityonline.info": ("entry-content read-details", [], "Related Posts"),
    "hackread.com": ("entry-content", [], ""),

    "www.csoonline.com": ("article__main", [], ""),
    "securityaffairs.com": (
        "row",
        ["common-heading line-bottom article-title mb-3 wow fadeInUp animated"],
        "Follow me on Twitter",
    ),
    "www.anquanke.com": ("content", [], ""),
    "www.freebuf.com": ("content-detail", [], "参考来源："),
    "www.seqrite.com": ("single-post-content", [], ""),
    "mp.weixin.qq.com": ("rich_media_wrp", [], ""),
    "thecyberexpress.com": ("entry-content no-share", [], "Share this:"),
    "thehackernews.com": ("articlebody clear cf", [], ""),
    "xlab.tencent.com": ("post-content", [], ""),

    # Expanded security intel sources (www/bare aliases resolved via host candidates)
    "www.bleepingcomputer.com": ("articleBody", [], "Related Articles"),
    "krebsonsecurity.com": ("entry-content", [], "Related Posts"),
    "www.securityweek.com": ("zox-post-body", ["zox-post-share"], ""),
    "www.darkreading.com": ("ArticleBase-Body", [], ""),
    "therecord.media": ("article-content", [], ""),
    "unit42.paloaltonetworks.com": ("article__content", [], ""),
    "blog.cloudflare.com": ("post-content", [], ""),
}
DISABLED_COLLECT_DOMAINS: frozenset[str] = frozenset(
    {
        "botcrawl.com",
        "go.theregister.com",
        "www.securitylab.ru",
        "theregister.com",
        "www.theregister.com",
        "securitylab.ru",
    }
)


def normalize_content_host(host: str | None) -> str:
    """Lowercase hostname without port or trailing dot."""
    value = (host or "").strip().lower().rstrip(".")
    if not value:
        return ""
    # Strip brackets from IPv6 literals if present
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return value


def content_host_candidates(host: str | None) -> list[str]:
    """Ordered host keys to try against domain_rules (exact, www strip/add)."""
    base = normalize_content_host(host)
    if not base:
        return []
    candidates: list[str] = [base]
    if base.startswith("www."):
        bare = base[4:]
        if bare and bare not in candidates:
            candidates.append(bare)
    else:
        www = f"www.{base}"
        if www not in candidates:
            candidates.append(www)
    return candidates


def resolve_domain_rule_key(url: str) -> str | None:
    """Map a page URL to a domain_rules key, or None if no rule applies."""
    from urllib.parse import urlsplit

    host = normalize_content_host(urlsplit(url).hostname)
    if not host or host in DISABLED_COLLECT_DOMAINS:
        # Still allow parse if a non-disabled rule matches via candidates
        pass
    for key in content_host_candidates(host):
        if key in DISABLED_COLLECT_DOMAINS:
            continue
        if key in domain_rules:
            return key
    # Suffix / parent match (m.example.com → example.com rule)
    for rule_key in domain_rules:
        if rule_key in DISABLED_COLLECT_DOMAINS:
            continue
        if host == rule_key or host.endswith("." + rule_key) or rule_key.endswith("." + host):
            return rule_key
    return None


def active_domain_rules() -> dict[str, tuple[str, list[str], str]]:
    """domain_rules minus intentionally disabled Collect sources."""
    return {
        key: value
        for key, value in domain_rules.items()
        if key not in DISABLED_COLLECT_DOMAINS
        and not any(key == d or key.endswith("." + d) or d.endswith("." + key) for d in DISABLED_COLLECT_DOMAINS)
    }

# 需要从标题中移除的后缀
title_suffixes = ["-安全KER - 安全资讯平台", " - FreeBuf网络安全行业门户"]
