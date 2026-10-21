"""Reference identification and safe title resolution."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import Any

from opencc import OpenCC

from segment.netease import netease_orig
from segment.shazam import shazam_orig


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
    netease_endpoint: str,
    netease_cookie: str = "",
    timeout: int = 60,
    use_shazam: bool = True,
    use_netease: bool = True,
) -> dict[str, Any]:
    """Query both recognizers concurrently, so one slow provider does not double the per-interval wait."""
    runners: dict[str, Callable[[], dict[str, Any]]] = {}
    if use_shazam:
        runners["shazam"] = lambda: _shazam_blocking(str(audio), timeout)
    if use_netease:
        runners["netease"] = lambda: _netease_blocking(str(audio), netease_endpoint, netease_cookie, timeout)
    results = await asyncio.gather(*(asyncio.to_thread(run) for run in runners.values()))
    outcome = dict(zip(runners, results, strict=True))
    # A disabled provider stays explicitly disabled so the record never looks like a failed match.
    return {
        "shazam": outcome.get("shazam", {"status": "disabled"}),
        "netease": outcome.get("netease", {"status": "disabled"}),
    }


def _shazam_blocking(audio: str, timeout: int) -> dict[str, Any]:
    try:
        return _outcome(asyncio.run(asyncio.wait_for(shazam_orig(audio), timeout=timeout)), None)
    except BaseException as error:  # noqa: BLE001 - Korean titles and provider errors are both reported
        return _outcome(None, error)


def _netease_blocking(audio: str, endpoint: str, cookie: str, timeout: int) -> dict[str, Any]:
    """``netease_orig`` is fully blocking (ffmpeg + node + requests), hence the worker thread."""
    try:
        return _outcome(
            asyncio.run(netease_orig(audio, endpoint=endpoint, cookie=cookie, rejects=(), timeout=timeout)),
            None,
        )
    except BaseException as error:  # noqa: BLE001 - Korean titles and provider errors are both reported
        return _outcome(None, error)


def normalize_title(value: str) -> str:
    text = unicodedata.normalize("NFKC", OpenCC("t2s").convert(value)).casefold()
    text = re.sub(r"[（(][^）)]*[）)]", " ", text)
    text = re.sub(r"\b(?:live|伴奏|翻唱|翻自|remaster(?:ed)?|version)\b", " ", text)
    return "".join(char for char in text if char.isalnum())


def deterministic_title_choice(
    references: dict[str, Any],
) -> tuple[str, str, str]:
    shazam = references.get("shazam", {})
    netease = references.get("netease", {})
    shazam_ok = shazam.get("status") == "matched"
    netease_ok = netease.get("status") == "matched"
    if shazam_ok and netease_ok:
        first = shazam.get("title", "")
        second = netease.get("title", "")
        if normalize_title(first) == normalize_title(second):
            return second or first, netease.get("artist") or shazam.get("artist", ""), "matched"
        return "", "", "conflict"
    if netease_ok:
        return netease.get("title", ""), netease.get("artist", ""), "single_provider"
    if shazam_ok:
        return shazam.get("title", ""), shazam.get("artist", ""), "single_provider"
    return "", "", "unmatched"


MINIMUM_TEXT_TITLE_CONFIDENCE = 0.85


def resolve_title_with_model(references: dict[str, Any], model_result: dict[str, Any]) -> tuple[str, str, str]:
    """Pick a provider using the text reviewer's verdict; the caller still decides whether audio is needed."""
    choice = model_result.get("choice")
    if choice not in {"shazam", "netease", "unresolved"}:
        raise ValueError(f"Invalid Qwen title choice: {choice}")
    confidence = model_result.get("confidence")
    if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
        raise ValueError("文本标题裁决置信度无效")
    if choice == "unresolved" or confidence < MINIMUM_TEXT_TITLE_CONFIDENCE:
        return "", "", "unresolved"
    selected = references.get(choice, {})
    if selected.get("status") != "matched":
        return "", "", "unresolved"
    return selected.get("title", ""), selected.get("artist", ""), "qwen_resolved"
