"""Collect / URL→Markdown HTTP routes (security news library + crawl SSE)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from loguru import logger
from sse_starlette.sse import EventSourceResponse

from api.auth.claims import ADMIN_SCOPE
from api.auth.models import User
from api.auth.scopes import require_scope
from api.models.schemas import Url2MdRequest
from api.services.audit_service import audit_request_context, record_audit_event_async
from api.services.collect_service import (
    get_article,
    library_status_counts,
    list_sources,
    reparse_article,
    reparse_failed_articles,
    run_crawl,
    search_articles,
)
from api.services.collect_crawl_service import (
    CollectCrawlAlreadyRunningError,
    extract_cve_ids,
    parse_and_store_url,
)
from api.utils.pagination import pagination_meta

router = APIRouter(prefix="/api/url2md", tags=["URL2MD"])


class CollectSearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = ""
    source_domain: str | None = None
    # ok (default) | error | all
    status: str = Field("ok", pattern=r"^(ok|error|all)$")
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
    items = await list_sources()
    return {
        "data": items,
        "meta": pagination_meta(page=1, limit=max(len(items), 1), total_count=len(items)),
    }


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
            status=request.status,
            page=request.page,
            size=request.size,
        )
        return {
            "data": items,
            "meta": pagination_meta(page=request.page, limit=request.size, total_count=total),
        }
    except Exception as e:
        logger.error("Collect search error: {}", e)
        raise HTTPException(status_code=400, detail=f"错误:{e}") from e


class CollectBulkReparseRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    source_domain: str | None = None
    limit: int = Field(10, ge=1, le=50)


@router.post("/articles/reparse-failed")
async def reparse_failed_collect_articles_route(
    request_ctx: Request,
    request: CollectBulkReparseRequest,
    user: User = Depends(require_scope("collect:write")),
) -> dict:
    """Re-fetch the newest failed Collect articles (bounded batch)."""
    try:
        stats = await reparse_failed_articles(
            source_domain=request.source_domain,
            limit=request.limit,
        )
        await record_audit_event_async(
            user,
            action="collect.reparse_failed",
            resource_type="collect_articles",
            resource_id="bulk",
            metadata=stats,
            **audit_request_context(request_ctx),
        )
        return {"message": "reparse completed", **stats}
    except Exception as e:
        logger.error("Collect bulk reparse error: {}", e)
        await record_audit_event_async(
            user,
            action="collect.reparse_failed",
            resource_type="collect_articles",
            resource_id="bulk",
            status="failure",
            metadata={"error": str(e)},
            **audit_request_context(request_ctx),
        )
        raise HTTPException(status_code=500, detail=f"bulk reparse failed: {e}") from e


@router.get("/stats")
async def collect_library_stats(
    source_domain: str | None = None,
    _user: User = Depends(require_scope("collect:read")),
) -> dict:
    """Ok/error totals for Collect library health badges."""
    counts = await library_status_counts(source_domain=source_domain)
    return counts


@router.get("/articles/{article_id}")
async def get_collect_article_route(
    article_id: int,
    _user: User = Depends(require_scope("collect:read")),
) -> dict:
    row = await get_article(article_id)
    if not row:
        raise HTTPException(status_code=404, detail="article not found")
    return row


@router.post("/articles/{article_id}/reparse")
async def reparse_collect_article_route(
    article_id: int,
    request_ctx: Request,
    user: User = Depends(require_scope("collect:write")),
) -> dict:
    """Re-fetch a stored URL (retry failed crawls / refresh content)."""
    try:
        record = await reparse_article(article_id)
        await record_audit_event_async(
            user,
            action="collect.reparse",
            resource_type="collect_articles",
            resource_id=str(article_id),
            metadata={
                "status": record.get("status"),
                "url": record.get("url"),
            },
            **audit_request_context(request_ctx),
        )
        if record.get("status") != "ok":
            raise HTTPException(
                status_code=400,
                detail=record.get("error_message") or "reparse failed",
            )
        return record
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Collect reparse error: {}", e)
        await record_audit_event_async(
            user,
            action="collect.reparse",
            resource_type="collect_articles",
            resource_id=str(article_id),
            status="failure",
            metadata={"error": str(e)},
            **audit_request_context(request_ctx),
        )
        raise HTTPException(status_code=400, detail=f"reparse failed: {e}") from e


def _sse_payload(event: str, data: Mapping[str, Any]) -> dict[str, str]:
    return {
        "event": event,
        "data": json.dumps(dict(data), ensure_ascii=False, default=str),
    }


@router.post("/crawl")
async def crawl_collect_sources(
    request_ctx: Request,
    request: CollectCrawlRequest,
    user: User = Depends(require_scope(ADMIN_SCOPE)),
    stream: bool = Query(False, description="Stream stage progress as SSE"),
):
    """Crawl configured source sites and upsert articles into the database.

    With ``stream=true``, emit SSE stage progress (start → discover → select →
    fetch → database → done). Synchronous JSON response remains the default.
    """
    if stream:
        return await _crawl_collect_stream(request_ctx, request, user)
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
        return {"message": "crawl completed", **stats}
    except CollectCrawlAlreadyRunningError as e:
        logger.warning("Collect crawl rejected: {}", e)
        raise HTTPException(status_code=409, detail=str(e)) from e
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
        raise HTTPException(status_code=500, detail=f"crawl failed: {e}") from e


async def _crawl_collect_stream(
    request_ctx: Request,
    request: CollectCrawlRequest,
    user: User,
) -> EventSourceResponse:
    queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

    async def on_progress(event: Mapping[str, Any]) -> None:
        await queue.put(dict(event))

    async def worker() -> None:
        try:
            stats = await run_crawl(
                domains=request.domains,
                max_links_per_source=request.max_links_per_source,
                max_articles_total=request.max_articles_total,
                on_progress=on_progress,
            )
            await record_audit_event_async(
                user,
                action="collect.crawl",
                resource_type="collect_articles",
                resource_id="crawl",
                metadata={**stats, "stream": True},
                **audit_request_context(request_ctx),
            )
        except CollectCrawlAlreadyRunningError as exc:
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 409,
                }
            )
        except asyncio.CancelledError:
            # Client disconnect / stop button — do not audit as crawl failure.
            logger.info("Collect streamed crawl cancelled")
            raise
        except Exception as exc:
            logger.exception("Collect streamed crawl failed: {}", exc)
            await record_audit_event_async(
                user,
                action="collect.crawl",
                resource_type="collect_articles",
                resource_id="crawl",
                status="failure",
                metadata={"error": str(exc), "stream": True},
                **audit_request_context(request_ctx),
            )
            await queue.put(
                {
                    "stage": "done",
                    "status": "failed",
                    "message": str(exc),
                    "error": str(exc),
                    "code": 500,
                }
            )
        finally:
            await queue.put(None)

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        task = asyncio.create_task(worker(), name="collect-crawl-progress")
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                stage = str(item.get("stage") or "progress")
                status = str(item.get("status") or "running")
                if status == "failed":
                    yield _sse_payload("progress.failed", item)
                elif stage == "done" and status == "completed":
                    yield _sse_payload("progress.done", item)
                else:
                    yield _sse_payload("progress", item)
        finally:
            if not task.done():
                task.cancel()
                try:
                    await task
                except (asyncio.CancelledError, Exception):
                    pass

    return EventSourceResponse(event_generator())


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
            raise HTTPException(
                status_code=400,
                detail=record.get("error_message") or "parse failed",
            )
        cve_ids = record.get("cve_ids") or extract_cve_ids(
            str(record.get("title") or ""),
            str(record.get("summary") or ""),
            str(markdown or ""),
        )
        return {
            "url": request.url,
            "markdown": markdown,
            "title": record.get("title"),
            "source_domain": record.get("source_domain"),
            "id": record.get("id"),
            "cve_ids": cve_ids,
            "summary": record.get("summary") or "",
        }
    except HTTPException:
        raise
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
        raise HTTPException(status_code=400, detail=f"错误:{e}") from e
