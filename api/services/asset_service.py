import httpx
import os
import time
from datetime import datetime, timedelta
from loguru import logger
from ..utils.asset_utils import process_asset_data

# Global cache for ACL session
_acl_session_cache = {
    "token": None,
    "expires_at": None,
}

# Token validity duration (default 1 hour)
TOKEN_EXPIRY_MINUTES = 60


async def _get_acl_token(client: httpx.AsyncClient) -> str:
    """Get or refresh ACL API token with caching"""
    global _acl_session_cache
    
    # Check if token is valid
    if (
        _acl_session_cache["token"]
        and _acl_session_cache["expires_at"]
        and datetime.now() < _acl_session_cache["expires_at"]
    ):
        logger.debug("Using cached ACL token")
        return _acl_session_cache["token"]
    
    # Login to get new token
    login_url = "https://10.192.56.37:8088/api/user/login"
    login_data = {
        "username": os.getenv("ACL_USERNAME"),
        "password": os.getenv("ACL_PASSWORD"),
    }
    login_resp = await client.post(login_url, json=login_data)
    login_resp.raise_for_status()
    login_result = login_resp.json()

    if login_result.get("code") != 200:
        logger.error("ACL login failed: {}", login_result.get("message"))
        raise Exception(f"Login failed: {login_result.get('message')}")

    token = login_result["data"]["token"]
    _acl_session_cache["token"] = token
    _acl_session_cache["expires_at"] = datetime.now() + timedelta(minutes=TOKEN_EXPIRY_MINUTES)
    logger.info("Successfully logged in to ACL API, token cached for {} minutes", TOKEN_EXPIRY_MINUTES)
    return token


async def search_asset_by_fingerprint(fingerprint: str) -> list[dict]:
    """Search assets by fingerprint using external ACL API"""
    try:
        async with httpx.AsyncClient(
            verify=False, timeout=30.0, follow_redirects=True
        ) as client:
            # Get cached or new token
            token = await _get_acl_token(client)
            client.headers.update({"Token": token, "Content-Type": "application/json"})

            # Search for assets by fingerprint
            site_api = "https://10.192.56.37:8088/api/site"
            params = {
                "page": 1,
                "size": 1_000_000,
                "ts": int(time.time() * 1000),
                "finger.name": fingerprint,
            }
            resp = await client.get(site_api, params=params)
            resp.raise_for_status()
            data = resp.json()

            if data.get("code") != 200:
                logger.error("Failed to fetch site data: {}", data.get("message"))
                raise Exception(f"Failed to fetch site data: {data.get('message')}")

            results = data.get("items", [])
            logger.info(
                "Found {} assets for fingerprint '{}'", len(results), fingerprint
            )
            # Use cached ip_df_agg for efficient processing
            processed_results = process_asset_data(results)
            return processed_results
    except httpx.HTTPError as e:
        logger.error("HTTP error during asset search: {}", e)
        raise Exception(f"Network error: {str(e)}")
    except Exception as e:
        logger.error("Error searching assets: {}", e)
        raise
