#!/usr/bin/env python3
"""
CVE更新工具和数据源类

将辅助函数和数据源类放在这里，保持 CVE 更新任务的核心流程简洁
"""

import re
import tomllib
from abc import ABC, abstractmethod
from io import StringIO
from pathlib import Path
from typing import Any

from anyio import Path as AsyncPath
import httpx
import polars as pl
from loguru import logger

from api.config import get_settings
from api.services.runtime_env import load_runtime_env_async


def _cve_cache_file(filename: str) -> str:
    return str(Path(get_settings().cve_data_dir) / filename)


class CVEDataSource(ABC):
    """CVE数据源抽象基类"""

    @abstractmethod
    async def fetch_data(self):
        """获取原始数据"""
        pass

    @abstractmethod
    def parse_data(self, raw_data: Any) -> pl.DataFrame:
        """解析数据为标准格式，返回 DataFrame

        返回格式:
        DataFrame with columns: cve_id, description, github_url
        """
        pass

    @abstractmethod
    def get_local_cache_path(self) -> str:
        """获取本地缓存文件路径"""
        pass

    @abstractmethod
    async def get_remote_commit(self) -> str:
        """获取远程数据的最新commit sha"""
        pass

    def compare_with_local(
        self, df_new: pl.DataFrame, df_old: pl.DataFrame
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """使用Polars高效对比新旧数据

        Args:
            df_new: 新数据DataFrame
            df_old: 旧数据DataFrame

        Returns:
            (increment_df, deleted_df) DataFrame 元组
        """
        if df_new.is_empty():
            return pl.DataFrame(), df_old

        if df_old.is_empty():
            return df_new, pl.DataFrame()

        # 使用anti_join找出增量数据（在new中但不在old中）
        df_increment = df_new.join(
            df_old.select(["cve_id", "github_url"]),
            on=["cve_id", "github_url"],
            how="anti",
        )

        # 使用anti_join找出删除数据（在old中但不在new中）
        df_deleted = df_old.join(
            df_new.select(["cve_id", "github_url"]),
            on=["cve_id", "github_url"],
            how="anti",
        )

        logger.info(
            "数据对比: 本地={}, 远程={}, 增量={}, 待删除={}",
            df_old.height,
            df_new.height,
            df_increment.height,
            df_deleted.height,
        )

        return df_increment, df_deleted


async def load_cve_source_config() -> dict[str, Any]:
    await load_runtime_env_async()
    config_path = AsyncPath(get_settings().cve_source_config_path)
    try:
        content = await config_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        logger.warning("无法解析 CVE 数据源配置: {}", config_path)
        return {}
    return data if isinstance(data, dict) else {}


class GitHubPocExpSource(CVEDataSource):
    """从GitHub PocOrExp仓库获取CVE数据"""

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = (config or {}).get("github", {})
        self.remote_url = cfg.get(
            "remote_url",
            "https://raw.githubusercontent.com/ycdxsb/PocOrExp_in_Github/refs/heads/main/PocOrExp.md",
        )
        self.local_path = cfg.get("local_cache", _cve_cache_file("github_cve_cache.csv"))
        self.commit_cache = cfg.get("commit_cache", _cve_cache_file("github_commit.txt"))
        self.repo_api = cfg.get(
            "repo_api", "https://api.github.com/repos/ycdxsb/PocOrExp_in_Github/commits"
        )
        self.default_branch = cfg.get("default_branch", "main")

    async def fetch_data(self) -> str:
        """从 GitHub 获取数据"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(self.remote_url)
            resp.raise_for_status()
            logger.info("成功从 {} 获取数据", self.remote_url)
            return resp.text

    def parse_data(self, raw_data: Any) -> pl.DataFrame:
        """解析 Markdown 格式的 CVE 数据"""
        if not isinstance(raw_data, str) or not raw_data:
            return pl.DataFrame()

        # 1. 使用正则匹配 CVE 块：从 ## CVE-xxx 开始到下一个 ## 或文件末尾
        # re.DOTALL 允许 . 匹配换行符
        cve_blocks = re.finditer(
            r"##\s*(CVE-\d{4}-\d+)(.*?)(?=\n##|\Z)", raw_data, re.DOTALL
        )

        url_pattern = re.compile(r"-\s*\[(https://github\.com/[^\]]+)\]")
        cve_data = []

        for block in cve_blocks:
            cve_id = block.group(1)
            content = block.group(2)

            # 2. 提取该块内所有的 GitHub URL
            urls = url_pattern.findall(content)
            if not urls:
                # 如果没有 URL，则跳过该 CVE（确保 github_url 不为空）
                continue

            # 3. 提取描述：取第一个 URL 之前的内容并清理
            first_url_match = url_pattern.search(content)
            desc_part = (
                content[: first_url_match.start()].strip()
                if first_url_match
                else content
            )

            # 过滤掉图片标签 (![...]) 和多余空行
            description = "\n".join(
                [
                    line.strip()
                    for line in desc_part.split("\n")
                    if line.strip() and not line.strip().startswith("![")
                ]
            )

            # 4. 为每个 URL 生成一条记录
            for url in urls:
                cve_data.append(
                    {
                        "cve_id": cve_id,
                        "description": description,
                        "github_url": url,
                    }
                )

        # 5. 使用 Polars 高效去重
        df_remote_cve = (
            pl.DataFrame(cve_data).unique(subset=["cve_id", "github_url"])
            if cve_data
            else pl.DataFrame()
        )

        logger.info("从数据中解析了 {} 条有效的 CVE 记录", df_remote_cve.height)
        return df_remote_cve

    def get_local_cache_path(self) -> str:
        """获取本地缓存文件路径"""
        return self.local_path

    async def get_remote_commit(self) -> str:
        """获取远程数据的最新 commit sha"""
        await load_runtime_env_async()
        github_token = get_settings().github_token.get_secret_value()
        headers = {"Authorization": f"token {github_token}"} if github_token else {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                self.repo_api,
                params={"sha": self.default_branch, "per_page": 1},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()[0]["sha"]


class ExploitDBSource(CVEDataSource):
    """从Exploit-DB获取CVE数据"""

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = (config or {}).get("exploit_db", {})
        self.remote_url = cfg.get(
            "remote_url",
            "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv?ref_type=heads",
        )
        self.local_path = cfg.get("local_cache", _cve_cache_file("exploit_db.csv"))
        self.commit_cache = cfg.get("commit_cache", _cve_cache_file("exploitdb_commit.txt"))
        self.repo_api = cfg.get(
            "repo_api",
            "https://gitlab.com/api/v4/projects/exploit-database%2Fexploitdb/repository/commits",
        )
        self.default_branch = cfg.get("default_branch", "main")

    async def fetch_data(self) -> str:
        """从 Exploit-DB 获取数据"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(self.remote_url)
            resp.raise_for_status()
            logger.info("成功从 {} 获取数据", self.remote_url)
            return resp.text

    def parse_data(self, raw_data: Any) -> pl.DataFrame:
        """解析 Exploit-DB 数据

        Args:
            raw_data: CSV 文本（从远程获取）

        Returns:
            处理后的 CVE 数据列表
        """
        if not isinstance(raw_data, str) or not raw_data:
            logger.warning(
                "意外的 raw_data 类型: 预期 CSV 文本，实际 {}",
                type(raw_data),
            )
            return pl.DataFrame()

        # 使用 Polars 处理数据
        # 基于 (cve_id, github_url) 去重
        # coalesce 从左到右折叠列，保留第一个非空值。
        df_remote_cve = (
            pl.read_csv(StringIO(raw_data))
            .lazy()
            .select(
                pl.when(pl.col("codes").is_null() | (pl.col("codes") == ""))
                .then(pl.col("file"))
                .otherwise(
                    pl.coalesce(
                        pl.col("codes").str.extract(r"(CVE-\d{4}-\d+)", 1),
                        pl.col("codes").str.extract(r"(OSVDB-\d+)", 1),
                        pl.col("codes"),
                    )
                )
                .alias("cve_id"),
                pl.col("description").alias("description"),
                pl.format(
                    "https://www.exploit-db.com/exploits/{}",
                    pl.col("file").str.extract(r"/(\d+)\.", 1),
                ).alias("github_url"),
            )
            .unique(subset=["cve_id", "github_url"], keep="first")
            .collect()
        )

        logger.info("去重后: {} 条唯一 CVE 记录）", df_remote_cve.height)
        return df_remote_cve

    def get_local_cache_path(self) -> str:
        """获取本地缓存文件路径"""
        return self.local_path

    async def get_remote_commit(self) -> str:
        """获取远程数据的最新 commit sha"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                self.repo_api,
                params={"ref_name": self.default_branch, "per_page": 1},
            )
            resp.raise_for_status()
            return resp.json()[0]["id"]


# 数据源注册表
DATA_SOURCES = {
    "github": GitHubPocExpSource,
    "exploit-db": ExploitDBSource,
}

__all__ = [
    "CVEDataSource",
    "GitHubPocExpSource",
    "ExploitDBSource",
    "DATA_SOURCES",
    "load_cve_source_config",
]
