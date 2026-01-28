import asyncio
import os
import httpx
import aiomysql
from fastmcp import FastMCP
from dotenv import load_dotenv
from api.utils.db import get_db_pool

load_dotenv(override=True)
mcp = FastMCP("fastapi-mcp")


@mcp.tool(annotations={"readOnlyHint": True, "idempotentHint": True})
def health() -> dict:
    """Simple health check tool."""
    return {"status": "ok"}


@mcp.tool()
async def fetch_exec_logs_by_only_id(only_id: str) -> dict | list[dict]:
    """根据 only_id 获取 W5 SOAR Workflow 执行日志。
    Args:
        only_id: W5 SOAR Workflow 执行唯一标识符
    Returns:
        W5 SOAR Webhook 接口返回
        {'code': int, 'msg': str, 'data': list}
        data: 日志列表
            - app_name: 应用名称
            - result: 执行结果
            - status: 状态 0-成功 1-警告 2-异常 3-威胁
    """
    if not only_id:
        return {"code": 400, "msg": "only_id 不能为空"}
    await asyncio.sleep(1.0)  # 等待日志写入数据库
    try:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                sql = "SELECT app_name, result, status FROM w5_db.w5_logs WHERE only_id=%s"
                await cursor.execute(sql, (only_id,))
                rows: list[dict] = await cursor.fetchall()
                return {"code": 200, "msg": "成功", "data": rows}
        return {"code": 200, "msg": "成功", "data": rows}
    except Exception as e:
        return {"code": 500, "msg": f"获取日志失败: {e}"}


@mcp.tool()
async def get_cve_poc(
    query: str, source: str | None = None, page: int = 1, size: int = 10
) -> dict:
    """根据 CVE 编号或关键字获取 CVE 漏洞利用代码或 PoC，通过飞书通知获取详情。
    Args:
        query: CVE 编号或关键字
        source: 数据源名称, 可选: github, exploit-db
        page: 页码，默认1
        size: 每页数量, 默认10，最大100
    Returns:
        W5 SOAR Webhook 接口返回
        {'code': int, 'msg': str, 'data': dict}
        data: {
            'only_id': str,  # W5 SOAR Workflow 执行唯一标识符
        }
    """
    headers = {"Content-Type": "application/json"}
    webhook_url = os.getenv(
        "MCP_WEBHOOK_URL", "http://localhost:8888/api/v1/w5/webhook"
    )
    webhook_key = os.getenv("W5_SOAR_TOKEN", "")
    webhook_uuid = "84488800-fa7c-11f0-8c8c-93c8eb47efc2"

    data = {
        "key": webhook_key,
        "uuid": webhook_uuid,
        "data": {
            "query": query,
            "source": source,
            "page": page,
            "size": size,
        },
    }

    async with httpx.AsyncClient(timeout=10, verify=False) as client:
        resp = await client.post(webhook_url, json=data, headers=headers)
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    mcp.run(transport="http", host="http://localhost", port=8000)
