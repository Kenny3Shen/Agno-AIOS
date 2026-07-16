from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field

from api.auth.claims import ADMIN_SCOPE
from api.auth.models import User
from api.auth.scopes import require_scope
from api.models.schemas import Url2MdRequest
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.collect_service import get_article, list_sources, run_crawl, search_articles
from api.services.collect_crawl_service import parse_and_store_url
from loguru import logger

router = APIRouter(prefix="/api/url2md", tags=["URL2MD"])


class CollectSearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = ""
    source_domain: str | None = None
    page: int = Field(1, ge=1)
    size: int = Field(20, ge=1, le=100)


class CollectCrawlRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    domains: list[str] | None = None
    max_links_per_source: int = Field(20, ge=1, le=50)
    max_articles_total: int = Field(80, ge=1, le=200)


@router.get("/sources")
async def collect_sources(
    _user: User = Depends(require_scope("collect:read")),
) -> dict:
    """List configured news source domains for Collect."""
    return {"status": 200, "items": await list_sources()}


@router.post("/articles/search")
async def search_collect_articles_route(
    request: CollectSearchRequest,
    _user: User = Depends(require_scope("collect:read")),
) -> dict:
    """Search persisted Collect articles (primary Collect UI path)."""
    try:
        items, total = await search_articles(
            query=request.query,
            source_domain=request.source_domain,
            page=request.page,
            size=request.size,
        )
        return {
            "status": 200,
            "items": items,
            "total": total,
            "page": request.page,
            "size": request.size,
        }
    except Exception as e:
        logger.error("Collect search error: {}", e)
        return {"status": 400, "message": f"错误:{e}"}


@router.get("/articles/{article_id}")
async def get_collect_article_route(
    article_id: int,
    _user: User = Depends(require_scope("collect:read")),
) -> dict:
    row = await get_article(article_id)
    if not row:
        return {"status": 404, "message": "article not found"}
    return {"status": 200, "item": row}


@router.post("/crawl")
async def crawl_collect_sources(
    request_ctx: Request,
    request: CollectCrawlRequest,
    user: User = Depends(require_scope(ADMIN_SCOPE)),
) -> dict:
    """Crawl configured source sites and upsert articles into the database."""
    try:
        stats = await run_crawl(
            domains=request.domains,
            max_links_per_source=request.max_links_per_source,
            max_articles_total=request.max_articles_total,
        )
        await record_audit_event_async(
            user,
            action="collect.crawl",
            resource_type="collect_articles",
            resource_id="crawl",
            metadata=stats,
            **audit_request_context(request_ctx),
        )
        return {"status": 200, "message": "crawl completed", **stats}
    except Exception as e:
        logger.error("Collect crawl error: {}", e)
        await record_audit_event_async(
            user,
            action="collect.crawl",
            resource_type="collect_articles",
            resource_id="crawl",
            status="failure",
            metadata={"error": str(e)},
            **audit_request_context(request_ctx),
        )
        return {"status": 500, "message": f"crawl failed: {e}"}


@router.post("/parse")
async def parse_url_to_markdown(
    request_ctx: Request,
    request: Url2MdRequest,
    user: User = Depends(require_scope("collect:write")),
) -> dict:
    """Parse a URL to Markdown and persist it for the Collect library."""
    try:
        record = await parse_and_store_url(request.url)
        await record_audit_event_async(
            user,
            action="collect.parse",
            resource_type="url2md",
            resource_id=request.url,
            metadata={"status": record.get("status"), "article_id": record.get("id")},
            **audit_request_context(request_ctx),
        )
        markdown = record.get("markdown") or ""
        if record.get("status") != "ok":
            return {
                "status": 400,
                "url": request.url,
                "message": record.get("error_message") or "parse failed",
                "markdown": [markdown] if markdown else [],
            }
        return {
            "status": 200,
            "url": request.url,
            "markdown": [markdown] if markdown else [],
            "title": record.get("title"),
            "source_domain": record.get("source_domain"),
            "id": record.get("id"),
        }
    except Exception as e:
        logger.error("URL to Markdown parsing error: {}", e)
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
