#!/home/shenss/python/fastapi/.venv/bin/python3
"""按时间范围检索 NDR 告警列表"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from base import post_jsonrpc

DEFAULT_ADVANCED_QUERY = "(((victim = '10.0.0.0/8' OR victim = '172.16.0.0/12' OR victim = '192.168.0.0/16') AND severity != 4) OR tag = '弱口令')"


def _apply_filters(
    advanced_query: str,
    ignore_dns: bool,
    ignore_scan: bool,
    ignore_attack_failed: bool,
) -> str:
    query = advanced_query
    if ignore_dns:
        query = f"({query}) AND app_proto != 'dns'"
    if ignore_scan:
        query = (
            f"({query}) AND (tag != '扫描器' OR attacker = '10.0.0.0/8' OR attacker = '172.16.0.0/12' OR attacker = '192.168.0.0/16')"
        )
    if ignore_attack_failed:
        query = (
            f"({query}) AND (result != 'failed' OR attacker = '10.0.0.0/8' OR attacker = '172.16.0.0/12' OR attacker = '192.168.0.0/16')"
        )
    return query


async def search_alarm_list(
    time_range_start: int,
    time_range_end: int,
    offset: int = 0,
    count: int = 1000,
    advanced_query: str = DEFAULT_ADVANCED_QUERY,
    ignore_dns: bool = False,
    ignore_scan: bool = False,
    ignore_attack_failed: bool = False,
) -> list[dict[str, Any]]:
    query = _apply_filters(advanced_query, ignore_dns, ignore_scan, ignore_attack_failed)
    result = await post_jsonrpc(
        "AlarmService.SearchAlarmList",
        {
            "advanced_query": query,
            "offset": offset,
            "count": count,
            "time_range_start": time_range_start,
            "time_range_end": time_range_end,
            "ignore": 0,
            "collapse_key": "collapse_field",
            "agg_sort": {"field": "maxtime", "operator": "", "ascending": False},
        },
    )
    data = result.get("data")
    return data or []


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="按时间范围检索 NDR 告警列表")
    parser.add_argument("--start", type=int, required=True, help="开始时间（epoch ms）")
    parser.add_argument("--end", type=int, required=True, help="结束时间（epoch ms）")
    parser.add_argument("--offset", type=int, default=0, help="偏移量")
    parser.add_argument("--count", type=int, default=1000, help="返回条数")
    parser.add_argument("--advanced", default=DEFAULT_ADVANCED_QUERY, help="高级查询语句")
    parser.add_argument("--ignore-dns", action="store_true", help="忽略 DNS 告警")
    parser.add_argument("--ignore-scan", action="store_true", help="忽略扫描器告警")
    parser.add_argument("--ignore-attack-failed", action="store_true", help="忽略攻击结果为 failed 的告警")
    return parser


async def _main_async() -> int:
    args = _build_parser().parse_args()
    try:
        data = await search_alarm_list(
            time_range_start=args.start,
            time_range_end=args.end,
            offset=args.offset,
            count=args.count,
            advanced_query=args.advanced,
            ignore_dns=args.ignore_dns,
            ignore_scan=args.ignore_scan,
            ignore_attack_failed=args.ignore_attack_failed,
        )
        print(json.dumps(data, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"检索告警失败: {exc}")
        return 1


def main() -> int:
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
