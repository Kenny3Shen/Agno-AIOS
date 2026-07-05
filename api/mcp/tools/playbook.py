import asyncio
from fastmcp import FastMCP
import httpx

from api.config import get_settings
from api.services.runtime_env import load_runtime_env_async

playbook_mcp = FastMCP("Playbook")


class W5Adapter:
    def __init__(self):
        settings = get_settings()
        self.token = settings.w5_soar_token.get_secret_value()
        if not self.token:
            raise ValueError("W5_SOAR_TOKEN 环境变量未设置")
        self.api_base = settings.w5_api_base
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
        settings = get_settings()
        self.token = settings.octomation_token.get_secret_value()
        if not self.token:
            raise ValueError("OCTOMATION_TOKEN 环境变量未设置")
        self.api_base = settings.octomation_api_base
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





_ADAPTERS_MAP: dict = {
    "w5-soar": W5Adapter,
    "octomation": OctomationAdapter,
}


async def get_adapter(platform: str):
    await load_runtime_env_async()
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
    adapter = await get_adapter(platform)
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
    adapter = await get_adapter(platform)
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
    adapter = await get_adapter(platform)
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
    adapter = await get_adapter(platform)
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
