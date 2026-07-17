"""CVE id extraction for Collect / 安全情报 article cards."""

from api.services.collect_crawl_service import extract_cve_ids
from api.services.collect_service import _with_cve_ids


def test_extract_cve_ids_dedupes_and_uppercases():
    ids = extract_cve_ids(
        "Advisory for cve-2024-1234",
        "Also CVE-2024-1234 and CVE-2021-44228",
        "noise CVE-99-1 invalid",
    )
    assert ids == ["CVE-2024-1234", "CVE-2021-44228"]


def test_with_cve_ids_from_title_without_body():
    row = _with_cve_ids(
        {
            "title": "Log4Shell CVE-2021-44228 emergency",
            "summary": "patch now",
            "markdown": "",
        }
    )
    assert row is not None
    assert row["cve_ids"] == ["CVE-2021-44228"]


def test_with_cve_ids_keeps_existing():
    row = _with_cve_ids(
        {
            "title": "CVE-2020-0001",
            "summary": "",
            "markdown": "",
            "cve_ids": ["CVE-2019-9999"],
        }
    )
    assert row is not None
    assert row["cve_ids"] == ["CVE-2019-9999"]
