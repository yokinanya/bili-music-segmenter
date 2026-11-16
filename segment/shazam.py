"""Shazam reference matching without global clients or post-request sleeps."""

import asyncio
import re

from aiohttp import ClientSession, ClientTimeout
from aiohttp_retry import ExponentialRetry, RetryClient
from shazamio import Shazam
from shazamio.client import HTTPClient

RETRY_ATTEMPTS = 20
RETRY_MAX_TIMEOUT = 60
RETRY_STATUSES = frozenset({500, 502, 503, 504, 429})
CONNECT_TIMEOUT_SECONDS = 30


class ShazamProxyClient(HTTPClient):
    """把请求固定走显式代理，不读取环境变量代理。"""

    def __init__(self, proxy):
        super().__init__(
            retry_options=ExponentialRetry(
                attempts=RETRY_ATTEMPTS, max_timeout=RETRY_MAX_TIMEOUT, statuses=RETRY_STATUSES
            )
        )
        self.proxy = proxy

    def _ensure_client(self):
        loop = asyncio.get_running_loop()
        if self._retry_client is None or (self._loop is not loop and not self._closed):
            session = ClientSession(
                trust_env=False,
                timeout=ClientTimeout(connect=CONNECT_TIMEOUT_SECONDS),
                trace_configs=[self.trace_config],
            )
            self._retry_client = RetryClient(
                client_session=session,
                retry_options=self.retry_options,
                raise_for_status=False,
            )
            self._loop = loop
        return self._retry_client

    async def request(self, method, url, **kwargs):
        kwargs["proxy"] = self.proxy
        return await super().request(method, url, **kwargs)

    async def request_text(self, url, *, content_type, **kwargs):
        kwargs["proxy"] = self.proxy
        return await super().request_text(url, content_type=content_type, **kwargs)


class ShazamWithProxy(Shazam):
    def __init__(self, proxy):
        self._proxy_client = ShazamProxyClient(proxy)
        super().__init__(http_client=self._proxy_client)

    async def close(self):
        await self._proxy_client.close()


def create_client(proxy):
    """代理为空时沿用 shazamio 默认客户端，保持原有直连行为。"""
    if proxy is None:
        return Shazam()
    return ShazamWithProxy(proxy)


async def shazam_orig(file, proxy=None, **kwargs):
    match = await shazam(file, proxy=proxy)
    return (shazam_title(match), match) if match is not None else None


async def shazam(file, proxy=None):
    client = create_client(proxy)
    try:
        response = await client.recognize(file)
    finally:
        await client.close()
    return parse_shazam_response(response)


def parse_shazam_response(response):
    if not isinstance(response, dict):
        raise ValueError("Shazam 响应必须是对象")
    if "track" in response:
        track = response["track"]
        if not isinstance(track, dict) or not all(isinstance(track.get(key), str) for key in ("title", "subtitle")):
            raise ValueError("Shazam track 缺少有效歌名或歌手")
        return track
    if response.get("matches") == []:
        return None
    raise ValueError(f"Shazam 响应缺少 track，字段：{sorted(response)}")


def legalize_filename(value):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", value).strip()


def shazam_title(match):
    return [legalize_filename(match["title"]), legalize_filename(match["subtitle"])]
