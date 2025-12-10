from fastapi import APIRouter
from api.models.schemas import AssetSearchRequest
from api.services.asset_service import search_asset_by_fingerprint, update_ip_entities
from loguru import logger

router = APIRouter(prefix="/api/asset", tags=["Asset"])


@router.post("/search")
async def search_asset(request: AssetSearchRequest):
    """Search for IP information based on asset info"""
    try:
        items = await search_asset_by_fingerprint(request.fingerprint)
        # Return all items for client-side pagination
        return {
            "status": 200,
            "items": items,
            "total": len(items),
        }
    except Exception as e:
        logger.error(f"Error searching assets: {e}")
        return {"status": 400, "message": f"error:{e}"}


@router.post("/update")
async def update_ip_entities_route():
    """Update IP entities from external source"""
    try:
        await update_ip_entities()
        return {"status": 200, "message": "IP entities updated successfully."}
    except Exception as e:
        logger.error(f"Error updating IP entities: {e}")
        return {"status": 400, "message": f"error:{e}"}
