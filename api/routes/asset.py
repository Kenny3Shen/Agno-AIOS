from fastapi import APIRouter
from api.models.schemas import AssetSearchRequest
from api.services.asset_service import search_asset_by_fingerprint
from loguru import logger

router = APIRouter(prefix="/api/asset", tags=["Asset"])


@router.post("/search")
async def search_asset(request: AssetSearchRequest):
    """根据资产信息搜索 IP 信息"""
    try:
        items = await search_asset_by_fingerprint(request.fingerprint)
        return {
            "status": 200,
            "items": items,
            "total": len(items),
        }
    except Exception as e:
        logger.error(f"搜索资产错误: {e}")
        return {"status": 400, "message": f"错误:{e}"}
