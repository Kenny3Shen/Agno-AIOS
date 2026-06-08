#!/home/shenss/python/fastapi/.venv/bin/python3
"""NDR API 基础方法"""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(override=True)


def _headers() -> dict[str, str]:
    return {
        "API-Token": os.getenv("NDR_API_TOKEN", ""),
        "Content-Type": "application/json;charset=UTF-8",
    }


def _api_url() -> str:
    return os.getenv("NDR_API_URL", "")


async def post_jsonrpc(method: str, params: dict[str, Any]) -> dict[str, Any]:
    """发送 JSON-RPC 请求并返回 result。"""
    if not _api_url():
        raise RuntimeError("NDR_API_URL 未配置")
    if not _headers().get("API-Token"):
        raise RuntimeError("NDR_API_TOKEN 未配置")

    body = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": f"intranet-skill-{int(time.time() * 1000)}",
    }

    async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
        resp = await client.post(url=_api_url(), json=body, headers=_headers())
        resp.raise_for_status()
        res_json = resp.json()
        return res_json.get("result", {})
