from unittest.mock import AsyncMock, patch

import pytest

from api.models.schemas import CveSearchRequest
from api.services.cve_service import search_cves


def test_cve_search_request_allows_an_empty_query_for_recent_entries():
    request = CveSearchRequest(query="   ")

    assert request.query == ""


@pytest.mark.asyncio
async def test_blank_cve_query_is_forwarded_for_recent_entry_lookup():
    rows = [{"id": 1, "cve_id": "CVE-2026-0001"}]
    with patch(
        "api.services.cve_service.search_cve_rows",
        AsyncMock(return_value=(rows, 1)),
    ) as search_rows:
        result = await search_cves(query="", source="github", page=2, size=20)

    assert result == (rows, 1)
    search_rows.assert_awaited_once_with(query="", source="github", page=2, size=20)



def test_search_cve_rows_uses_fts_for_keyword_queries():
    """Keyword path should build a tsquery filter (not only ILIKE)."""
    import inspect
    from api.persistence import cves

    source = inspect.getsource(cves.search_cve_rows)
    assert "plainto_tsquery" in source
    assert "ts_rank_cd" in source
    assert 'startswith("CVE-")' in source or "startswith('CVE-')" in source
