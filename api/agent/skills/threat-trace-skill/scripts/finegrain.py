#!/home/shenss/python/fastapi/.venv/bin/python3
"""获取威胁情报详情"""

import argparse
import asyncio
import json
from datetime import date, datetime
from typing import Any

import aiomysql

from base import _get_pool


async def finegrain_threat_info(threat_ids: tuple[int, ...]) -> list[dict[str, Any]]:
    """通过威胁情报 id 查询 description、url、public_time 等详细信息。

    Args:
        threat_ids: 威胁情报 id 列表

    Returns:
        list[dict[str, Any]]: 详细信息, 包含 description、url、public_time 等字段
    """
    pool = await _get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cursor:
            sql = "SELECT description, url, public_time FROM dynamic_monitor WHERE id IN %s"
            await cursor.execute(sql, (threat_ids,))
            result = await cursor.fetchall()
            return result


def _parse_ids(raw: str) -> tuple[int, ...]:
    items = [item.strip() for item in raw.split(",") if item.strip()]
    if not items:
        return tuple()
    return tuple(int(item) for item in items)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="获取威胁情报详情")
    parser.add_argument(
        "--ids",
        required=True,
        help="威胁情报 id，逗号分隔，例如 1,2,3",
    )
    return parser


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


async def _main_async() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    threat_ids = _parse_ids(args.ids)
    if not threat_ids:
        raise SystemExit("ids 不能为空")

    try:
        result = await finegrain_threat_info(threat_ids)
        print(json.dumps(result, ensure_ascii=False, default=_json_default))
        return 0
    except Exception as e:
        print(f"查询威胁情报详情失败: {e}")
        return 1


def main() -> int:
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())