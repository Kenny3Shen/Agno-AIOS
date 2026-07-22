from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import polars as pl
import pytest

from api.tasks import update_cve
from api.tasks.cve_sources import ExploitDBSource, MarcioCVESource, normalize_cve_id


class _ChangingSource:
    def __init__(self, config: dict[str, str]) -> None:
        self.cache_path = Path(config["cache_path"])
        self.commit_path = Path(config["commit_path"])

    async def get_remote_commit(self) -> str:
        return "remote-sha"

    async def fetch_data(self) -> str:
        return "raw"

    def parse_data(self, raw_data: str) -> pl.DataFrame:
        return pl.DataFrame(
            [
                {
                    "cve_id": "CVE-2026-0001",
                    "description": "Example",
                    "github_url": "https://github.com/example/poc",
                }
            ]
        )

    def get_local_cache_path(self) -> str:
        return str(self.cache_path)

    def compare_with_local(
        self, df_new: pl.DataFrame, df_old: pl.DataFrame
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        return df_new, pl.DataFrame()


class _EmptySource(_ChangingSource):
    def parse_data(self, raw_data: str) -> pl.DataFrame:
        return pl.DataFrame(
            schema={
                "cve_id": pl.String,
                "description": pl.String,
                "github_url": pl.String,
            }
        )


class _StableCachedSource(_ChangingSource):
    def __init__(self, config: dict[str, str]) -> None:
        super().__init__(config)
        self.commit_cache = str(self.commit_path)

    async def fetch_data(self) -> str:
        raise AssertionError("an unchanged commit with a usable cache must not refetch")


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


def test_exploitdb_source_excludes_non_cve_codes_and_paths() -> None:
    raw_csv = "\n".join(
        [
            "id,file,description,date,author,type,platform,port,codes,tags,verified",
            "1,exploits/linux/remote/12345.py,Valid,2026-01-01,a,remote,linux,,CVE-2026-0001,,1",
            "2,exploits/linux/remote/12346.py,OSVDB,2026-01-01,a,remote,linux,,OSVDB-12345,,1",
            "3,exploits/linux/remote/12347.py,Short,2026-01-01,a,remote,linux,,CVE-2026-123,,1",
            "4,exploits/linux/remote/12348.py,Empty,2026-01-01,a,remote,linux,,,,1",
            "5,exploits/linux/remote/12349.py,Another,2026-01-01,a,remote,linux,,CVE-2026-0002;OSVDB-1,,1",
        ]
    )

    parsed = ExploitDBSource().parse_data(raw_csv)

    assert sorted(parsed.select("cve_id").to_series().to_list()) == [
        "CVE-2026-0001",
        "CVE-2026-0002",
    ]
    assert normalize_cve_id("CVE-2026-123") is None
    assert normalize_cve_id("osvdb-12345") is None


def test_marcio_source_parses_markdown_tables_and_deduplicates_repository_pairs() -> None:
    raw_markdown = "\n".join(
        [
            "| Stars | Updated | Name | Description |",
            "| --- | --- | --- | --- |",
            "| 10 | now | [cve_2026_31431](https://github.com/Example/Copy-Fail/) | First PoC for CVE-2026-31431 |",
            "| 9 | now | [CVE-2026-31431](https://github.com/example/copy-fail) | Duplicate repository |",
            "| 8 | now | [CVE-2025-1111-CVE-2025-2222](https://github.com/example/two-cves) | Covers both CVEs |",
            "| 7 | now | [scanner](https://github.com/example/description-only) | Scanner for CVE-2024-9999 |",
            "| 6 | now | [CVE-2025-123](https://github.com/example/invalid) | Invalid short sequence |",
            "| 6 | now | [CVE-2025-1234oops](https://github.com/example/invalid-suffix) | Invalid suffix |",
            "| 5 | now | [CVE-2023-4567](https://github.com/example/title-only) |  |",
            "| 4 | now | [CVE-2022-1234](https://github.com/example/canonical.git/?ref=main) | Git URL |",
            "| 3 | now | [CVE-2021-1234](https://github.com/example/not-a-repository/tree/main) | Nested path |",
        ]
    )

    parsed = MarcioCVESource().parse_data(raw_markdown)

    assert parsed.to_dicts() == [
        {
            "cve_id": "CVE-2026-31431",
            "description": "First PoC for CVE-2026-31431",
            "github_url": "https://github.com/Example/Copy-Fail",
        },
        {
            "cve_id": "CVE-2025-1111",
            "description": "Covers both CVEs",
            "github_url": "https://github.com/example/two-cves",
        },
        {
            "cve_id": "CVE-2025-2222",
            "description": "Covers both CVEs",
            "github_url": "https://github.com/example/two-cves",
        },
        {
            "cve_id": "CVE-2024-9999",
            "description": "Scanner for CVE-2024-9999",
            "github_url": "https://github.com/example/description-only",
        },
        {
            "cve_id": "CVE-2023-4567",
            "description": "CVE-2023-4567",
            "github_url": "https://github.com/example/title-only",
        },
        {
            "cve_id": "CVE-2022-1234",
            "description": "Git URL",
            "github_url": "https://github.com/example/canonical",
        },
    ]


def test_description_delta_refreshes_existing_source_row() -> None:
    remote = pl.DataFrame(
        {
            "cve_id": ["CVE-2026-0001"],
            "github_url": ["https://github.com/example/poc"],
            "description": ["Corrected description"],
            "source": ["github"],
        }
    )
    local = remote.with_columns(pl.lit("Old description").alias("description"))

    updates = update_cve._description_updates(remote, local)

    assert updates.to_dicts() == remote.to_dicts()


def test_compare_with_local_uses_cve_url_identity_for_lazy_anti_joins() -> None:
    source = ExploitDBSource()
    remote = pl.DataFrame(
        [
            {
                "cve_id": "CVE-2026-0001",
                "description": "Updated description",
                "github_url": "https://github.com/example/existing",
            },
            {
                "cve_id": "CVE-2026-0002",
                "description": "Added",
                "github_url": "https://github.com/example/new",
            },
        ]
    )
    local = pl.DataFrame(
        [
            {
                "cve_id": "CVE-2026-0001",
                "description": "Old description",
                "github_url": "https://github.com/example/existing",
            },
            {
                "cve_id": "CVE-2026-0003",
                "description": "Removed",
                "github_url": "https://github.com/example/removed",
            },
        ]
    )

    additions, deletions = source.compare_with_local(remote, local)

    assert additions.to_dicts() == [remote.row(1, named=True)]
    assert deletions.to_dicts() == [local.row(1, named=True)]


@pytest.mark.asyncio
async def test_unchanged_commit_backfills_missing_source_membership(tmp_path) -> None:
    cache_path = tmp_path / "cache.csv"
    commit_path = tmp_path / "commit.txt"
    cache_path.write_text(
        "cve_id,description,github_url,source\n"
        "CVE-2026-0001,Existing,https://github.com/example/poc,github\n",
        encoding="utf-8",
    )
    commit_path.write_text("remote-sha", encoding="utf-8")
    config = {"cache_path": str(cache_path), "commit_path": str(commit_path)}
    source_identity = (
        "CVE-2026-0001",
        "https://github.com/example/poc",
        "fake",
    )

    with (
        patch.dict(update_cve.DATA_SOURCES, {"fake": _StableCachedSource}, clear=True),
        patch.object(
            update_cve,
            "find_missing_cve_source_keys",
            new=AsyncMock(return_value={source_identity}),
        ) as find_missing,
    ):
        delta = await update_cve.get_add_del_data("fake", config)

    find_missing.assert_awaited_once()
    assert delta.upsert_data == [
        {
            "cve_id": "CVE-2026-0001",
            "description": "Existing",
            "github_url": "https://github.com/example/poc",
            "source": "fake",
        }
    ]
    assert delta.deleted_data == []
    assert not delta.should_update_cache
    assert not delta.should_update_commit


@pytest.mark.asyncio
async def test_main_does_not_advance_cache_or_commit_when_database_update_fails(tmp_path):
    cache_path = tmp_path / "cache.csv"
    commit_path = tmp_path / "commit.txt"
    config = {"cache_path": str(cache_path), "commit_path": str(commit_path)}

    with (
        patch.dict(update_cve.DATA_SOURCES, {"fake": _ChangingSource}, clear=True),
        patch.object(update_cve, "load_cve_source_config", new=AsyncMock(return_value=config)),
        patch.object(
            update_cve,
            "get_enabled_cve_source_names",
            new=AsyncMock(return_value=["fake"]),
        ),
        patch.object(
            update_cve,
            "update_cve_database",
            new=AsyncMock(side_effect=RuntimeError("db unavailable")),
        ),
    ):
        with pytest.raises(RuntimeError, match="db unavailable"):
            await update_cve.main()

    assert not cache_path.exists()
    assert not commit_path.exists()


@pytest.mark.asyncio
async def test_main_skips_disabled_cve_sources() -> None:
    delta = update_cve.CVESourceDelta(
        source_name="enabled",
        upsert_data=[],
        deleted_data=[],
        local_cache_path="/tmp/enabled.csv",
        remote_dataframe=pl.DataFrame(),
        remote_commit=None,
        local_commit_path="/tmp/enabled.commit",
        should_update_cache=False,
        should_update_commit=False,
    )

    with (
        patch.dict(
            update_cve.DATA_SOURCES,
            {"enabled": _ChangingSource, "disabled": _ChangingSource},
            clear=True,
        ),
        patch.object(
            update_cve,
            "load_cve_source_config",
            new=AsyncMock(return_value={}),
        ),
        patch.object(
            update_cve,
            "get_enabled_cve_source_names",
            new=AsyncMock(return_value=["enabled"]),
        ) as enabled_sources,
        patch.object(
            update_cve,
            "get_add_del_data",
            new=AsyncMock(return_value=delta),
        ) as get_delta,
        patch.object(
            update_cve,
            "update_cve_database",
            new=AsyncMock(return_value=(0, 0)),
        ),
        patch.object(update_cve, "_commit_source_state", new=AsyncMock()),
        patch.object(update_cve, "_configure_file_logging_async", new=AsyncMock()),
        patch.dict(update_cve.environ, {"TAIS_CVE_UPDATE_LOCK_HELD": "1"}),
    ):
        result = await update_cve.main()

    assert result == (0, 0)
    enabled_sources.assert_awaited_once_with(["enabled", "disabled"])
    get_delta.assert_awaited_once_with("enabled", {})


@pytest.mark.asyncio
async def test_empty_remote_parse_does_not_delete_local_cache_or_advance_commit(tmp_path):
    cache_path = tmp_path / "cache.csv"
    commit_path = tmp_path / "commit.txt"
    cache_path.write_text(
        "cve_id,description,github_url,source\n"
        "CVE-2025-0001,Existing,https://github.com/example/old,github\n",
        encoding="utf-8",
    )
    config = {"cache_path": str(cache_path), "commit_path": str(commit_path)}

    with (
        patch.dict(update_cve.DATA_SOURCES, {"fake": _EmptySource}, clear=True),
        patch.object(update_cve, "load_cve_source_config", new=AsyncMock(return_value=config)),
    ):
        with pytest.raises(RuntimeError, match="parsed no CVE rows"):
            await update_cve.get_add_del_data("fake", config)

    assert "CVE-2025-0001" in cache_path.read_text(encoding="utf-8")
    assert not commit_path.exists()
