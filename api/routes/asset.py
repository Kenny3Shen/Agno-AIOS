from fastapi import APIRouter, Depends
from api.dependencies import get_asset_client, get_asset_lock
import asyncio
import httpx
from api.models.schemas import AssetSearchRequest
from api.services.asset_service import search_asset_by_fingerprint
from loguru import logger

router = APIRouter(prefix="/api/asset", tags=["Asset"])


@router.post("/search")
async def search_asset(
    request: AssetSearchRequest,
    client: httpx.AsyncClient = Depends(get_asset_client),
    asset_lock: asyncio.Lock = Depends(get_asset_lock),
) -> dict:
    """根据资产信息搜索 IP 信息"""
    try:
        items = await search_asset_by_fingerprint(client, request.fingerprint, asset_lock)
        return {
            "status": 200,
            "items": items,
            "total": len(items),
        }
    except Exception as e:
        logger.error(f"搜索资产错误: {e}")
        return {"status": 400, "message": f"错误:{e}"}
