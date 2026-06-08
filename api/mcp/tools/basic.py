from fastmcp import FastMCP
import httpx
from dotenv import load_dotenv
import json
import asyncio


load_dotenv(override=True)


basic_mcp = FastMCP("Basic")


@basic_mcp.tool()
async def send_feishu_notify(
    feishu_webhook_url: str,
    title: str,
    content_md: str,
    template: str = "blue",
) -> dict:
    """发送飞书机器人通知
    Args:
        feishu_webhook_url: 飞书机器人 Webhook URL
        title: 标题
        content_md: 内容
    Returns:
        dict: 发送结果
    """

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
            return len(
                json.dumps(_make_payload(content), ensure_ascii=False).encode("utf-8")
            )
        except Exception:
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
                    content=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                )

            resp_json: dict = {}
            try:
                resp_json = r.json()
            except Exception:
                return {"code": -1, "msg": "响应解析失败"}

            code = resp_json.get("code") or resp_json.get("StatusCode")
            if r.status_code == 200 and code == 0:
                return {"code": 0, "msg": "success"}
            elif code == 11232:
                await asyncio.sleep(10)
                continue  # 发送频率过快，重试
            else:
                return {"code": -1, "msg": f"发送失败，响应：{resp_json}"}

        except Exception:
            return {"code": -1, "msg": "请求异常，发送失败"}
    return {"code": -1, "msg": "发送失败，重试次数用尽"}
