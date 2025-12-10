#!/usr/bin/env python3
"""
Utilities and data source classes for CVE updating.

Move helpers and data source classes here so `update_cve.py` keeps the core workflow.
"""

import os
import re
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple

import httpx
import polars as pl
from loguru import logger


class CVEDataSource(ABC):
    """CVE数据源抽象基类"""

    @abstractmethod
    async def fetch_data(self):
        """获取原始数据"""
        pass

    @abstractmethod
    def parse_data(self, raw_data) -> List[Dict[str, str]]:
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

    def compare_with_local(
        self, new_data: List[Dict[str, str]], old_data: List[Dict[str, str]]
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
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
            f"Data comparison: local={len(old_data)}, remote={len(new_data)}, "
            f"increment={len(increment_data)}, to_delete={len(deleted_data)}"
        )

        return increment_data, deleted_data


class GitHubPocExpSource(CVEDataSource):
    """从GitHub PocOrExp仓库获取CVE数据"""

    def __init__(self):
        self.remote_url = "https://raw.githubusercontent.com/ycdxsb/PocOrExp_in_Github/refs/heads/main/PocOrExp.md"
        self.local_path = os.path.join("./api/data", "github_cve_cache.csv")

    async def fetch_data(self) -> str:
        """从GitHub获取数据"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(self.remote_url)
                resp.raise_for_status()
                logger.info(f"Successfully fetched data from {self.remote_url}")
                return resp.text
        except Exception as e:
            logger.exception(f"Failed to fetch data from {self.remote_url}: {e}")
            raise

    def parse_data(self, raw_data: str) -> List[Dict[str, str]]:
        """解析Markdown格式的CVE数据"""
        if not raw_data:
            logger.warning("parse_data called with empty text")
            return []

        lines = raw_data.strip().split("\n")
        cve_data = []
        current_cve = None
        current_desc = []

        # 正则表达式
        cve_pattern = re.compile(r"^##\s*(CVE-\d{4}-\d+)")
        url_pattern = re.compile(r"-\s*\[(https://github\.com/[^\]]+)\]")

        for line in lines:
            line = line.strip()

            # 匹配CVE标题
            cve_match = cve_pattern.match(line)
            if cve_match:
                if current_cve and not any(
                    d["cve_id"] == current_cve for d in cve_data
                ):
                    cve_data.append(
                        {
                            "cve_id": current_cve,
                            "description": "\n".join(current_desc).strip(),
                            "github_url": "",
                        }
                    )

                current_cve = cve_match.group(1)
                current_desc = []
                continue

            # 匹配GitHub URL
            url_match = url_pattern.match(line)
            if url_match:
                if current_cve:
                    url = url_match.group(1)
                    cve_data.append(
                        {
                            "cve_id": current_cve,
                            "description": "\n".join(current_desc).strip(),
                            "github_url": url,
                        }
                    )
                continue

            if (
                current_cve
                and not line.startswith("##")
                and not line.startswith("![")
                and line
            ):
                current_desc.append(line)

        if current_cve and not any(d["cve_id"] == current_cve for d in cve_data):
            cve_data.append(
                {
                    "cve_id": current_cve,
                    "description": "\n".join(current_desc).strip(),
                    "github_url": "",
                }
            )

        # 使用Polars进行去重，基于(cve_id, github_url)
        if cve_data:
            df = pl.DataFrame(cve_data)
            df_unique = df.unique(subset=["cve_id", "github_url"], keep="first")
            cve_data = df_unique.to_dicts()
            logger.info(f"After deduplication: {len(cve_data)} unique CVE entries")
        
        logger.info(f"Parsed {len(cve_data)} CVE entries from data")
        return cve_data

    def get_local_cache_path(self) -> str:
        """获取本地缓存文件路径"""
        return self.local_path


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
        self.remote_url = "https://gitlab.com/exploit-database/exploitdb/-/raw/main/files_exploits.csv?ref_type=heads"
        self.local_path = os.path.join("./api/data", "exploit_db.csv")

    async def fetch_data(self) -> pl.DataFrame:
        """从Exploit-DB获取数据"""
        try:
            df = pl.read_csv(self.remote_url)
            logger.info(f"Successfully fetched data from {self.remote_url}")
            return df
        except Exception as e:
            logger.exception(f"Failed to fetch data from {self.remote_url}: {e}")
            raise

    def parse_data(self, raw_data) -> List[Dict[str, str]]:
        """解析Exploit-DB数据

        Args:
            raw_data: 可以是pl.DataFrame（从远程获取）或list[dict]（从缓存加载）

        Returns:
            处理后的CVE数据列表
        """
        # 如果是空列表，直接返回
        if isinstance(raw_data, list):
            if not raw_data:
                return []
            # 如果是dict列表且已经有正确的字段，直接返回（从缓存加载）
            if "cve_id" in raw_data[0]:
                logger.info(f"Loaded {len(raw_data)} CVE entries from cache")
                return raw_data

        # 如果不是DataFrame，返回空列表
        if not isinstance(raw_data, pl.DataFrame):
            logger.warning(
                f"Unexpected raw_data type: {type(raw_data)}, returning empty list"
            )
            return []

        # 检查DataFrame是否为空
        if raw_data.is_empty():
            return []

        df_processed = raw_data.select(
            [
                pl.struct(["codes", "file"]) 
                .map_elements(lambda x: _process_codes(x["codes"], x["file"]), return_dtype=pl.Utf8)
                .alias("cve_id"),
                pl.col("description").alias("description"),
                pl.col("file").map_elements(_process_file, return_dtype=pl.Utf8).alias("github_url"),
            ]
        )

        # 基于(cve_id, github_url)去重
        df_unique = df_processed.unique(subset=["cve_id", "github_url"], keep="first")
        cve_list = df_unique.to_dicts()
        logger.info(f"After deduplication: {len(cve_list)} unique CVE entries (from {len(df_processed)} total)")
        return cve_list

    def get_local_cache_path(self) -> str:
        """获取本地缓存文件路径"""
        return self.local_path


# 注册表
DATA_SOURCES = {
    "github": GitHubPocExpSource,
    "exploit-db": ExploitDBSource,
}

__all__ = ["CVEDataSource", "GitHubPocExpSource", "ExploitDBSource", "DATA_SOURCES"]
