"""P1: inject-side memory ranking for Chat / Team context.

Agno's default ``add_memories_to_context`` dumps *all* user memories into the
system prompt.  This module scores candidates with a deterministic, zero-LLM
formula and returns a capped subset.

Score (higher is better, each component in [0, 1]):

    score = 0.40 * recency
          + 0.35 * keyword
          + 0.15 * topic
          + 0.10 * quality

Then:
1. Drop rows outside the time window (``window_days``; 0 = disabled).
2. Optionally keep only the best row per topic key (conflict dedupe).
3. Sort by score, take top-k.
4. Enforce a total character budget (``max_chars``).

No embeddings — keyword/topic matching is intentional for P1 cost/latency.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Sequence

from loguru import logger

# Weight vector — fixed product defaults (Settings expose operational caps only).
W_RECENCY = 0.40
W_KEYWORD = 0.35
W_TOPIC = 0.15
W_QUALITY = 0.10

# Latin tokens ≥2 chars; CJK runs ≥1 char; digits/IP-ish tokens kept when ≥2.
_TOKEN_RE = re.compile(
    r"[a-z0-9][a-z0-9._-]{1,}|[\u4e00-\u9fff]{1,}",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class MemoryInjectConfig:
    """Operational knobs for inject-side selection."""

    enabled: bool = True
    top_k: int = 12
    max_chars: int = 2000
    window_days: int = 90
    dedupe_topics: bool = True


def memory_inject_config_from_settings(settings: Any) -> MemoryInjectConfig:
    """Build config from ChatSettings dataclass or plain mapping."""
    if settings is None:
        return MemoryInjectConfig()

    def _get(name: str, default: Any) -> Any:
        if isinstance(settings, dict):
            return settings.get(name, default)
        return getattr(settings, name, default)

    return MemoryInjectConfig(
        enabled=bool(_get("memory_inject_enabled", True)),
        top_k=max(1, min(100, int(_get("memory_inject_top_k", 12) or 12))),
        max_chars=max(200, min(20_000, int(_get("memory_inject_max_chars", 2000) or 2000))),
        window_days=max(0, min(3650, int(_get("memory_inject_window_days", 90) or 0))),
        dedupe_topics=bool(_get("memory_inject_dedupe_topics", True)),
    )


def tokenize_for_memory_match(text: str) -> frozenset[str]:
    """Normalize query/memory text into a token set for keyword overlap."""
    raw = str(text or "").strip().lower()
    if not raw:
        return frozenset()
    tokens: set[str] = set()
    for match in _TOKEN_RE.findall(raw):
        token = match.strip("._-").lower()
        if not token:
            continue
        # Drop ultra-common English stopwords that pollute overlap.
        if token in _STOPWORDS:
            continue
        tokens.add(token)
    return frozenset(tokens)


_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "have",
        "has",
        "are",
        "was",
        "were",
        "you",
        "your",
        "user",
        "please",
        "about",
        "into",
        "will",
        "would",
        "could",
        "should",
        "what",
        "when",
        "where",
        "which",
        "how",
        "why",
        "not",
        "but",
        "can",
        "all",
        "any",
        "our",
        "they",
        "them",
        "their",
    }
)


def _as_utc_datetime(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if isinstance(value, int | float):
        try:
            ts = float(value)
            if ts > 1e12:
                ts = ts / 1000.0
            return datetime.fromtimestamp(ts, UTC)
        except (OSError, OverflowError, ValueError):
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.isdigit():
            return _as_utc_datetime(int(text))
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _memory_text(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("memory") or "")
    return str(getattr(item, "memory", None) or "")


def _memory_topics(item: Any) -> list[str]:
    raw = item.get("topics") if isinstance(item, dict) else getattr(item, "topics", None)
    if not isinstance(raw, list):
        return []
    return [str(t).strip() for t in raw if str(t).strip()]


def _memory_id(item: Any) -> str:
    if isinstance(item, dict):
        return str(item.get("memory_id") or "").strip()
    return str(getattr(item, "memory_id", None) or "").strip()


def _memory_updated(item: Any) -> object:
    if isinstance(item, dict):
        return item.get("updated_at") or item.get("created_at")
    return getattr(item, "updated_at", None) or getattr(item, "created_at", None)


def topic_key(item: Any) -> str | None:
    """Stable key for conflict dedupe: first non-empty topic, lowercased."""
    topics = _memory_topics(item)
    if not topics:
        return None
    return topics[0].casefold()


def score_memory_for_inject(
    item: Any,
    *,
    query_tokens: frozenset[str],
    now: datetime | None = None,
) -> float:
    """Return composite inject score in roughly [0, 1+]."""
    wall = now or datetime.now(UTC)
    updated = _as_utc_datetime(_memory_updated(item))
    if updated is None:
        recency = 0.0
    else:
        age_days = max(0.0, (wall - updated).total_seconds() / 86_400.0)
        recency = 1.0 / (1.0 + age_days / 30.0)

    text = _memory_text(item)
    mem_tokens = tokenize_for_memory_match(text)
    topics = _memory_topics(item)
    topic_tokens = tokenize_for_memory_match(" ".join(topics))

    if not query_tokens:
        # No query → pure recency + quality (last_n-like with quality prior).
        keyword = 0.0
        topic = 0.0
    else:
        overlap = query_tokens & mem_tokens
        keyword = len(overlap) / max(1, len(query_tokens))
        # Cap so a single token match is meaningful but not dominating alone.
        keyword = min(1.0, keyword * 1.5)

        topic_overlap = query_tokens & topic_tokens
        # Also credit when a topic string appears as substring of query tokens.
        topic = min(1.0, len(topic_overlap) / max(1, min(3, len(topic_tokens) or 1)))
        if topics and not topic_overlap:
            for topic_label in topics:
                label = topic_label.casefold()
                if any(label in qt or qt in label for qt in query_tokens if len(qt) >= 2):
                    topic = max(topic, 0.6)
                    break

    length = len(text.strip())
    if length <= 0:
        quality = 0.0
    elif length < 12:
        quality = 0.2
    else:
        quality = min(1.0, length / 280.0)

    return (
        W_RECENCY * recency
        + W_KEYWORD * keyword
        + W_TOPIC * topic
        + W_QUALITY * quality
    )


def select_memories_for_inject(
    memories: Sequence[Any] | None,
    *,
    query: str = "",
    config: MemoryInjectConfig | None = None,
    now: datetime | None = None,
) -> list[Any]:
    """Rank and cap memories for system-prompt injection.

    Returns the original memory objects (not copies) in **descending score**
    order, already limited by top-k and max_chars.
    """
    cfg = config or MemoryInjectConfig()
    if not cfg.enabled:
        return list(memories or [])

    wall = now or datetime.now(UTC)
    query_tokens = tokenize_for_memory_match(query)
    candidates: list[Any] = list(memories or [])
    if not candidates:
        return []

    # 1) Time window (0 = no filter).
    if cfg.window_days > 0:
        cutoff = wall - timedelta(days=cfg.window_days)
        filtered: list[Any] = []
        for item in candidates:
            updated = _as_utc_datetime(_memory_updated(item))
            if updated is None or updated >= cutoff:
                filtered.append(item)
        candidates = filtered

    if not candidates:
        return []

    # 2) Score.
    scored: list[tuple[float, str, Any]] = []
    for item in candidates:
        score = score_memory_for_inject(item, query_tokens=query_tokens, now=wall)
        mid = _memory_id(item) or str(id(item))
        scored.append((score, mid, item))

    # 3) Topic dedupe — keep highest score per topic key.
    if cfg.dedupe_topics:
        best_by_topic: dict[str, tuple[float, str, Any]] = {}
        no_topic: list[tuple[float, str, Any]] = []
        for entry in scored:
            key = topic_key(entry[2])
            if key is None:
                no_topic.append(entry)
                continue
            prev = best_by_topic.get(key)
            if prev is None or entry[0] > prev[0] or (
                entry[0] == prev[0] and entry[1] > prev[1]
            ):
                best_by_topic[key] = entry
        scored = list(best_by_topic.values()) + no_topic

    # 4) Sort + top-k.
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    ranked = [item for _s, _id, item in scored[: max(1, cfg.top_k)]]

    # 5) Character budget (always keep at least one if any).
    selected: list[Any] = []
    used = 0
    for item in ranked:
        text = _memory_text(item).strip()
        cost = len(text) + 4  # bullet overhead
        if selected and used + cost > cfg.max_chars:
            continue
        selected.append(item)
        used += cost
        if used >= cfg.max_chars:
            break

    if not selected and ranked:
        selected = [ranked[0]]

    logger.debug(
        "memory inject selected={}/{} query_tokens={} top_k={} max_chars={}",
        len(selected),
        len(memories or []),
        len(query_tokens),
        cfg.top_k,
        cfg.max_chars,
    )
    return selected


__all__ = [
    "MemoryInjectConfig",
    "W_KEYWORD",
    "W_QUALITY",
    "W_RECENCY",
    "W_TOPIC",
    "memory_inject_config_from_settings",
    "score_memory_for_inject",
    "select_memories_for_inject",
    "tokenize_for_memory_match",
    "topic_key",
]
