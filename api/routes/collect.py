from fastapi import APIRouter, Depends, Request

from api.auth.models import User
from api.auth.scopes import require_scope
from api.models.schemas import Url2MdRequest
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.url2md_service import fetch_and_parse_url
from loguru import logger

router = APIRouter(prefix="/api/url2md", tags=["URL2MD"])


@router.post("/parse")
async def parse_url_to_markdown(
    request_ctx: Request,
    request: Url2MdRequest,
    user: User = Depends(require_scope("collect:write")),
) -> dict:
    """Parse the content of a given URL and convert it to Markdown format."""
    try:
        markdown_content = await fetch_and_parse_url([request.url])
        await record_audit_event_async(
            user,
            action="collect.parse",
            resource_type="url2md",
            resource_id=request.url,
            **audit_request_context(request_ctx),
        )

        return {
            "status": 200,
            "url": request.url,
            "markdown": markdown_content,
        }
    except Exception as e:
        logger.error(f"URL to Markdown parsing error: {e}")
        await record_audit_event_async(
            user,
            action="collect.parse",
            resource_type="url2md",
            resource_id=request.url,
            status="failure",
            metadata={"error": str(e)},
            **audit_request_context(request_ctx),
        )
        return {"status": 400, "message": f"错误:{e}"}
