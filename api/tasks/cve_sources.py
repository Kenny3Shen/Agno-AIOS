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


# CVE Program IDs have a four-digit year and at least a four-digit sequence.
# Keep this shared by parsers and the update pipeline so non-CVE identifiers
# (ExploitDB file paths, OSVDB IDs, arbitrary advisory codes) cannot enter the
# CVE table.
CVE_ID_PATTERN = r"CVE-\d{4}-\d{4,}"
_CVE_ID_FULL_RE = re.compile(rf"^{CVE_ID_PATTERN}$", re.IGNORECASE)
_CVE_ID_EXTRACT_PATTERN = rf"(?i)\b({CVE_ID_PATTERN})\b"
_CVE_ID_POLARS_PATTERN = rf"(?i)^{CVE_ID_PATTERN}$"
_CVE_REQUIRED_COLUMNS = {"cve_id", "description", "github_url"}


def normalize_cve_id(value: Any) -> str | None:
    """Return an uppercase CVE ID only when *value* has the canonical form."""
    cve_id = str(value or "").strip().upper()
    return cve_id if _CVE_ID_FULL_RE.fullmatch(cve_id) else None


def normalize_cve_dataframe(dataframe: pl.DataFrame) -> pl.DataFrame:
    """Normalize and strictly filter a source dataframe to valid CVE rows."""
    if dataframe.is_empty():
        return dataframe
    missing = _CVE_REQUIRED_COLUMNS.difference(dataframe.columns)
    if missing:
        logger.warning("CVE source data is missing required columns: {}", sorted(missing))
        return pl.DataFrame(
            schema={
                "cve_id": pl.String,
                "description": pl.String,
                "github_url": pl.String,
            }
        )

    initial_height = dataframe.height
    identity_columns = ["cve_id", "github_url"]
    if "source" in dataframe.columns:
        identity_columns.append("source")
    normalized = (
        dataframe.with_columns(
            pl.col("cve_id")
            .cast(pl.String)
            .str.strip_chars()
            .str.to_uppercase()
            .alias("cve_id"),
            pl.col("description").fill_null("").cast(pl.String).alias("description"),
            pl.col("github_url")
            .fill_null("")
            .cast(pl.String)
            .str.strip_chars()
            .alias("github_url"),
        )
        .filter(pl.col("cve_id").str.contains(_CVE_ID_POLARS_PATTERN))
        .filter(pl.col("github_url") != "")
        .unique(subset=identity_columns, keep="first")
    )
    rejected = initial_height - normalized.height
    if rejected:
        logger.warning("Filtered {} non-CVE or invalid reference row(s)", rejected)
    return normalized


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
            rf"^##\s*({CVE_ID_PATTERN})\b(.*?)(?=^##\s|\Z)",
            raw_data,
            re.DOTALL | re.IGNORECASE | re.MULTILINE,
        )

        url_pattern = re.compile(r"-\s*\[(https://github\.com/[^\]]+)\]")
        cve_data = []

        for block in cve_blocks:
            cve_id = normalize_cve_id(block.group(1))
            if not cve_id:
                continue
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

        normalized = normalize_cve_dataframe(df_remote_cve)
        logger.info("从数据中解析了 {} 条有效的 CVE 记录", normalized.height)
        return normalized

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

        try:
            source_frame = pl.read_csv(StringIO(raw_data))
        except pl.exceptions.PolarsError as exc:
            logger.warning("无法解析 ExploitDB CSV: {}", exc)
            return pl.DataFrame()

        required = {"file", "codes", "description"}
        missing = required.difference(source_frame.columns)
        if missing:
            logger.warning("ExploitDB CSV is missing required columns: {}", sorted(missing))
            return pl.DataFrame()

        # ExploitDB includes many rows without CVEs. Do not fall back to file
        # paths, OSVDB IDs, or arbitrary ``codes`` values: this is a CVE table.
        df_remote_cve = (
            source_frame.lazy()
            .select(
                pl.col("codes")
                .cast(pl.String)
                .str.extract(_CVE_ID_EXTRACT_PATTERN, 1)
                .str.to_uppercase()
                .alias("cve_id"),
                pl.col("description").fill_null("").cast(pl.String).alias("description"),
                pl.col("file")
                .cast(pl.String)
                .str.extract(r"/(\d+)\.", 1)
                .alias("_exploit_id"),
            )
            .filter(pl.col("cve_id").is_not_null())
            .filter(pl.col("_exploit_id").str.contains(r"^\d+$"))
            .with_columns(
                pl.format(
                    "https://www.exploit-db.com/exploits/{}",
                    pl.col("_exploit_id"),
                ).alias("github_url")
            )
            .select("cve_id", "description", "github_url")
            .collect()
        )
        normalized = normalize_cve_dataframe(df_remote_cve)

        logger.info("去重后: {} 条唯一 CVE 记录", normalized.height)
        return normalized

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
    "CVE_ID_PATTERN",
    "DATA_SOURCES",
    "load_cve_source_config",
    "normalize_cve_dataframe",
    "normalize_cve_id",
]
