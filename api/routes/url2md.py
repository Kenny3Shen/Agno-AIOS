from fastapi import APIRouter
from api.models.schemas import Url2MdRequest
from api.services.url2md_service import fetch_and_parse_url
from loguru import logger

router = APIRouter(prefix="/api/url2md", tags=["URL2MD"])

@router.post("/parse")
async def parse_url_to_markdown(request: Url2MdRequest) -> dict:
    """Parse the content of a given URL and convert it to Markdown format."""
    try:
        url = request.url.strip()
        if not url:
            return {"status": 400, "message": "URL不能为空"}

        markdown_content = fetch_and_parse_url([url])

        return {
            "status": 200,
            "url": url,
            "markdown": markdown_content,
        }
    except Exception as e:
        logger.error(f"URL to Markdown parsing error: {e}")
        return {"status": 400, "message": f"错误:{e}"}