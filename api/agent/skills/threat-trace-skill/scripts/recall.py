#!/home/shenss/python/fastapi/.venv/bin/python3
"""召回威胁情报"""

import argparse
import asyncio
import json
from typing import Any

import aiomysql

from base import _get_pool


async def recall_threat_info(keywords: str, days: int = 90) -> list[dict[str, Any]]:
    """通过关键词查询威胁情报信息的 id 和 title。

    Args:
        keywords: 查询关键词
        days: 查询最近多少天的数据，默认90天

    Returns:
        list[dict[str, Any]]: 查询结果
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            sql = (
                "SELECT id, title "
                "FROM dynamic_monitor "
                "WHERE (title LIKE %s OR description LIKE %s) "
                "AND public_time >= DATE_SUB(NOW(), INTERVAL %s DAY) "
                "ORDER BY public_time DESC"
            )
            await cursor.execute(sql, (f"%{keywords}%", f"%{keywords}%", days))
            result = await cursor.fetchall()
            return result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="召回威胁情报概要")
    parser.add_argument("--keywords", required=True, help="检索关键词")
    parser.add_argument("--days", type=int, default=90, help="查询最近多少天的数据，默认90天")
    return parser


async def _main_async() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        result = await recall_threat_info(args.keywords, args.days)
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except Exception as e:
        print(f"查询威胁情报失败: {e}")
        return 1


def main() -> int:
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
