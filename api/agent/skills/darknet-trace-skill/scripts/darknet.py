#!/home/shenss/python/fastapi/.venv/bin/python3
"""获取暗网数据泄露威胁情报标题"""

import argparse
import asyncio
import json
import re
from datetime import datetime
from typing import Any

import aiomysql

from base import _get_pool


def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, datetime):
        return obj.strftime("%Y-%m-%d %H:%M:%S")
    raise TypeError(f"Type {type(obj)} not serializable")


async def recall_darknet_titles(
    days: int = 7, limit: int | None = None
) -> list[dict[str, Any]]:
    """召回最近 N 天的暗网数据标题。

    Args:
        days: 查询最近多少天的数据，默认 7 天（上周）。
        limit: 限制返回条数，默认不限制。

    Returns:
        标题列表（包含 id/title/date_time）。
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            sql = (
                "SELECT id, title, date_time "
                "FROM anwang "
                "WHERE date_time >= DATE_SUB(NOW(), INTERVAL %s DAY) "
                "ORDER BY date_time DESC"
            )
            params: list[Any] = [days]
            if limit is not None:
                sql += " LIMIT %s"
                params.append(limit)
            await cursor.execute(sql, params)
            result = await cursor.fetchall()
            return result


def _match_domestic_titles(items: list[dict[str, Any]]) -> list[str]:
    """按规则匹配国内相关标题。"""
    kw_regex = re.compile(
        r"中国|车主|省|(?<![股超城上])市(?!场|值)|香港|大陆|台湾|澳门|(?<![德法英美日俄韩意加瑞澳西])国内|\bChina\b|\bchinese\b",
        re.IGNORECASE,
    )
    matched_titles: list[str] = []
    for item in items:
        title_str = str(item.get("title") or "")
        if kw_regex.search(title_str):
            matched_titles.append(title_str)
    return matched_titles


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="召回暗网泄露标题（上周默认 7 天）")
    parser.add_argument(
        "--days", type=int, default=7, help="查询最近多少天的数据，默认 7 天"
    )
    parser.add_argument("--limit", type=int, default=None, help="限制返回条数（可选）")
    return parser


async def _main_async() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        items = await recall_darknet_titles(days=args.days, limit=args.limit)
        matched_titles = _match_domestic_titles(items)
        payload = {
            "count": len(items),
            "domestic_count": len(matched_titles),
            "domestic_titles": matched_titles,
        }
        print(json.dumps(payload, ensure_ascii=False, default=json_serial))
        return 0
    except Exception as e:
        print(f"查询暗网情报失败: {e}")
        return 1


def main() -> int:
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
