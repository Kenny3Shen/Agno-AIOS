import asyncio
import json
import sqlite3
import time
import uuid
from fastmcp import FastMCP
import os
import httpx
from dotenv import load_dotenv
from api.mcp.config import HIAGENT_CACHE_DB, enabled_hiagent_urls

load_dotenv(override=True)
playbook_mcp = FastMCP("Playbook")


def _get_hiagent_urls() -> list[str]:
    """从中台 MCP 配置读取已启用的 Hi-Agent MCP URL 列表。"""
    return enabled_hiagent_urls()


class W5Adapter:
    def __init__(self):
        self.token = os.getenv("W5_SOAR_TOKEN", "")
        if not self.token:
            raise ValueError("W5_SOAR_TOKEN 环境变量未设置")
        self.api_base = os.getenv("W5_API_BASE", "")
        if not self.api_base:
            raise ValueError("W5_API_BASE 环境变量未设置")
        self.headers = {"Content-Type": "application/json"}
        self.client = httpx.AsyncClient(timeout=10, verify=False)

    async def list_workflows(self) -> dict:
        payload = {"key": self.token}
        resp = await self.client.post(
            f"{self.api_base}/get/workflow_list",
            json=payload,
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_method_params(self, method_id: str) -> dict:
        payload = {"key": self.token, "uuid": method_id}
        resp = await self.client.post(
            f"{self.api_base}/get/webhook_param",
            json=payload,
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def invoke_method(self, method_id: str, params: dict | None = None) -> dict:
        payload = {"key": self.token, "uuid": method_id, "data": params}
        resp = await self.client.post(
            f"{self.api_base}/webhook",
            json=payload,
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_exec_result(self, exec_id: str) -> dict:
        payload = {"key": self.token, "only_id": exec_id}
        resp = await self.client.post(
            f"{self.api_base}/get/webhook_result",
            json=payload,
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()


class OctomationAdapter:
    def __init__(self):
        self.token = os.getenv("OCTOMATION_TOKEN", "")
        if not self.token:
            raise ValueError("OCTOMATION_TOKEN 环境变量未设置")
        self.api_base = os.getenv("OCTOMATION_API_BASE", "")
        if not self.api_base:
            raise ValueError("OCTOMATION_API_BASE 环境变量未设置")
        self.headers = {"hg-token": self.token, "Content-Type": "application/json"}
        self.client = httpx.AsyncClient(timeout=10, verify=False)

    async def list_workflows(self) -> dict:
        request_body = {"publishStatus": "ONLINE"}
        resp = await self.client.post(
            f"{self.api_base}/api/playbook/findAll",
            json=request_body,
            headers=self.headers,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            return {"code": -1, "msg": data.get("message", "未知错误"), "data": []}

        playbooks = data.get("result", [])
        return {
            "code": 0,
            "msg": "ok",
            "data": [
                {"id": p.get("id"), "name": p.get("displayName")} for p in playbooks
            ],
        }

    async def get_method_params(self, method_id: str) -> dict:
        # 优先尝试从剧本详情获取参数定义
        try:
            detail_resp = await self.client.get(
                f"{self.api_base}/api/playbook/{method_id}",
                headers=self.headers,
            )
            detail_resp.raise_for_status()
            detail_data = detail_resp.json()
            if detail_data.get("code") == 200:
                result = detail_data.get("result", {})
                if isinstance(result, dict):
                    param_set = result.get("paramCefSet", [])
                    formatted = []
                    for p in param_set:
                        if isinstance(p, dict):
                            formatted.append(
                                {
                                    "key": p.get("cefColumn", ""),
                                    "description": p.get("display", ""),
                                }
                            )
                    return {"code": 0, "msg": "ok", "data": formatted}
        except Exception:
            pass

        # 降级尝试旧的 param 接口（可能返回502）
        try:
            resp = await self.client.get(
                f"{self.api_base}/api/playbook/param",
                params={"playbookId": method_id},
                headers=self.headers,
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") == 200:
                return {"code": 0, "msg": "ok", "data": data.get("result", [])}
        except Exception:
            pass

        # 最后的降级：返回空参数列表，允许用户手动填写
        return {"code": 0, "msg": "ok", "data": []}

    async def invoke_method(self, method_id: str, params: dict | None = None) -> dict:
        payload_params = []
        for key, value in (params or {}).items():
            payload_params.append({"key": key, "value": str(value)})

        api_request = {
            "eventId": 0,
            "executorInstanceId": method_id,
            "executorInstanceType": "PLAYBOOK",
            "params": payload_params,
        }

        resp = await self.client.post(
            f"{self.api_base}/api/event/execution",
            json=api_request,
            headers=self.headers,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            return {"code": -1, "msg": data.get("message", "未知错误"), "data": {}}

        activity_id = data.get("result")
        if not activity_id:
            return {"code": -1, "msg": "API未返回活动ID", "data": {}}

        return {"code": 0, "msg": "ok", "data": {"exec_id": activity_id}}

    async def get_exec_result(self, exec_id: str) -> dict:
        status_resp = await self.client.get(
            f"{self.api_base}/api/activity/{exec_id}",
            headers=self.headers,
        )
        status_resp.raise_for_status()
        status_data = status_resp.json()
        if status_data.get("code") != 200:
            return {
                "code": -1,
                "msg": status_data.get("message", "未知错误"),
                "data": {},
            }

        result_data = status_data.get("result", {})
        status = result_data.get("executeStatus", "UNKNOWN")
        if status != "SUCCESS":
            return {"code": 1, "msg": "执行中", "data": {"status": status}}

        result_resp = await self.client.get(
            f"{self.api_base}/api/event/activity",
            params={"activityId": exec_id},
            headers=self.headers,
        )
        result_resp.raise_for_status()
        result_json = result_resp.json()
        if result_json.get("code") != 200:
            return {
                "code": -1,
                "msg": result_json.get("message", "未知错误"),
                "data": {},
            }

        return {
            "code": 0,
            "msg": "ok",
            "data": {"status": status, "result": result_json},
        }





class HiAgentAdapter:
    """
    HiAgent 兼容层

    与 W5/Octomation 不同，hi-agent 的每个工具拥有独立的 mcp_url。
    通过 MCP 协议（JSON-RPC 2.0）的 tools/list 和 tools/call 交互。

    特点：
    - list_workflows: 遍历所有已注册的 mcp_url，聚合工具列表
    - get_method_params: 从缓存的 inputSchema 中提取参数定义
    - invoke_method: SSE 流式读取 tools/call 结果
    - get_exec_result: 同步执行，结果在 invoke 时即刻返回（本地缓存）
    """

    MCP_HEADERS = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0",
    }

    _DB_PATH = HIAGENT_CACHE_DB

    def __init__(self):
        self.client = httpx.AsyncClient(timeout=60.0, verify=False)
        # 内存缓存: tool_name -> {url, description, input_schema}
        self._tool_registry: dict[str, dict] = {}
        # SQLite 持久化执行结果
        self._init_db()

    # ── 内部: SQLite 持久化 ──────────────────────────────
    def _init_db(self) -> None:
        conn = sqlite3.connect(self._DB_PATH)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS hiagent_exec_cache (
                    exec_id TEXT PRIMARY KEY,
                    tool_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result TEXT,
                    error TEXT,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _save_exec(self, exec_id: str, tool_name: str, status: str,
                   result: str = "", error: str = "") -> None:
        conn = sqlite3.connect(self._DB_PATH)
        try:
            conn.execute(
                "INSERT OR REPLACE INTO hiagent_exec_cache "
                "(exec_id, tool_name, status, result, error, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (exec_id, tool_name, status, result, error, time.time()),
            )
            conn.commit()
        finally:
            conn.close()

    def _load_exec(self, exec_id: str) -> dict | None:
        conn = sqlite3.connect(self._DB_PATH)
        try:
            row = conn.execute(
                "SELECT exec_id, tool_name, status, result, error, created_at "
                "FROM hiagent_exec_cache WHERE exec_id = ?",
                (exec_id,),
            ).fetchone()
            if not row:
                return None
            return {
                "exec_id": row[0],
                "tool_name": row[1],
                "status": row[2],
                "result": row[3],
                "error": row[4],
                "created_at": row[5],
            }
        finally:
            conn.close()

    # ── 内部: SSE/JSON 响应解析 ────────────────────────────
    @staticmethod
    def _parse_mcp_response(raw_text: str) -> dict | None:
        """兼容 SSE data: 行 / 纯 JSON / 多行混合"""
        raw_text = raw_text.strip()
        for line in raw_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("data:"):
                try:
                    return json.loads(line[5:].strip())
                except Exception:
                    continue
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except Exception:
                    continue
        try:
            return json.loads(raw_text)
        except Exception:
            return None

    # ── 内部: SSE 流式读取 tools/call 结果 ─────────────────
    async def _stream_tools_call(self, url: str, tool_name: str, args: dict) -> str:
        """
        通过 SSE 流式读取 tools/call 结果。
        HiAgent 通过 notifications/progress 逐块推送内容，
        最后返回标准 JSON-RPC result。
        """
        payload = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
            "id": 2,
        }

        accumulated = ""
        final_result = None

        async with self.client.stream(
            "POST", url, headers=self.MCP_HEADERS, json=payload
        ) as response:
            if response.status_code != 200:
                body = await response.aread()
                return f"HTTP {response.status_code}: {body.decode()[:200]}"

            async for line in response.aiter_lines():
                line = line.strip()
                if not line:
                    continue
                json_str = line[5:].strip() if line.startswith("data:") else line
                if not json_str.startswith("{"):
                    continue
                try:
                    msg = json.loads(json_str)
                except Exception:
                    continue

                # 标准 JSON-RPC 最终结果
                if "result" in msg and "id" in msg:
                    result = msg["result"]
                    if isinstance(result, dict) and "content" in result:
                        texts = [
                            c.get("text", "")
                            for c in result["content"]
                            if c.get("type") == "text"
                        ]
                        final_result = "\n".join(texts)
                    else:
                        final_result = str(result)
                    continue

                # HiAgent progress 通知中的流式内容
                if msg.get("method") == "notifications/progress":
                    inner_msg = msg.get("params", {}).get("message", "")
                    try:
                        inner = json.loads(inner_msg)
                        if inner.get("event") == "message":
                            data_str = inner.get("data", "")
                            try:
                                data_obj = json.loads(data_str)
                                accumulated += data_obj.get("content", "")
                            except Exception:
                                accumulated += data_str
                    except Exception:
                        pass

        # 优先返回标准 result，否则返回累积的 progress 内容
        return final_result if final_result else accumulated

    # ── 适配器接口 ────────────────────────────────────────
    async def list_workflows(self) -> dict:
        """遍历所有已注册的 mcp_url，聚合工具列表"""
        urls = _get_hiagent_urls()
        if not urls:
            return {"code": -1, "msg": "未注册任何 hi-agent MCP URL", "data": []}

        all_tools: list[dict] = []
        errors: list[str] = []

        for url in urls:
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/list",
                "params": {},
                "id": 1,
            }
            try:
                r = await self.client.post(url, headers=self.MCP_HEADERS, json=payload)
                if r.status_code != 200:
                    errors.append(f"{url}: HTTP {r.status_code}")
                    continue

                data = self._parse_mcp_response(r.text)
                if data is None:
                    errors.append(f"{url}: 响应解析失败")
                    continue

                res = data.get("result", {})
                tools = []
                if isinstance(res, dict) and "tools" in res:
                    tools = res["tools"]
                elif isinstance(data, dict) and "tools" in data:
                    tools = data["tools"]
                elif isinstance(res, list):
                    tools = res

                for t in tools:
                    t_name = t.get("name", "")
                    if not t_name:
                        continue
                    schema = t.get("inputSchema", t.get("input_schema", {}))
                    # 缓存工具信息（用于后续 get_params / invoke）
                    self._tool_registry[t_name] = {
                        "url": url,
                        "description": t.get("description", ""),
                        "input_schema": schema,
                    }
                    all_tools.append(
                        {
                            "id": t_name,
                            "name": t_name,
                            "description": t.get("description", ""),
                        }
                    )
            except Exception as exc:
                errors.append(f"{url}: {exc}")

        result: dict = {"code": 0, "msg": "ok", "data": all_tools}
        if errors:
            result["errors"] = errors
        return result

    async def get_method_params(self, method_id: str) -> dict:
        """从缓存的 inputSchema 提取参数定义"""
        info = self._tool_registry.get(method_id)
        if not info:
            # 可能还没 list 过，先刷新
            await self.list_workflows()
            info = self._tool_registry.get(method_id)
        if not info:
            return {"code": -1, "msg": f"未找到工具: {method_id}", "data": []}

        schema = info.get("input_schema", {})
        props = schema.get("properties", {})
        formatted = []
        for k, v in props.items():
            formatted.append(
                {
                    "key": k,
                    "type": v.get("type", "string"),
                    "description": v.get("description", ""),
                    "required": k in schema.get("required", []),
                }
            )
        return {"code": 0, "msg": "ok", "data": formatted}

    async def invoke_method(self, method_id: str, params: dict | None = None) -> dict:
        """调用指定工具，SSE 流式读取完整结果"""
        info = self._tool_registry.get(method_id)
        if not info:
            await self.list_workflows()
            info = self._tool_registry.get(method_id)
        if not info:
            return {"code": -1, "msg": f"未找到工具: {method_id}", "data": {}}

        url = info["url"]
        exec_id = str(uuid.uuid4())[:8]

        try:
            result_text = await self._stream_tools_call(url, method_id, params or {})
            # 持久化结果到 SQLite
            self._save_exec(exec_id, method_id, "SUCCESS", result=result_text)
            return {
                "code": 0,
                "msg": "ok",
                "data": {"exec_id": exec_id, "result": result_text},
            }
        except Exception as exc:
            self._save_exec(exec_id, method_id, "FAILED", error=str(exc))
            return {"code": -1, "msg": f"调用失败: {exc}", "data": {}}

    async def get_exec_result(self, exec_id: str) -> dict:
        """查询 SQLite 中持久化的执行结果"""
        cached = self._load_exec(exec_id)
        if not cached:
            return {"code": -1, "msg": f"未找到执行记录: {exec_id}", "data": {}}
        if cached["status"] == "SUCCESS":
            return {"code": 0, "msg": "ok", "data": cached}
        return {"code": 1, "msg": cached.get("error", "执行失败"), "data": cached}


_ADAPTERS_MAP: dict = {
    "w5-soar": W5Adapter,
    "octomation": OctomationAdapter,
    "hi-agent": HiAgentAdapter,
}


def get_adapter(platform: str):
    key = (platform or "").strip().lower()
    if not key or key not in _ADAPTERS_MAP:
        return None
    try:
        return _ADAPTERS_MAP[key]()
    except ValueError as e:
        return {"code": -4, "msg": str(e), "data": {}}


def err_platform() -> dict:
    return {"code": -3, "msg": "platform 不存在", "data": {}}


@playbook_mcp.tool()
async def list_workflows(platform: str) -> dict:
    """获取剧本列表"""
    adapter = get_adapter(platform)
    if not adapter:
        return err_platform()
    if isinstance(adapter, dict):
        return adapter

    try:
        list_workflows_resp = await adapter.list_workflows()
        return list_workflows_resp
    except Exception as exc:
        return {"code": -1, "msg": f"请求失败: {exc}"}


@playbook_mcp.tool()
async def get_method_params(platform: str, method_id: str) -> dict:
    """获取剧本所需参数"""
    if not method_id:
        return {"code": -1, "msg": "method_id 不能为空", "data": {}}
    adapter = get_adapter(platform)
    if not adapter:
        return err_platform()
    if isinstance(adapter, dict):
        return adapter

    try:
        method_params = await adapter.get_method_params(method_id)
        return method_params
    except Exception as exc:
        return {"code": -1, "msg": f"请求失败: {exc}"}


@playbook_mcp.tool()
async def invoke_method(
    platform: str, method_id: str, params: dict | None = None
) -> dict:
    """调用剧本方法"""
    if not method_id:
        return {"code": -1, "msg": "method_id 不能为空", "data": {}}
    adapter = get_adapter(platform)
    if not adapter:
        return err_platform()
    if isinstance(adapter, dict):
        return adapter
    try:
        return await adapter.invoke_method(method_id, params or {})
    except Exception as exc:
        return {"code": -1, "msg": f"请求失败: {exc}"}


@playbook_mcp.tool()
async def get_exec_result(platform: str, exec_id: str) -> dict:
    """查询剧本执行结果"""
    if not exec_id:
        return {"code": -1, "msg": "exec_id 不能为空", "data": {}}
    adapter = get_adapter(platform)
    if not adapter:
        return err_platform()
    if isinstance(adapter, dict):
        return adapter

    last_resp: dict | None = None
    for attempt in range(3):
        try:
            resp = await adapter.get_exec_result(exec_id)
            last_resp = resp
            if isinstance(resp, dict) and resp.get("code") == 0:
                return resp
        except Exception as exc:
            last_resp = {"code": -1, "msg": f"请求失败: {exc}", "data": {}}

        if attempt < 2:
            delay = 0.5 * (2**attempt)
            await asyncio.sleep(delay)

    return last_resp or {"code": -1, "msg": "请求失败", "data": {}}
