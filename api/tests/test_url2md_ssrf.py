from __future__ import annotations

import socket

import httpx
import pytest

from api.services import url2md_service


@pytest.mark.asyncio
@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.1.1", "::1"])
async def test_url2md_rejects_non_public_dns_answers(monkeypatch, address: str) -> None:
    async def fake_getaddrinfo(*_args, **_kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443))]

    monkeypatch.setattr(url2md_service.anyio, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(url2md_service.UnsafeUrlError):
        await url2md_service.validate_public_http_url("https://example.test/article")


@pytest.mark.asyncio
async def test_url2md_rejects_non_http_schemes() -> None:
    with pytest.raises(url2md_service.UnsafeUrlError, match="scheme"):
        await url2md_service.validate_public_http_url("file:///etc/passwd")


@pytest.mark.asyncio
async def test_url2md_validates_redirect_destination(monkeypatch) -> None:
    checked_urls: list[str] = []

    async def fake_validate(url: str) -> str:
        checked_urls.append(url)
        if "127.0.0.1" in url:
            raise url2md_service.UnsafeUrlError("internal address")
        return url

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://127.0.0.1/private"})

    monkeypatch.setattr(url2md_service, "validate_public_http_url", fake_validate)
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(url2md_service.UnsafeUrlError, match="internal"):
            await url2md_service._get_public_url(client, "https://example.test/start")

    assert checked_urls == ["https://example.test/start", "http://127.0.0.1/private"]
