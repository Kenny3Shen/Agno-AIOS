from fastmcp import FastMCP
import httpx
import asyncio

from loguru import logger
from mcp.types import ToolAnnotations

from api.utils.json import dumps_bytes

basic_mcp = FastMCP("Basic")


@basic_mcp.tool(
    title="发送飞书通知",
    tags={"notification", "feishu"},
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=True,
    ),
    meta={"category": "notification"},
)
async def send_feishu_notify(
    title: str,
    content_md: str,
    template: str = "blue",
    feishu_webhook_url: str | None = None,
) -> dict:
    """发送飞书机器人通知

    Args:
        title: 标题
        content_md: 内容
        template: 卡片颜色模板
        feishu_webhook_url: 可选；缺省时使用服务端配置的飞书 Webhook
    Returns:
        dict: 发送结果
    """
    if not (feishu_webhook_url or "").strip():
        from api.config import get_settings

        feishu_webhook_url = get_settings().feishu_webhook_url.get_secret_value().strip()
    if not feishu_webhook_url:
        return {"code": -1, "msg": "飞书 Webhook 未配置"}

    def _make_payload(content: str) -> dict:
        payload = {
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
        return payload

    def _payload_size(content: str) -> int:
        try:
            return len(dumps_bytes(_make_payload(content)))
        except Exception:
            logger.debug("Feishu payload size estimate failed; treating as oversized", exc_info=True)
            return 10**9

    limit_bytes = 30 * 1024
    content = content_md
    if _payload_size(content) > limit_bytes:
        content = content[:5000] + "\n...\n"

    headers = {"Content-Type": "application/json; charset=utf-8"}
    max_retries = 3

    for attempt in range(max_retries):
        payload = _make_payload(content)
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    feishu_webhook_url,
                    headers=headers,
                    content=dumps_bytes(payload),
                )

            resp_json: dict = {}
            try:
                resp_json = r.json()
            except Exception:
                logger.warning(
                    "Feishu webhook response is not JSON (status={})",
                    r.status_code,
                    exc_info=True,
                )
                return {"code": -1, "msg": "响应解析失败"}

            code = resp_json.get("code")
            if code is None:
                code = resp_json.get("StatusCode")
            if r.status_code == 200 and code == 0:
                return {"code": 0, "msg": "success"}
            elif code == 11232:
                await asyncio.sleep(10)
                continue  # 发送频率过快，重试
            else:
                return {"code": -1, "msg": f"发送失败，响应：{resp_json}"}

        except Exception:
            logger.warning(
                "Feishu webhook request failed (attempt {}/{})",
                attempt + 1,
                max_retries,
                exc_info=True,
            )
            return {"code": -1, "msg": "请求异常，发送失败"}
    return {"code": -1, "msg": "发送失败，重试次数用尽"}
