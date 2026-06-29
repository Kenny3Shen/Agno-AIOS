import asyncio
import time
import warnings

import httpx
from loguru import logger

from api.config import get_settings
from ..utils.asset_utils import process_asset_data

warnings.filterwarnings("ignore", message="Unverified HTTPS request")


async def relogin(client: httpx.AsyncClient, lock: asyncio.Lock) -> httpx.AsyncClient:
    logger.info("Token 过期，正在重新登录获取新 Token")
    async with lock:
        settings = get_settings()
        login_url = "https://10.192.56.37:8088/api/user/login"
        login_data = {
            "username": settings.acl_username,
            "password": settings.acl_password.get_secret_value(),
        }
        login_resp = await client.post(login_url, json=login_data)
        login_resp.raise_for_status()
        login_result = login_resp.json()
        if login_result.get("code") != 200:
            raise Exception("登录失败")
        token = login_result["data"]["token"]
        # do not write to .env at runtime; only update in-memory header
        client.headers.update({"Token": token, "Content-Type": "application/json"})
        return client


async def search_asset_by_fingerprint(
    client: httpx.AsyncClient, fingerprint: str, lock: asyncio.Lock
) -> list[dict]:
    """使用外部 ACL API 通过指纹搜索资产，使用 lock 来序列化 token 刷新。"""
    site_api = "https://10.192.56.37:8088/api/site"
    params = {
        "page": 1,
        "size": 1_000_000,
        "ts": int(time.time() * 1000),
        "finger.name": fingerprint,
    }

    resp = await client.get(site_api, params=params)
    data = resp.json()

    if resp.status_code == 401 or "not login" in data.get("message", ""):
        client = await relogin(client, lock)
        resp = await client.get(site_api, params=params)
        resp.raise_for_status()

    if data.get("code") != 200:
        raise Exception(
            f"HTTP {resp.status_code} 获取资产数据失败: {data.get('message')}"
        )

    results = data.get("items", [])
    logger.info("找到 {} 个资产，指纹为 '{}'", len(results), fingerprint)
    processed_results = process_asset_data(results)
    return processed_results

async def search_asset_by_ip(
    client: httpx.AsyncClient, ip: str, lock: asyncio.Lock
) -> list[dict]:
    """使用外部 ACL API 通过指纹搜索资产，使用 lock 来序列化 token 刷新。"""
    site_api = "https://10.192.56.37:8088/api/site"
    params = {
        "page": 1,
        "size": 1_000_000,
        "ts": int(time.time() * 1000),
        "ip": ip,
    }

    resp = await client.get(site_api, params=params)
    data = resp.json()

    if resp.status_code == 401 or "not login" in data.get("message", ""):
        client = await relogin(client, lock)
        resp = await client.get(site_api, params=params)
        resp.raise_for_status()

    if data.get("code") != 200:
        raise Exception(
            f"HTTP {resp.status_code} 获取资产数据失败: {data.get('message')}"
        )

    results = data.get("items", [])
    logger.info("找到 {} 个资产，IP 为 '{}'", len(results), ip)
    processed_results = process_asset_data(results)
    return processed_results
