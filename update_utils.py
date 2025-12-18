#!/usr/bin/env python3
"""
CVE更新工具和数据源类

将辅助函数和数据源类放在这里，保持 update_cve.py 的核心流程简洁
"""

import os
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
import tomllib
import polars as pl
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class CVEDataSource(ABC):
    """CVE数据源抽象基类"""

    @abstractmethod
    async def fetch_data(self):
        """获取原始数据"""
        pass

    @abstractmethod
    def parse_data(self, raw_data: Any) -> list[dict[str, str]]:
        """解析数据为标准格式

        返回格式:
        [
            {
                'cve_id': str,
                'description': str,
                'github_url': str
            },
            ...
        ]
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
        self, new_data: list[dict[str, str]], old_data: list[dict[str, str]]
    ) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
        """使用Polars高效对比新旧数据

        Args:
            new_data: 新数据列表
            old_data: 旧数据列表

        Returns:
            (increment_data, deleted_data) 元组
        """
        if not new_data:
            # 如果新数据为空，所有旧数据都应该删除
            return [], old_data

        if not old_data:
            # 如果旧数据为空，所有新数据都是增量
            return new_data, []

        # 使用Polars DataFrame进行高效对比
        df_new = pl.DataFrame(new_data)
        df_old = pl.DataFrame(old_data)

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

        # 转换回列表字典格式
        increment_data = df_increment.to_dicts()
        deleted_data = df_deleted.to_dicts()

        logger.info(
            f"数据对比: 本地={len(old_data)}, 远程={len(new_data)}, "
            f"增量={len(increment_data)}, 待删除={len(deleted_data)}"
        )

        return increment_data, deleted_data


CONFIG_PATH = os.getenv("CONFIG_PATH", "config.toml")
try:
    with open(CONFIG_PATH, "rb") as f:
        CONFIG = tomllib.load(f)
except Exception:
    CONFIG = {}


class GitHubPocExpSource(CVEDataSource):
    """从GitHub PocOrExp仓库获取CVE数据"""

    def __init__(self):
        cfg = CONFIG.get("github", {})
        self.remote_url = cfg.get(
            "remote_url",
            "https://raw.githubusercontent.com/ycdxsb/PocOrExp_in_Github/refs/heads/main/PocOrExp.md",
        )
        self.local_path = cfg.get(
            "local_cache", os.path.join("./api/data", "github_cve_cache.csv")
        )
        self.commit_cache = cfg.get(
            "commit_cache", os.path.join("./api/data", "github_commit.txt")
        )
        self.repo_api = cfg.get(
            "repo_api", "https://api.github.com/repos/ycdxsb/PocOrExp_in_Github/commits"
        )
        self.default_branch = cfg.get("default_branch", "main")

    async def fetch_data(self) -> str:
        """从 GitHub 获取数据"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(self.remote_url)
            resp.raise_for_status()
            logger.info(f"成功从 {self.remote_url} 获取数据")
            return resp.text

    def parse_data(self, raw_data: Any) -> list[dict[str, str]]:
        """解析 Markdown 格式的 CVE 数据"""
        if not isinstance(raw_data, str) or not raw_data:
            return []

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
        if cve_data:
            cve_data = (
                pl.DataFrame(cve_data)
                .unique(subset=["cve_id", "github_url"])
                .to_dicts()
            )

        logger.info(f"从数据中解析了 {len(cve_data)} 条有效的 CVE 记录")
        return cve_data

    def get_local_cache_path(self) -> str:
        """获取本地缓存文件路径"""
        return self.local_path

    async def get_remote_commit(self) -> str:
        """获取远程数据的最新 commit sha"""
        github_token = os.getenv("GITHUB_TOKEN", None)
        headers = {"Authorization": f"token {github_token}"} if github_token else {}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                self.repo_api,
                params={"sha": self.default_branch, "per_page": 1},
                headers=headers,
            )
            resp.raise_for_status()
            return resp.json()[0]["sha"]


# Helper functions for ExploitDBSource
def _process_codes(codes, file_path):
    if not codes or codes == "":
        return file_path

    # 优先匹配CVE编号
    cve_match = re.search(r"CVE-\d{4}-\d+", codes)
    if cve_match:
        return cve_match.group(0)

    # 如果没有CVE编号，匹配OSVDB编号
    osvdb_match = re.search(r"OSVDB-\d+", codes)
    if osvdb_match:
        return osvdb_match.group(0)

    return codes


def _process_file(file_path):
    match = re.search(r"/(\d+)\.", file_path)
    if match:
        exploit_id = match.group(1)
        return f"https://www.exploit-db.com/exploits/{exploit_id}"
    return file_path


class ExploitDBSource(CVEDataSource):
    """从Exploit-DB获取CVE数据"""

    def __init__(self):
        cfg = CONFIG.get("exploit_db", {})
        self.remote_url = cfg.get(
            "remote_url",
            "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv?ref_type=heads",
        )
        self.local_path = cfg.get(
            "local_cache", os.path.join("./api/data", "exploit_db.csv")
        )
        self.commit_cache = cfg.get(
            "commit_cache", os.path.join("./api/data", "exploitdb_commit.txt")
        )
        self.repo_api = cfg.get(
            "repo_api",
            "https://gitlab.com/api/v4/projects/exploit-database%2Fexploitdb/repository/commits",
        )
        self.default_branch = cfg.get("default_branch", "main")

    async def fetch_data(self) -> pl.LazyFrame:
        """从 Exploit-DB 获取数据"""
        # df = pl.read_csv(self.remote_url)
        df = pl.scan_csv(self.remote_url)
        logger.info(f"成功从 {self.remote_url} 获取数据")
        return df

    def parse_data(self, raw_data: Any) -> list[dict[str, str]]:
        """解析 Exploit-DB 数据

        Args:
            raw_data: pl.LazyFrame（从远程获取）

        Returns:
            处理后的 CVE 数据列表
        """
        if not isinstance(raw_data, pl.LazyFrame):
            logger.warning(f"意外的 raw_data 类型: {type(raw_data)}，返回空列表")
            return []

        # 使用 Polars 处理数据
        # 基于 (cve_id, github_url) 去重
        df_processed = (
            raw_data.select(
                pl.struct(["codes", "file"])
                .map_elements(
                    lambda x: _process_codes(x["codes"], x["file"]),
                    return_dtype=pl.Utf8,
                )
                .alias("cve_id"),
                pl.col("description").alias("description"),
                pl.col("file")
                .map_elements(_process_file, return_dtype=pl.Utf8)
                .alias("github_url"),
            )
            .unique(subset=["cve_id", "github_url"], keep="first")
            .collect()
        )

        cve_list = df_processed.to_dicts()
        logger.info(
            f"去重后: {len(cve_list)} 条唯一 CVE 记录（总共 {len(cve_list)} 条）"
        )
        return cve_list

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

__all__ = ["CVEDataSource", "GitHubPocExpSource", "ExploitDBSource", "DATA_SOURCES"]
