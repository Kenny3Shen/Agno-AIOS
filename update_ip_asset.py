#!/usr/bin/env python3
"""
IP 资产数据更新脚本
从 ACL API 获取 IP 实体数据并进行聚合处理

使用方法:
    uv run update_ip_asset.py

环境变量:
    ACL_USERNAME: ACL API 用户名
    ACL_PASSWORD: ACL API 密码
"""

import os
import sys
import asyncio
import json
import time
import warnings
from datetime import datetime
import httpx
from loguru import logger
from dotenv import load_dotenv, set_key

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

load_dotenv()

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


async def update_ip_entities():
    """更新 IP 资产数据"""
    raw_path = "./api/data/raw_ip_entities.json"
    if os.path.exists(raw_path):
        logger.info("使用缓存的 raw_ip_entities.json")
        with open(raw_path, "r") as f:
            data = json.load(f)
        aggregate_ip_entities(data["items"])
        return

    async with httpx.AsyncClient(verify=False, timeout=60.0, follow_redirects=True) as client:
        token = os.getenv("TOKEN")
        if not token:
            login_url = "https://10.192.56.37:8088/api/user/login"
            login_data = {
                "username": os.getenv("ACL_USERNAME"),
                "password": os.getenv("ACL_PASSWORD"),
            }
            logger.info("正在登录 ACL API...")
            login_resp = await client.post(login_url, json=login_data)
            login_resp.raise_for_status()
            login_result = login_resp.json()
            if login_result.get("code") != 200:
                raise Exception("登录失败")
            token = login_result["data"]["token"]
            set_key(".env", "TOKEN", token)

        client.headers.update({"Token": token, "Content-Type": "application/json"})

        site_api = "https://10.192.56.37:8088/api/ip"
        params = {
            "page": 1,
            "size": 1_000_000,
            "tabIndex": 2,
            "ts": int(time.time() * 1000),
        }
        logger.info("正在从 ACL API 获取 IP 实体...")
        resp = await client.get(site_api, params=params)

        if resp.status_code == 401:
            logger.info("Token 已过期，重新登录")
            login_url = "https://10.192.56.37:8088/api/user/login"
            login_data = {
                "username": os.getenv("ACL_USERNAME"),
                "password": os.getenv("ACL_PASSWORD"),
            }
            login_resp = await client.post(login_url, json=login_data)
            login_resp.raise_for_status()
            login_result = login_resp.json()
            if login_result.get("code") != 200:
                raise Exception("登录失败")
            token = login_result["data"]["token"]
            set_key(".env", "TOKEN", token)
            client.headers.update({"Token": token, "Content-Type": "application/json"})
            resp = await client.get(site_api, params=params)

        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise Exception("获取 IP 数据失败")

        logger.info(f"成功获取 {len(data.get('items', []))} 条 IP 实体")
        
        os.makedirs(os.path.dirname(raw_path), exist_ok=True)
        with open(raw_path, "w") as f:
            json.dump(data, f, indent=4)

    aggregate_ip_entities(data["items"])


async def main():
    """主函数"""
    try:
        start_time = datetime.now()
        logger.info(f"IP asset update started at {start_time}")

        await update_ip_entities()

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        logger.info(
            f"IP asset update completed, duration={duration:.2f}s"
        )

        return 0
    except Exception as e:
        logger.exception(f"IP asset update failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
