"""CVE id extraction for Collect / 安全情报 article cards."""

from unittest.mock import AsyncMock, patch

import pytest

from api.services.collect_crawl_service import extract_cve_ids
from api.services import collect_service


def test_extract_cve_ids_dedupes_and_uppercases():
    ids = extract_cve_ids(
        "Advisory for cve-2024-1234",
        "Also CVE-2024-1234 and CVE-2021-44228",
        "noise CVE-99-1 invalid",
    )
    assert ids == ["CVE-2024-1234", "CVE-2021-44228"]


@pytest.mark.asyncio
async def test_search_articles_exposes_derived_and_persisted_cve_ids():
    rows = [
        {
            "title": "Log4Shell CVE-2021-44228 emergency",
            "summary": "patch now",
            "markdown": "",
        },
        {
            "title": "CVE-2020-0001",
            "summary": "",
            "markdown": "",
            "cve_ids": ["cve-2019-9999"],
        },
    ]
    with patch.object(
        collect_service,
        "search_collect_articles",
        AsyncMock(return_value=(rows, len(rows))),
    ):
        articles, total = await collect_service.search_articles()

    assert total == 2
    assert [article["cve_ids"] for article in articles] == [
        ["CVE-2021-44228"],
        ["CVE-2019-9999"],
    ]
