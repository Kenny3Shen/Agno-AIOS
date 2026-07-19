"""Low-risk, generally useful FastMCP tools.

Secrets and transport destinations are deliberately kept in server-side
configuration.  MCP callers can tune bounded delivery behaviour, but cannot
turn this notification tool into a general-purpose HTTP client.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Annotated, Any, Literal
from urllib.parse import urlparse

import httpx
from fastmcp import FastMCP
from loguru import logger
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from api.utils.json import dumps_bytes


CardTemplate = Literal[
    "blue",
    "wathet",
    "turquoise",
    "green",
    "yellow",
    "orange",
    "red",
    "carmine",
    "violet",
    "purple",
    "indigo",
    "grey",
]
FailureReason = Literal[
    "configuration",
    "validation",
    "network",
    "timeout",
    "rate_limited",
    "upstream",
    "invalid_response",
]

FEISHU_PAYLOAD_LIMIT_BYTES = 30 * 1024
DEFAULT_REQUEST_TIMEOUT_SECONDS = 8.0
MAX_REQUEST_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_RETRIES = 2
MAX_RETRIES = 2
MAX_RETRY_DELAY_SECONDS = 5.0
# The FastMCP timeout must accommodate the largest public retry configuration:
# three total requests, two bounded retry waits, and a small scheduling/JSON
# serialization margin.  Each request is also bounded as a whole below.
TOOL_TIMEOUT_SECONDS = (
    (MAX_RETRIES + 1) * MAX_REQUEST_TIMEOUT_SECONDS
    + MAX_RETRIES * MAX_RETRY_DELAY_SECONDS
    + 5.0
)
_TRUNCATION_SUFFIX = "\n\n…（内容因飞书消息大小限制已截断）"
_ALLOWED_TEMPLATES = frozenset(CardTemplate.__args__)
_RETRYABLE_HTTP_STATUSES = frozenset({408, 429, 500, 502, 503, 504})
_RETRYABLE_FEISHU_CODES = frozenset({11232})


class FeishuNotifyResult(BaseModel):
    """Stable machine-readable outcome for a Feishu notification request."""

    code: int = Field(description="0 表示成功；负数表示本地发送失败。")
    msg: str = Field(description="适合展示给操作员的简短结果说明。", max_length=500)
    status: Literal["sent", "failed"] = Field(description="本次通知的最终状态。")
    attempts: int = Field(ge=0, description="实际已发出的 HTTP 请求次数。")
    content_truncated: bool = Field(
        description="是否为满足飞书消息大小限制而截断了 Markdown 内容。"
    )
    http_status: int | None = Field(
        default=None, description="上游 HTTP 状态码；尚未发出请求时为空。"
    )
    feishu_code: int | None = Field(
        default=None, description="飞书响应中的业务状态码；未返回时为空。"
    )
    failure_reason: FailureReason | None = Field(
        default=None, description="失败分类；成功时为空。"
    )
    retryable: bool = Field(
        default=False, description="失败是否通常可在稍后重新调用工具后恢复。"
    )


basic_mcp = FastMCP("Basic", mask_error_details=True)


def _make_payload(title: str, content: str, template: CardTemplate) -> dict[str, Any]:
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": template,
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": content}}
            ],
        },
    }


def _payload_size(title: str, content: str, template: CardTemplate) -> int:
    return len(dumps_bytes(_make_payload(title, content, template)))


def _fit_content_to_payload_limit(
    title: str, content: str, template: CardTemplate
) -> tuple[str, bool]:
    """Keep the full card payload within Feishu's byte limit.

    Character count is insufficient for Chinese and emoji text, so use a
    binary search over Python characters and calculate the encoded JSON size
    for each candidate.
    """
    if _payload_size(title, content, template) <= FEISHU_PAYLOAD_LIMIT_BYTES:
        return content, False

    low, high = 0, len(content)
    best = ""
    while low <= high:
        midpoint = (low + high) // 2
        candidate = f"{content[:midpoint]}{_TRUNCATION_SUFFIX}"
        if _payload_size(title, candidate, template) <= FEISHU_PAYLOAD_LIMIT_BYTES:
            best = candidate
            low = midpoint + 1
        else:
            high = midpoint - 1

    # Input limits keep the header small enough that this fallback is only a
    # last-resort guard against unexpected JSON serialization differences.
    return best or _TRUNCATION_SUFFIX, True


def _configured_webhook_url() -> str:
    from api.config import get_settings

    return get_settings().feishu_webhook_url.get_secret_value().strip()


def _is_secure_webhook_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


def _coerce_feishu_code(response: Mapping[str, Any]) -> int | None:
    value = response.get("code", response.get("StatusCode"))
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return None
    return None


def _retry_delay_seconds(attempt: int, headers: Mapping[str, Any] | None) -> float:
    """Respect a bounded Retry-After hint, then use short exponential backoff."""
    retry_after = headers.get("retry-after") if headers is not None else None
    if retry_after is not None:
        try:
            return min(max(float(retry_after), 0.0), MAX_RETRY_DELAY_SECONDS)
        except (TypeError, ValueError):
            pass
    return min(0.5 * (2 ** (attempt - 1)), 2.0)


async def _sleep_before_retry(attempt: int, headers: Mapping[str, Any] | None) -> None:
    await asyncio.sleep(_retry_delay_seconds(attempt, headers))


def _failure(
    *,
    code: int,
    msg: str,
    attempts: int,
    content_truncated: bool,
    failure_reason: FailureReason,
    http_status: int | None = None,
    feishu_code: int | None = None,
    retryable: bool = False,
) -> FeishuNotifyResult:
    return FeishuNotifyResult(
        code=code,
        msg=msg,
        status="failed",
        attempts=attempts,
        content_truncated=content_truncated,
        http_status=http_status,
        feishu_code=feishu_code,
        failure_reason=failure_reason,
        retryable=retryable,
    )


@basic_mcp.tool(
    title="发送飞书通知",
    tags={"notification", "feishu"},
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
    meta={"category": "notification", "result_format": "feishu_notify_v2"},
    timeout=TOOL_TIMEOUT_SECONDS,
    version="2",
)
async def send_feishu_notify(
    title: Annotated[
        str,
        Field(
            description="飞书卡片标题，去除首尾空白后不能为空。",
            min_length=1,
            max_length=100,
        ),
    ],
    content_md: Annotated[
        str,
        Field(
            description="飞书 lark_md 格式的通知正文；超出上游字节限制时会保留前缀并标记截断。",
            min_length=1,
            max_length=50_000,
        ),
    ],
    template: Annotated[
        CardTemplate,
        Field(description="飞书卡片头部颜色模板。"),
    ] = "blue",
    max_retries: Annotated[
        int,
        Field(
            description="可重试的网络、限流或 5xx 失败后的额外尝试次数。",
            ge=0,
            le=MAX_RETRIES,
        ),
    ] = DEFAULT_MAX_RETRIES,
    request_timeout_seconds: Annotated[
        float,
        Field(
            description="单次飞书 HTTP 请求超时秒数；总执行时间仍受工具超时限制。",
            ge=1.0,
            le=MAX_REQUEST_TIMEOUT_SECONDS,
        ),
    ] = DEFAULT_REQUEST_TIMEOUT_SECONDS,
) -> FeishuNotifyResult:
    """发送服务端已配置 Webhook 的飞书机器人通知。

    Webhook URL 只从服务端 `FEISHU_WEBHOOK_URL` 读取，不接受 MCP 调用方
    提供的 URL，避免意外泄露密钥或把通知工具用作任意 HTTP 请求代理。

    Args:
        title: 飞书卡片标题。
        content_md: lark_md 格式的通知正文。
        template: 飞书卡片头部颜色。
        max_retries: 可恢复失败时的额外重试次数，范围为 0 到 2。
        request_timeout_seconds: 单次 HTTP 请求的超时秒数，范围为 1 到 10。
    """
    normalized_title = title.strip()
    if not normalized_title or not content_md.strip():
        return _failure(
            code=-2,
            msg="title 和 content_md 不能为空白。",
            attempts=0,
            content_truncated=False,
            failure_reason="validation",
        )
    if template not in _ALLOWED_TEMPLATES:
        return _failure(
            code=-2,
            msg="template 不是受支持的飞书卡片颜色。",
            attempts=0,
            content_truncated=False,
            failure_reason="validation",
        )

    webhook_url = _configured_webhook_url()
    if not webhook_url:
        return _failure(
            code=-3,
            msg="飞书 Webhook 未配置。请在服务端配置 FEISHU_WEBHOOK_URL。",
            attempts=0,
            content_truncated=False,
            failure_reason="configuration",
        )
    if not _is_secure_webhook_url(webhook_url):
        return _failure(
            code=-3,
            msg="服务端飞书 Webhook 必须是有效的 HTTPS URL。",
            attempts=0,
            content_truncated=False,
            failure_reason="configuration",
        )

    content, content_truncated = _fit_content_to_payload_limit(
        normalized_title, content_md, template
    )
    payload = _make_payload(normalized_title, content, template)
    payload_bytes = dumps_bytes(payload)
    headers = {"Content-Type": "application/json; charset=utf-8"}

    # A Feishu webhook path contains its credential.  Do not follow a
    # compromised/misconfigured endpoint's redirect to another destination.
    async with httpx.AsyncClient(
        timeout=request_timeout_seconds, follow_redirects=False
    ) as client:
        for attempt in range(1, max_retries + 2):
            try:
                # httpx's scalar timeout applies to individual connection,
                # read, write, and pool phases.  Bound the *whole* request as
                # advertised by this MCP parameter as well.
                async with asyncio.timeout(request_timeout_seconds):
                    response = await client.post(
                        webhook_url,
                        headers=headers,
                        content=payload_bytes,
                    )
            except asyncio.CancelledError:
                raise
            except (TimeoutError, httpx.TimeoutException):
                logger.warning(
                    "Feishu webhook timed out (attempt {}/{})",
                    attempt,
                    max_retries + 1,
                )
                if attempt <= max_retries:
                    await _sleep_before_retry(attempt, None)
                    continue
                return _failure(
                    code=-1,
                    msg="飞书 Webhook 请求超时。",
                    attempts=attempt,
                    content_truncated=content_truncated,
                    failure_reason="timeout",
                    retryable=True,
                )
            except httpx.RequestError:
                logger.warning(
                    "Feishu webhook request failed (attempt {}/{})",
                    attempt,
                    max_retries + 1,
                    exc_info=True,
                )
                if attempt <= max_retries:
                    await _sleep_before_retry(attempt, None)
                    continue
                return _failure(
                    code=-1,
                    msg="飞书 Webhook 网络请求失败。",
                    attempts=attempt,
                    content_truncated=content_truncated,
                    failure_reason="network",
                    retryable=True,
                )

            response_data: Mapping[str, Any] | None = None
            try:
                candidate = response.json()
                if isinstance(candidate, Mapping):
                    response_data = candidate
            except (TypeError, ValueError):
                logger.warning(
                    "Feishu webhook response is not JSON (status={})",
                    response.status_code,
                )

            feishu_code = (
                _coerce_feishu_code(response_data) if response_data is not None else None
            )
            retryable_status = response.status_code in _RETRYABLE_HTTP_STATUSES
            retryable_code = feishu_code in _RETRYABLE_FEISHU_CODES
            if retryable_status or retryable_code:
                if attempt <= max_retries:
                    response_headers = getattr(response, "headers", None)
                    await _sleep_before_retry(
                        attempt,
                        response_headers
                        if isinstance(response_headers, Mapping)
                        else None,
                    )
                    continue
                failure_reason: FailureReason = (
                    "rate_limited"
                    if response.status_code == 429 or retryable_code
                    else "upstream"
                )
                return _failure(
                    code=-1,
                    msg="飞书 Webhook 暂时不可用，重试次数已用尽。",
                    attempts=attempt,
                    content_truncated=content_truncated,
                    failure_reason=failure_reason,
                    http_status=response.status_code,
                    feishu_code=feishu_code,
                    retryable=True,
                )

            if response.status_code == 200 and feishu_code == 0:
                return FeishuNotifyResult(
                    code=0,
                    msg="success",
                    status="sent",
                    attempts=attempt,
                    content_truncated=content_truncated,
                    http_status=response.status_code,
                    feishu_code=feishu_code,
                )

            if response_data is None:
                return _failure(
                    code=-1,
                    msg="飞书 Webhook 返回了无法解析的响应。",
                    attempts=attempt,
                    content_truncated=content_truncated,
                    failure_reason="invalid_response",
                    http_status=response.status_code,
                )

            return _failure(
                code=-1,
                # A webhook response is untrusted external content.  Keep the
                # structured status/code for diagnostics without feeding an
                # arbitrary upstream message back to an agent.
                msg="飞书 Webhook 返回了失败状态。",
                attempts=attempt,
                content_truncated=content_truncated,
                failure_reason="upstream",
                http_status=response.status_code,
                feishu_code=feishu_code,
                retryable=False,
            )

    # The loop always returns; retain a typed fallback for static analyzers.
    return _failure(
        code=-1,
        msg="飞书 Webhook 发送未完成。",
        attempts=0,
        content_truncated=content_truncated,
        failure_reason="network",
        retryable=True,
    )
