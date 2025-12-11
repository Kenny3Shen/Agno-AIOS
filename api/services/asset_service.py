import httpx
import os
import time
import warnings
from loguru import logger
from dotenv import load_dotenv, set_key
from ..utils.asset_utils import process_asset_data

warnings.filterwarnings("ignore", message="Unverified HTTPS request")

load_dotenv()


async def _get_acl_token(client: httpx.AsyncClient) -> str:
    """从 .env 获取 ACL API token 或登录获取新 token"""
    token = os.getenv("TOKEN")
    if token:
        return token
    
    login_url = "https://10.192.56.37:8088/api/user/login"
    login_data = {
        "username": os.getenv("ACL_USERNAME"),
        "password": os.getenv("ACL_PASSWORD"),
    }
    
    logger.info("正在登录 ACL API 获取新 token")
    login_resp = await client.post(login_url, json=login_data)
    login_resp.raise_for_status()
    login_result = login_resp.json()

    if login_result.get("code") != 200:
        logger.error("ACL 登录失败: {}", login_result.get("message"))
        raise Exception(f"登录失败: {login_result.get('message')}")

    token = login_result["data"]["token"]
    set_key(".env", "TOKEN", token)
    
    logger.info("成功登录 ACL API")
    return token


async def search_asset_by_fingerprint(fingerprint: str) -> list[dict]:
    """使用外部 ACL API 通过指纹搜索资产"""
    async with httpx.AsyncClient(
        verify=False, timeout=30.0, follow_redirects=True
    ) as client:
        token = await _get_acl_token(client)
        client.headers.update({"Token": token, "Content-Type": "application/json"})

        site_api = "https://10.192.56.37:8088/api/site"
        params = {
            "page": 1,
            "size": 1_000_000,
            "ts": int(time.time() * 1000),
            "finger.name": fingerprint,
        }
        
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
            raise Exception(f"获取资产数据失败: {data.get('message')}")

        results = data.get("items", [])
        logger.info(
            "找到 {} 个资产，指纹为 '{}'", len(results), fingerprint
        )
        processed_results = process_asset_data(results)
        return processed_results
