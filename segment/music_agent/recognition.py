"""Reference identification and safe title resolution."""

from __future__ import annotations

import asyncio
import unicodedata
from pathlib import Path
from typing import Any

from opencc import OpenCC

from segment.music_agent.runtime import CURRENT, fingerprint
from segment.netease import NetEaseDisagreement, NetEaseNoMatch, netease_orig, variant_free
from segment.shazam import create_client, parse_shazam_response, shazam_title

# 网易云改为多采样点投票后，旧缓存里的单点结果不能复用。
NETEASE_VOTE_VERSION = "netease-vote-v1"


def _outcome(result: tuple[Any, Any] | None, error: BaseException | None) -> dict[str, Any]:
    if error is not None:
        return {"status": "error", "error": f"{type(error).__name__}: {str(error)[:300]}"}
    if result is None:
        return {"status": "no_match"}
    (title, artist), raw = result
    raw_match = None
    if isinstance(raw, dict):
        raw_match = {key: raw[key] for key in ("title", "subtitle", "id", "name", "artist") if key in raw}
    return {"status": "matched", "title": title, "artist": artist, "raw": raw_match}


async def recognize_audio(
    audio: Path,
    *,
    netease_cookie: str = "",
    timeout: int = 60,
    use_shazam: bool = True,
    use_netease: bool = True,
    budget: asyncio.Semaphore | None = None,
    netease_budget: asyncio.Semaphore | None = None,
    shazam_proxy: str | None = None,
) -> dict[str, Any]:
    """Query both recognizers concurrently, so one slow provider does not double the per-interval wait.

    网易云对上游更敏感，可以用更低的独立额度；未提供时退回共享额度。
    """
    runners = {}
    if use_shazam:
        runners["shazam"] = lambda: _run_shazam(str(audio), timeout, shazam_proxy)
    if use_netease:
        runners["netease"] = lambda: asyncio.to_thread(_netease_blocking, str(audio), netease_cookie, timeout)

    async def invoke(provider, run):
        scope = CURRENT.get()
        # Shazam 走代理时，同一段音频的直连缓存结果不能复用。
        identity_key = [str(audio), provider] + ([shazam_proxy] if provider == "shazam" else [])
        identity = "recognition/" + fingerprint(identity_key)

        async def request():
            async def call():
                result = await run()
                if result["status"] == "error":
                    raise RuntimeError(result["error"])
                return result

            limit = netease_budget if provider == "netease" and netease_budget is not None else budget
            if limit is None:
                return await call()
            if scope:
                scope.runtime.event(identity, f"{provider} 识曲", state="waiting")
            async with limit:
                if scope:
                    scope.runtime.event(identity, f"{provider} 识曲", state="running")
                return await call()

        if scope:
            return await scope.runtime.async_run(
                {
                    "id": identity,
                    "label": f"{provider} 识曲",
                    "input": identity_key,
                },
                request,
            )
        return await request()

    results = await asyncio.gather(
        *(invoke(provider, run) for provider, run in runners.items()), return_exceptions=True
    )
    if not any(isinstance(result, dict) and result.get("status") == "matched" for result in results):
        for result in results:
            if isinstance(result, BaseException):
                raise result
    outcome = {
        provider: _outcome(None, result) if isinstance(result, Exception) else result
        for provider, result in zip(runners, results, strict=True)
    }
    for result in results:
        if isinstance(result, BaseException) and not isinstance(result, Exception):
            raise result
    # A disabled provider stays explicitly disabled so the record never looks like a failed match.
    return {
        "shazam": outcome.get("shazam", {"status": "disabled"}),
        "netease": outcome.get("netease", {"status": "disabled"}),
    }


async def _run_shazam(audio: str, timeout: int, proxy: str | None = None) -> dict:
    try:
        scope = CURRENT.get()
        if scope is None:
            # 不走 shazam_orig：它按路径识别，会把文件校验压到 asyncio 默认线程池里。
            client = create_client(proxy)
            try:
                match = await asyncio.wait_for(client.recognize(audio), timeout=timeout)
            finally:
                await client.close()
            track = parse_shazam_response(match)
            return _outcome((shazam_title(track), track) if track else None, None)
        if proxy is not None:
            client = create_client(proxy)
        else:
            client = scope.runtime.shazam_client
        try:
            match = await asyncio.wait_for(client.recognize(audio), timeout=timeout)
        finally:
            if proxy is not None:
                await client.close()
        track = parse_shazam_response(match)
        return _outcome((shazam_title(track), track) if track else None, None)
    except Exception as error:
        return _outcome(None, error)


def _netease_blocking(audio: str, cookie: str, timeout: int) -> dict[str, Any]:
    """``netease_orig`` 是同步的（FFmpeg + Node），因此独占一个工作线程。

    多个采样点串行执行，整体时限设为 ``timeout``，避免慢网络下累计等待数倍超时。
    """
    try:
        return _outcome(netease_orig(audio, cookie=cookie, rejects=(), timeout=timeout, deadline=timeout), None)
    except (NetEaseNoMatch, NetEaseDisagreement) as error:
        return netease_outcome(error)
    except Exception as error:
        return _outcome(None, error)


def netease_outcome(error: BaseException) -> dict[str, Any]:
    """不同起点识别到不同作品时标记 conflict 交给人工选择，不能静默采用其中一个。"""
    if isinstance(error, NetEaseDisagreement):
        return {"status": "conflict", "error": str(error), "samples": [list(item) for item in error.groups]}
    if isinstance(error, NetEaseNoMatch):
        return {"status": "no_match"}
    return _outcome(None, error)


def normalize_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", OpenCC("t2s").convert(value)).casefold()
    # 只剥离版本附注（cover/伴奏/纯享版…），歌名本身不同的括号内容必须保留。
    text = variant_free(text)
    return "".join(char for char in text if char.isalnum())


def deterministic_title_choice(
    references: dict[str, Any],
) -> tuple[str, str, str]:
    """歌名决定结论，歌手只作展示：同名不同歌手不算冲突。"""
    shazam = references.get("shazam", {})
    netease = references.get("netease", {})
    shazam_ok = shazam.get("status") == "matched"
    netease_ok = netease.get("status") == "matched"
    # 网易云各采样点识别到不同作品时，不能当作"没有结果"，等同识曲冲突交给人工。
    if netease.get("status") == "conflict":
        return "", "", "conflict"
    if shazam_ok and netease_ok:
        first = normalize_title(shazam.get("title", ""))
        second = normalize_title(netease.get("title", ""))
        if first == second:
            title = netease.get("title") or shazam.get("title", "")
            return title, netease.get("artist") or shazam.get("artist", ""), "matched"
        return "", "", "conflict"
    if netease_ok:
        return netease.get("title", ""), netease.get("artist", ""), "single_provider"
    if shazam_ok:
        return shazam.get("title", ""), shazam.get("artist", ""), "single_provider"
    return "", "", "unmatched"
