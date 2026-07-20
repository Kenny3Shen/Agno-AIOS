"""Per-user Feishu webhook resolution."""

from __future__ import annotations

import pytest

from api.services import user_notification_settings_service as service


def test_is_secure_feishu_webhook_url():
    assert service.is_secure_feishu_webhook_url(
        "https://open.feishu.cn/open-apis/bot/v2/hook/abc"
    )
    assert not service.is_secure_feishu_webhook_url("http://insecure.example/hook")
    assert not service.is_secure_feishu_webhook_url("")


@pytest.mark.asyncio
async def test_resolve_prefers_user_webhook_over_global(monkeypatch):
    async def fake_user(user_id: str) -> str:
        assert user_id == "u1"
        return "https://open.feishu.cn/open-apis/bot/v2/hook/user"

    monkeypatch.setattr(service, "get_user_feishu_webhook_url", fake_user)
    monkeypatch.setattr(
        service,
        "global_feishu_webhook_url",
        lambda: "https://open.feishu.cn/open-apis/bot/v2/hook/global",
    )
    assert (
        await service.resolve_feishu_webhook_url("u1")
        == "https://open.feishu.cn/open-apis/bot/v2/hook/user"
    )


@pytest.mark.asyncio
async def test_resolve_falls_back_to_global(monkeypatch):
    async def fake_user(_user_id: str) -> str:
        return ""

    monkeypatch.setattr(service, "get_user_feishu_webhook_url", fake_user)
    monkeypatch.setattr(
        service,
        "global_feishu_webhook_url",
        lambda: "https://open.feishu.cn/open-apis/bot/v2/hook/global",
    )
    assert (
        await service.resolve_feishu_webhook_url("u1")
        == "https://open.feishu.cn/open-apis/bot/v2/hook/global"
    )


@pytest.mark.asyncio
async def test_update_rejects_insecure_url(monkeypatch):
    with pytest.raises(ValueError, match="https"):
        await service.update_user_feishu_webhook("u1", "http://bad.example/hook")


@pytest.mark.asyncio
async def test_feishu_notify_uses_personal_webhook_before_global(monkeypatch):
    """MCP tool prefers personal webhook over FEISHU_WEBHOOK_URL."""
    from pydantic import SecretStr

    from api.mcp.tools import basic

    posted: list[str] = []

    class _Settings:
        feishu_webhook_url = SecretStr("https://open.feishu.cn/open-apis/bot/v2/hook/global")

    class _Response:
        status_code = 200
        headers: dict[str, str] = {}

        def json(self):
            return {"code": 0}

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url: str, **_kwargs):
            posted.append(url)
            return _Response()

    async def fake_user_id() -> str:
        return "user-1"

    async def fake_user_webhook(user_id: str) -> str:
        assert user_id == "user-1"
        return "https://open.feishu.cn/open-apis/bot/v2/hook/personal"

    monkeypatch.setattr("api.config.get_settings", lambda: _Settings())
    monkeypatch.setattr(basic, "_current_mcp_user_id", fake_user_id)
    monkeypatch.setattr(basic, "_user_webhook_url", fake_user_webhook)
    monkeypatch.setattr(basic.httpx, "AsyncClient", _Client)

    result = await basic.send_feishu_notify(
        title="t",
        content_md="hello",
        template="blue",
        max_retries=0,
    )
    assert result.status == "sent"
    assert posted == ["https://open.feishu.cn/open-apis/bot/v2/hook/personal"]
