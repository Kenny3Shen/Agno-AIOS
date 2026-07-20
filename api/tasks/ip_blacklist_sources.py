"""IP blacklist threat-intel source loaders."""

from __future__ import annotations

import ipaddress
import re
import tomllib
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

import httpx
import polars as pl
from anyio import Path as AsyncPath
from loguru import logger

from api.config import get_settings
from api.services.runtime_env import load_runtime_env_async

_IP_OR_CIDR_RE = re.compile(
    r"^(?:"
    r"(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?"  # IPv4 / CIDR
    r"|"
    r"[0-9a-fA-F:]+(?:/\d{1,3})?"  # IPv6 / CIDR (loose; validated below)
    r")$"
)


def _cache_file(filename: str) -> str:
    return str(Path(get_settings().ip_blacklist_data_dir) / filename)


def normalize_indicator(value: str) -> str | None:
    """Return a canonical IP or CIDR string, or None if invalid."""
    text = (value or "").strip()
    if not text or text.startswith("#") or text.startswith(";"):
        return None
    # FireHOL comments sometimes trail entries.
    text = text.split()[0].strip()
    if not _IP_OR_CIDR_RE.match(text):
        return None
    try:
        if "/" in text:
            network = ipaddress.ip_network(text, strict=False)
            return str(network)
        address = ipaddress.ip_address(text)
        return str(address)
    except ValueError:
        return None


def normalize_ip_blacklist_dataframe(dataframe: pl.DataFrame) -> pl.DataFrame:
    if dataframe.is_empty():
        return dataframe
    required = {"indicator", "source"}
    missing = required.difference(dataframe.columns)
    if missing:
        logger.warning("IP blacklist data missing columns: {}", sorted(missing))
        return pl.DataFrame(
            schema={
                "indicator": pl.String,
                "indicator_type": pl.String,
                "source": pl.String,
                "list_name": pl.String,
                "description": pl.String,
            }
        )
    rows: list[dict[str, str]] = []
    for record in dataframe.to_dicts():
        indicator = normalize_indicator(str(record.get("indicator") or ""))
        source = str(record.get("source") or "").strip()
        if not indicator or not source:
            continue
        indicator_type = "cidr" if "/" in indicator else "ip"
        rows.append(
            {
                "indicator": indicator,
                "indicator_type": indicator_type,
                "source": source,
                "list_name": str(record.get("list_name") or "").strip(),
                "description": str(record.get("description") or "").strip(),
            }
        )
    if not rows:
        return pl.DataFrame(
            schema={
                "indicator": pl.String,
                "indicator_type": pl.String,
                "source": pl.String,
                "list_name": pl.String,
                "description": pl.String,
            }
        )
    return pl.DataFrame(rows).unique(subset=["indicator", "source"], keep="first")


class IpBlacklistSource(ABC):
    source_id: str

    @abstractmethod
    async def fetch_data(self) -> str:
        pass

    @abstractmethod
    def parse_data(self, raw_data: Any) -> pl.DataFrame:
        pass

    @abstractmethod
    def get_local_cache_path(self) -> str:
        pass


async def load_ip_blacklist_source_config() -> dict[str, Any]:
    await load_runtime_env_async()
    config_path = AsyncPath(get_settings().ip_blacklist_source_config_path)
    try:
        content = await config_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        data = tomllib.loads(content)
    except tomllib.TOMLDecodeError:
        logger.warning("无法解析 IP 黑名单源配置: {}", config_path)
        return {}
    return data if isinstance(data, dict) else {}


class FireholLevel1Source(IpBlacklistSource):
    """FireHOL level1 netset: high-confidence attack / abuse aggregates."""

    source_id = "firehol-level1"

    def __init__(self, config: dict[str, Any] | None = None):
        cfg = (config or {}).get("firehol_level1", {})
        self.remote_url = cfg.get(
            "remote_url",
            "https://raw.githubusercontent.com/firehol/blocklist-ipsets/master/firehol_level1.netset",
        )
        self.local_path = cfg.get(
            "local_cache", _cache_file("firehol_level1.netset")
        )
        self.etag_cache = cfg.get("etag_cache", _cache_file("firehol_level1.etag"))
        self.list_name = str(cfg.get("source") or self.source_id)
        self.description = str(
            cfg.get("description")
            or "FireHOL level1 aggregate (Spamhaus DROP/EDROP, DShield, Feodo, …)"
        )

    async def fetch_data(self) -> str:
        headers: dict[str, str] = {"User-Agent": "TAIS-IP-Blacklist/1.0"}
        etag_path = Path(self.etag_cache)
        if etag_path.is_file():
            try:
                etag = etag_path.read_text(encoding="utf-8").strip()
                if etag:
                    headers["If-None-Match"] = etag
            except OSError:
                pass
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            resp = await client.get(self.remote_url, headers=headers)
            if resp.status_code == 304:
                cache = Path(self.local_path)
                if cache.is_file():
                    logger.info("IP blacklist {} not modified (304), using cache", self.source_id)
                    return cache.read_text(encoding="utf-8", errors="replace")
            resp.raise_for_status()
            text = resp.text
            logger.info("成功从 {} 获取 IP 黑名单 ({} bytes)", self.remote_url, len(text))
            etag = resp.headers.get("etag")
            if etag:
                try:
                    etag_path.parent.mkdir(parents=True, exist_ok=True)
                    etag_path.write_text(etag, encoding="utf-8")
                except OSError as exc:
                    logger.debug("无法写入 etag 缓存: {}", exc)
            return text

    def parse_data(self, raw_data: Any) -> pl.DataFrame:
        if not isinstance(raw_data, str) or not raw_data:
            return pl.DataFrame()
        rows: list[dict[str, str]] = []
        for line in raw_data.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            indicator = normalize_indicator(line)
            if not indicator:
                continue
            rows.append(
                {
                    "indicator": indicator,
                    "indicator_type": "cidr" if "/" in indicator else "ip",
                    "source": self.source_id,
                    "list_name": self.list_name,
                    "description": self.description,
                }
            )
        if not rows:
            return pl.DataFrame()
        df = pl.DataFrame(rows)
        normalized = normalize_ip_blacklist_dataframe(df)
        logger.info("FireHOL level1 解析有效指标 {} 条", normalized.height)
        return normalized

    def get_local_cache_path(self) -> str:
        return self.local_path


def build_sources(config: dict[str, Any] | None = None) -> list[IpBlacklistSource]:
    cfg = config or {}
    # Default / configured FireHOL level1 (high-confidence aggregate).
    if not cfg or "firehol_level1" in cfg:
        return [FireholLevel1Source(cfg)]
    # Unknown sections: still attempt FireHOL with empty section defaults.
    logger.warning("IP 黑名单配置未包含 firehol_level1，使用默认源")
    return [FireholLevel1Source({})]


__all__ = [
    "FireholLevel1Source",
    "IpBlacklistSource",
    "build_sources",
    "load_ip_blacklist_source_config",
    "normalize_indicator",
    "normalize_ip_blacklist_dataframe",
]
