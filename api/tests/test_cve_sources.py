from api.tasks.cve_sources import ExploitDBSource


def test_exploitdb_source_parses_csv_text() -> None:
    raw_csv = "\n".join(
        [
            "id,file,description,date,author,type,platform,port,codes,tags,verified",
            "1,exploits/linux/remote/12345.py,Example vuln,2026-01-01,a,remote,linux,,CVE-2026-0001,,1",
        ]
    )

    parsed = ExploitDBSource().parse_data(raw_csv)

    assert parsed.to_dicts() == [
        {
            "cve_id": "CVE-2026-0001",
            "description": "Example vuln",
            "github_url": "https://www.exploit-db.com/exploits/12345",
        }
    ]
