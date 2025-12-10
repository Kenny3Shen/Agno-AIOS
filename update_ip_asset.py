#!/usr/bin/env python3
"""
IP资产数据更新脚本
从ACL API获取IP实体数据并进行聚合处理

使用方法:
    uv run update_ip_asset.py

环境变量:
    ACL_USERNAME: ACL API用户名
    ACL_PASSWORD: ACL API密码
"""

import os
import sys
import asyncio
import json
import time
from datetime import datetime
import httpx
from loguru import logger

# 添加api目录到路径以便导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from api.utils.asset_utils import aggregate_ip_entities

# 配置日志
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL)
log_dir = os.getenv("LOG_DIR", "logs")
os.makedirs(log_dir, exist_ok=True)
logger.add(
    os.path.join(log_dir, "update_ip_asset.log"),
    level=LOG_LEVEL,
    rotation="10 MB",
    retention="10 days",
)

# ACL API配置
ACL_API_BASE = "https://10.192.56.37:8088/api"
ACL_USERNAME = os.getenv("ACL_USERNAME")
ACL_PASSWORD = os.getenv("ACL_PASSWORD")


async def login_to_acl(client: httpx.AsyncClient) -> str:
    """登录ACL API获取token
    
    Args:
        client: httpx客户端
        
    Returns:
        API token
    """
    login_url = f"{ACL_API_BASE}/user/login"
    login_data = {
        "username": ACL_USERNAME,
        "password": ACL_PASSWORD,
    }

    try:
        logger.info("Logging in to ACL API...")
        resp = await client.post(login_url, json=login_data)
        resp.raise_for_status()
        result = resp.json()

        if result.get("code") != 200:
            error_msg = result.get("message", "Unknown error")
            logger.error(f"ACL login failed: {error_msg}")
            raise Exception(f"Login failed: {error_msg}")

        token = result["data"]["token"]
        logger.info("Successfully logged in to ACL API")
        return token
    except httpx.HTTPError as e:
        logger.exception(f"HTTP error during login: {e}")
        raise
    except Exception as e:
        logger.exception(f"Login failed: {e}")
        raise


async def fetch_ip_entities(client: httpx.AsyncClient, token: str) -> list[dict]:
    """从ACL API获取IP实体数据
    
    Args:
        client: httpx客户端
        token: API token
        
    Returns:
        IP实体列表
    """
    ip_api = f"{ACL_API_BASE}/ip"
    params = {
        "page": 1,
        "size": 1_000_000,
        "tabIndex": 2,
        "ts": int(time.time() * 1000),
    }

    try:
        logger.info("Fetching IP entities from ACL API...")
        client.headers.update({"Token": token, "Content-Type": "application/json"})

        resp = await client.get(ip_api, params=params)
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 200:
            error_msg = data.get("message", "Unknown error")
            logger.error(f"Failed to fetch IP data: {error_msg}")
            raise Exception(f"Failed to fetch IP data: {error_msg}")

        items = data.get("items", [])
        logger.info(f"Successfully fetched {len(items)} IP entities")
        return items
    except httpx.HTTPError as e:
        logger.exception(f"HTTP error during IP fetch: {e}")
        raise
    except Exception as e:
        logger.exception(f"Failed to fetch IP entities: {e}")
        raise


async def save_raw_data(data: dict, filepath: str):
    """保存原始数据到文件
    
    Args:
        data: 要保存的数据
        filepath: 文件路径
    """
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        logger.info(f"Saved raw data to {filepath}")
    except Exception as e:
        logger.exception(f"Failed to save raw data: {e}")
        raise


async def update_ip_assets() -> int:
    """更新IP资产数据
    
    Returns:
        处理的IP实体数量
    """
    # 检查环境变量
    if not ACL_USERNAME or not ACL_PASSWORD:
        raise ValueError(
            "ACL_USERNAME and ACL_PASSWORD environment variables must be set"
        )

    try:
        async with httpx.AsyncClient(
            verify=False, timeout=60.0, follow_redirects=True
        ) as client:
            # 1. 登录获取token
            token = await login_to_acl(client)

            # 2. 获取IP实体数据
            items = await fetch_ip_entities(client, token)

            # 3. 保存原始数据
            raw_data_path = os.path.join("api", "data", "raw_ip_entities.json")
            await save_raw_data({"items": items}, raw_data_path)

            # 4. 聚合处理数据
            logger.info("Aggregating IP entities...")
            aggregate_ip_entities(items)
            logger.info("IP entities aggregation completed")

            return len(items)
    except Exception as e:
        logger.exception(f"IP asset update failed: {e}")
        raise


async def main():
    """主函数"""
    try:
        start_time = datetime.now()
        logger.info(f"IP asset update started at {start_time}")

        count = await update_ip_assets()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(
            f"IP asset update completed: processed={count} entities, "
            f"duration={duration:.2f}s"
        )

        return 0
    except Exception as e:
        logger.exception(f"IP asset update failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
