"""Shazam 代理注入：显式代理优先，未配置时保持直连。"""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from segment import shazam
from segment.music_agent.config import proxy_from_env


def test_no_proxy_keeps_default_client():
    client = shazam.create_client(None)
    assert type(client) is shazam.Shazam


def test_proxy_client_forwards_proxy(monkeypatch):
    seen = []

    async def fake_request(self, method, url, **kwargs):
        seen.append((method, proxy_of(kwargs)))
        return {}

    async def fake_request_text(self, url, **kwargs):
        seen.append(("GET", proxy_of(kwargs)))
        return "csv"

    def proxy_of(kwargs):
        return kwargs.get("proxy")

    monkeypatch.setattr(shazam.HTTPClient, "request", fake_request)
    monkeypatch.setattr(shazam.HTTPClient, "request_text", fake_request_text)
    http = shazam.ShazamProxyClient("http://127.0.0.1:7890")
    asyncio.run(http.request("POST", "https://example.test", proxy=None))
    asyncio.run(http.request_text("https://example.test", content_type="text/csv", proxy="http://other.example"))
    assert seen == [("POST", "http://127.0.0.1:7890"), ("GET", "http://127.0.0.1:7890")]


def test_proxy_client_disables_environment_proxy():
    client = shazam.create_client("http://127.0.0.1:7890")

    async def run():
        built = client.http_client._ensure_client()
        try:
            trust_env = built._client.trust_env
        finally:
            await client.close()
        return trust_env, built._client.closed

    assert asyncio.run(run()) == (False, True)


def test_shazam_proxy_requires_scheme(monkeypatch):
    monkeypatch.setenv("SHAZAM_PROXY", "127.0.0.1:7890")
    with pytest.raises(ValueError, match="SHAZAM_PROXY"):
        proxy_from_env("SHAZAM_PROXY")


def test_shazam_proxy_is_read_from_env(monkeypatch):
    monkeypatch.delenv("SHAZAM_PROXY", raising=False)
    assert proxy_from_env("SHAZAM_PROXY") is None
    monkeypatch.setenv("SHAZAM_PROXY", " socks5://127.0.0.1:1080 ")
    assert proxy_from_env("SHAZAM_PROXY") == "socks5://127.0.0.1:1080"


def test_run_shazam_uses_proxy_client(monkeypatch):
    """流水线内的识曲必须把代理交给客户端，不能复用无代理的共享 client。"""
    from segment.music_agent import recognition

    used = []

    class Stub:
        async def recognize(self, audio):
            used.append(("recognize", audio))
            return {"track": {"title": "歌", "subtitle": "人"}}

        async def close(self):
            used.append("closed")

    def create(proxy):
        used.append(proxy)
        return Stub()

    audio = Path("a.mp3")
    monkeypatch.setattr(recognition, "create_client", create)
    # 识别真实音频时核心识别器会卡在自带的 executor 上，这里只验证客户端装配与释放。
    monkeypatch.setattr(recognition, "asyncio", SimpleNamespace(wait_for=lambda awaitable, timeout: awaitable))
    result = asyncio.run(recognition._run_shazam(audio, 60, "http://127.0.0.1:7890"))
    assert result["status"] == "matched"
    assert used == ["http://127.0.0.1:7890", ("recognize", audio), "closed"]
    assert result["status"] == "matched"
    assert used == ["http://127.0.0.1:7890", ("recognize", audio), "closed"]
