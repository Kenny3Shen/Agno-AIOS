import asyncio
import logging
import os
import time

import httpx
from agno.agent import Agent
from agno.models.openai import OpenAILike
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

instructions = """
你是一位网络安全专家，专注于网络流量分析和入侵检测系统（NDR）告警研判。
用户会输入一个 doc_id，你需要根据该 doc_id 获取对应的 NDR 告警数据，并分析判断其是否为误报。

请根据以下步骤进行分析：
1. **攻击特征匹配**：分析 `payload` 或 HTTP/DNS 请求内容（`req_body`, `req_line`, `req_header_raw`）是否符合告警名称（`name`）或 CVE 描述的攻击特征。
2. **响应分析**：检查 HTTP 响应状态码（`status`）和响应体（`resp_body`）。
   - 如果状态码是 200 且响应体包含敏感数据或预期报错，可能是攻击成功。
   - 如果状态码是 403/404/500，攻击可能失败，但仍需判断是否为恶意扫描。
3. **上下文分析**：结合源 IP、目的 IP、端口等信息判断攻击意图。

请以 Markdown 格式输出分析结果，包含以下字段：

"verdict": "研判结论，可选值为 "真实" (确认为攻击), "误报" (确认为误报), "可疑" (需进一步人工排查)",
"confidence": "置信度评分，范围 0-100，表示你对研判结论的确信程度",
"analysis": "详细的分析过程，解释为什么得出该结论",
"evidence": "支持结论的关键证据（如匹配的 Payload 片段）",
"suggestion": "处置建议（如封禁 IP、忽略、修复漏洞等）"
"""


async def get_data_from_doc_id(doc_id: str) -> dict:
    """通过 doc_id 获取 NDR 告警的原始数据，并进行清洗返回。
    Args:
        doc_id (str): 104 位十六进制字符串，NDR 告警的唯一标识符。
    Returns:
        cleaned_data (dict): 清洗后的告警数据字典。包括：
            - name: 告警名称
            - msg: 告警描述
            - cve_list: 关联 CVE 列表
            - attacker_ip_port: 攻击者 IP:port
            - victim_ip_port: 受害者 IP:port
            - proto: 传输层协议
            - app_proto: 应用层协议
            - timestamp: 时间戳
            - classify: 分类
            - tag: 标签
            - payload: 原始 Payload (如果有)
            - http_details: HTTP 协议详情（如果适用）
            - protocol_details: 其他协议详情（如果适用）
    """

    headers = {
        "API-Token": os.getenv("NDR_API_TOKEN", ""),
        "Content-Type": "application/json;charset=UTF-8",
    }
    body = {
        "jsonrpc": "2.0",
        "method": "AlarmService.GetAlarmDocument",
        "params": {"doc_id": doc_id},
        "id": f"quanxi-{int(time.time() * 1000)}-getdoc",
    }
    async with httpx.AsyncClient(timeout=60.0, verify=False) as client:
        resp = await client.post(
            url=os.getenv("NDR_API_URL", ""), json=body, headers=headers
        )
        resp.raise_for_status()
        res_json = resp.json()
        raw_data = res_json.get("result", {}).get("data")

    if not raw_data:
        return {"error": f"未找到 doc_id={doc_id} 对应的告警数据"}
    keys_to_keep = [
        "name",  # 告警名称
        "msg",  # 告警描述
        "cve_list",  # 关联 CVE
        "attacker_ip",  # 攻击者 IP
        "attacker_port",  # 攻击者端口
        "victim_ip",  # 受害者 IP
        "victim_port",  # 受害者端口
        "proto",  # 传输层协议
        "app_proto",  # 应用层协议
        "timestamp",  # 时间戳
        "classify",  # 分类
        "tag",  # 标签
        "payload",  # 原始 Payload (如果有)
    ]

    cleaned: dict = {
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

    # 2. 协议详情 (appbrief) 处理
    if "appbrief" in raw_data and isinstance(raw_data["appbrief"], dict):
        appbrief: dict = raw_data["appbrief"]
        appbrief.pop("version_data", None)  # 删除冗余字段
        # HTTP 协议特殊处理
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
        # 其他协议使用 appbrief
        else:
            cleaned["protocol_details"] = appbrief
    # print(cleaned)
    return cleaned


async def search_alarm_list(
    self,
    time_range_start: int,
    time_range_end: int,
    offset: int = 0,
    count: int = 10_000,
    advanced_query: str = "(((victim = '10.0.0.0/8' OR victim = '172.16.0.0/12' OR victim = '192.168.0.0/16') AND severity != 4) OR tag = '弱口令')",  # "victim =/!=/like/not like/is/in/not in '{ip}' AND/OR xxx"
) -> list[dict]:
    # 构建过滤条件
    # 忽略 DNS 告警
    if self.ignore_dns:
        advanced_query = f"({advanced_query}) AND app_proto != 'dns'"
    # 忽略 扫描器 告警
    if self.ignore_scan:
        advanced_query = f"({advanced_query}) AND (tag != '扫描器' OR attacker = '10.0.0.0/8' OR attacker = '172.16.0.0/12' OR attacker = '192.168.0.0/16')"
    # 忽略 攻击结果为 failed 的告警
    if self.ignore_attack_failed:
        advanced_query = f"({advanced_query}) AND (result != 'failed' OR attacker = '10.0.0.0/8' OR attacker = '172.16.0.0/12' OR attacker = '192.168.0.0/16')"
    body = {
        "jsonrpc": "2.0",
        "method": "AlarmService.SearchAlarmList",
        "params": {
            "advanced_query": advanced_query,
            "offset": offset,
            "count": count,
            "time_range_start": time_range_start,
            "time_range_end": time_range_end,
            "ignore": 0,  # 是否忽略已处理告警，0-否，1-是
            "collapse_key": "collapse_field",
            "agg_sort": {"field": "maxtime", "operator": "", "ascending": False},
        },
        "id": "Agent",
    }

    try:
        resp = await self.client.post(
            url=self.api_url, json=body, headers=self._headers
        )
        resp.raise_for_status()
        res_json = resp.json()
        data = res_json.get("result", {}).get("data")
        return data or []
    except Exception:
        logger.warning("intranet IP skill lookup failed", exc_info=True)
        return []



class VerdictAgent(Agent):
    def __init__(
        self, api_key: str, base_url: str, model: str, thinking: bool = False, **kwargs
    ):
        super().__init__(
            name="VerdictAgent",
            model=OpenAILike(
                id=model,
                api_key=api_key,
                base_url=base_url,
                extra_body={
                    "thinking": {"type": "disabled" if not thinking else "enabled"}
                },
            ),
            instructions=instructions,
            tools=[get_data_from_doc_id],
            add_datetime_to_context=True,
            markdown=True,
        )


if __name__ == "__main__":
    doc_id = "7be9d9103fcd029765bcf4762dd2a360f0d2cb9964ea21e386f24f23208f5a8b869a4dd1f9ca772c481b7ae14f0d6767f5029aab"
    agent = VerdictAgent(
        api_key=os.getenv("LLM_API_KEY", ""),
        base_url=os.getenv("LLM_URL", ""),
        model=os.getenv("LLM_EP", ""),
    )
    asyncio.run(
        agent.aprint_response(f"分析这个 doc_id 是否为误报: {doc_id}", stream=True)
    )
