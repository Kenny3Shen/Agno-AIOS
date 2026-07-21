"""Unit tests for P1 inject-side memory ranking."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from api.services.memory_inject_service import (
    MemoryInjectConfig,
    score_memory_for_inject,
    select_memories_for_inject,
    tokenize_for_memory_match,
)


def _mem(
    memory_id: str,
    text: str,
    *,
    days_ago: float = 1,
    topics: list[str] | None = None,
    now: datetime | None = None,
) -> SimpleNamespace:
    wall = now or datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    updated = wall - timedelta(days=days_ago)
    return SimpleNamespace(
        memory_id=memory_id,
        memory=text,
        topics=topics or [],
        updated_at=int(updated.timestamp()),
        created_at=int(updated.timestamp()),
        user_id="u1",
    )


def test_tokenize_keeps_cjk_and_latin() -> None:
    tokens = tokenize_for_memory_match("用户 prefers Chinese 报告 CVE-2024-1234")
    assert "用户" in tokens or any("用" in t for t in tokens)
    assert "prefers" in tokens or "chinese" in tokens
    assert "cve-2024-1234" in tokens or "2024" in tokens


def test_score_prefers_keyword_overlap() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    query = tokenize_for_memory_match("containment playbook for ransomware")
    relevant = score_memory_for_inject(
        _mem(
            "a",
            "User prefers the ransomware containment playbook with high severity.",
            topics=["containment"],
            now=now,
        ),
        query_tokens=query,
        now=now,
    )
    unrelated = score_memory_for_inject(
        _mem("b", "User likes blue UI themes.", topics=["ui"], now=now),
        query_tokens=query,
        now=now,
    )
    assert relevant > unrelated


def test_score_has_no_quality_length_bias_without_query() -> None:
    """Without a query, ranking is recency-only (no content-length quality term)."""
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    short = score_memory_for_inject(
        _mem("s", "ok", days_ago=1, now=now),
        query_tokens=frozenset(),
        now=now,
    )
    long = score_memory_for_inject(
        _mem(
            "l",
            "User is a SOC analyst who prefers Chinese language incident reports "
            "and high severity first triage.",
            days_ago=1,
            now=now,
        ),
        query_tokens=frozenset(),
        now=now,
    )
    assert abs(short - long) < 1e-9


def test_select_respects_top_k_and_window() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    rows = [
        _mem("fresh", "User is a SOC analyst.", days_ago=2, now=now),
        _mem("stale", "User was a student.", days_ago=200, now=now),
        _mem("mid", "User prefers Chinese reports.", days_ago=10, now=now),
    ]
    selected = select_memories_for_inject(
        rows,
        query="SOC analyst report",
        config=MemoryInjectConfig(
            enabled=True,
            top_k=2,
            window_days=90,
            dedupe_topics=False,
        ),
        now=now,
    )
    ids = {m.memory_id for m in selected}
    assert "stale" not in ids
    assert len(selected) <= 2


def test_dedupe_topics_keeps_best() -> None:
    now = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
    rows = [
        _mem(
            "old_lang",
            "User prefers English reports.",
            days_ago=30,
            topics=["pref.language"],
            now=now,
        ),
        _mem(
            "new_lang",
            "User prefers Chinese language reports for security.",
            days_ago=1,
            topics=["pref.language"],
            now=now,
        ),
        _mem(
            "other",
            "User escalates to oncall.",
            days_ago=2,
            topics=["pref.escalation"],
            now=now,
        ),
    ]
    selected = select_memories_for_inject(
        rows,
        query="Chinese report language",
        config=MemoryInjectConfig(
            enabled=True,
            top_k=10,
            window_days=90,
            dedupe_topics=True,
        ),
        now=now,
    )
    ids = [m.memory_id for m in selected]
    assert "new_lang" in ids
    assert "old_lang" not in ids


def test_disabled_returns_all() -> None:
    rows = [_mem("a", "one"), _mem("b", "two")]
    selected = select_memories_for_inject(
        rows,
        query="x",
        config=MemoryInjectConfig(enabled=False),
    )
    assert len(selected) == 2
