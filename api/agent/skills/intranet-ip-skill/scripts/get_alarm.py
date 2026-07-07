#!/home/shenss/python/fastapi/.venv/bin/python3
"""按 doc_id 获取并清洗 NDR 告警"""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from pydantic import TypeAdapter

from base import post_jsonrpc


def _clean_alarm(raw_data: dict[str, Any]) -> dict[str, Any]:
    keys_to_keep = [
        "name",
        "msg",
        "cve_list",
        "attacker_ip",
        "attacker_port",
        "victim_ip",
        "victim_port",
        "proto",
        "app_proto",
        "timestamp",
        "classify",
        "tag",
        "payload",
    ]

    cleaned: dict[str, Any] = {
        k: raw_data.get(k) for k in keys_to_keep if raw_data.get(k) is not None
    }
    cleaned["attacker_ip_port"] = (
        f"{raw_data.get('attacker_ip')}:{raw_data.get('attacker_port')}"
    )
    cleaned["victim_ip_port"] = (
        f"{raw_data.get('victim_ip')}:{raw_data.get('victim_port')}"
    )
    cleaned.pop("attacker_ip", None)
    cleaned.pop("attacker_port", None)
    cleaned.pop("victim_ip", None)
    cleaned.pop("victim_port", None)

    if "appbrief" in raw_data and isinstance(raw_data["appbrief"], dict):
        appbrief: dict[str, Any] = raw_data["appbrief"]
        appbrief.pop("version_data", None)
        if "http" in appbrief:
            http_info = appbrief["http"]
            cleaned["http_details"] = {
                "hostname": http_info.get("hostname"),
                "method": http_info.get("method"),
                "url": http_info.get("url"),
                "user_agent": http_info.get("user_agent"),
                "req_header": http_info.get("req_header_raw"),
                "req_body": http_info.get("req_body"),
                "resp_status": http_info.get("status"),
                "resp_header": http_info.get("resp_header_raw"),
                "resp_body": http_info.get("resp_body"),
            }
        else:
            cleaned["protocol_details"] = appbrief

    return cleaned


async def get_alarm_by_doc_id(doc_id: str) -> dict[str, Any]:
    result = await post_jsonrpc(
        "AlarmService.GetAlarmDocument",
        {"doc_id": doc_id},
    )
    raw_data = result.get("data")
    if not raw_data:
        return {"error": f"未找到 doc_id={doc_id} 对应的告警数据"}
    return _clean_alarm(raw_data)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="按 doc_id 获取并清洗 NDR 告警")
    parser.add_argument("--doc-id", required=True, help="NDR 告警 doc_id")
    return parser


async def _main_async() -> int:
    args = _build_parser().parse_args()
    try:
        data = await get_alarm_by_doc_id(args.doc_id)
        print(TypeAdapter(Any).dump_json(data).decode("utf-8"))
        return 0
    except Exception as exc:
        print(f"获取告警失败: {exc}")
        return 1


def main() -> int:
    return asyncio.run(_main_async())


if __name__ == "__main__":
    raise SystemExit(main())
