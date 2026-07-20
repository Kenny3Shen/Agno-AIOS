"""Critical IP blacklist threat-intel tests."""

from __future__ import annotations

import polars as pl
import pytest

from api.tasks.ip_blacklist_sources import (
    FireholLevel1Source,
    normalize_indicator,
    normalize_ip_blacklist_dataframe,
)


def test_normalize_indicator_accepts_ip_and_cidr():
    assert normalize_indicator("1.2.3.4") == "1.2.3.4"
    assert normalize_indicator("10.0.0.0/8") == "10.0.0.0/8"
    assert normalize_indicator("  8.8.8.8  # comment") == "8.8.8.8"
    assert normalize_indicator("# comment only") is None
    assert normalize_indicator("not-an-ip") is None
    assert normalize_indicator("999.1.1.1") is None


def test_firehol_parse_skips_comments_and_invalid_lines():
    raw = """
# FireHOL level1
# Source: spamhaus
1.2.3.0/24
8.8.8.8
not-valid
2001:db8::/32
"""
    source = FireholLevel1Source({})
    frame = source.parse_data(raw)
    assert not frame.is_empty()
    indicators = set(frame["indicator"].to_list())
    assert "1.2.3.0/24" in indicators
    assert "8.8.8.8" in indicators
    assert "2001:db8::/32" in indicators
    assert all(frame["source"].to_list()[0] == "firehol-level1" for _ in [0])
    assert "not-valid" not in indicators


def test_normalize_ip_blacklist_dataframe_dedupes_and_types():
    frame = pl.DataFrame(
        {
            "indicator": ["1.1.1.1", "1.1.1.1", "2.2.2.0/24", "bad"],
            "source": ["firehol-level1", "firehol-level1", "firehol-level1", "firehol-level1"],
            "list_name": ["a", "a", "a", "a"],
            "description": ["d", "d", "d", "d"],
        }
    )
    normalized = normalize_ip_blacklist_dataframe(frame)
    assert normalized.height == 2
    types = {
        row["indicator"]: row["indicator_type"] for row in normalized.to_dicts()
    }
    assert types["1.1.1.1"] == "ip"
    assert types["2.2.2.0/24"] == "cidr"


@pytest.mark.asyncio
async def test_search_ip_blacklist_rows_filters_by_query(monkeypatch):
    from api.persistence import ip_blacklist as store

    captured: dict = {}

    class FakeResult:
        def __init__(self, value):
            self._value = value

        def scalar_one(self):
            return self._value

        def mappings(self):
            return self

        def all(self):
            return self._value

    class FakeConn:
        async def execute(self, stmt):
            sql = str(stmt)
            captured.setdefault("sql", []).append(sql)
            if "count" in sql.lower():
                return FakeResult(1)
            return FakeResult(
                [
                    {
                        "id": 1,
                        "indicator": "1.2.3.4",
                        "indicator_type": "ip",
                        "source": "firehol-level1",
                        "list_name": "firehol-level1",
                        "description": "test",
                        "first_seen": None,
                        "last_seen": None,
                        "updated_at": None,
                    }
                ]
            )

    class FakeBegin:
        async def __aenter__(self):
            return FakeConn()

        async def __aexit__(self, *args):
            return False

    class FakeEngine:
        def begin(self):
            return FakeBegin()

    async def _ensure():
        return None

    monkeypatch.setattr(store, "ensure_ip_blacklist_table", _ensure)
    monkeypatch.setattr(store, "get_async_control_plane_engine", lambda: FakeEngine())

    rows, total = await store.search_ip_blacklist_rows(query="1.2.3", page=1, size=10)
    assert total == 1
    assert rows[0]["indicator"] == "1.2.3.4"
