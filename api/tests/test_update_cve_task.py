from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import polars as pl
import pytest

from api.tasks import update_cve


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
            "update_cve_database",
            new=AsyncMock(side_effect=RuntimeError("db unavailable")),
        ),
    ):
        with pytest.raises(RuntimeError, match="db unavailable"):
            await update_cve.main()

    assert not cache_path.exists()
    assert not commit_path.exists()


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
