"""Reference identification and safe title resolution."""

from __future__ import annotations

import asyncio
import re
import unicodedata
from pathlib import Path
from typing import Any

from opencc import OpenCC

from segment.netease import netease_orig
from segment.shazam import KoreanCharException, shazam_orig


def _outcome(result: tuple[Any, Any] | None, error: Exception | None) -> dict[str, Any]:
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
    shazam_result = None
    netease_result = None
    shazam_error = None
    netease_error = None
    if use_shazam:
        try:
            shazam_result = await asyncio.wait_for(shazam_orig(str(audio)), timeout=timeout)
        except KoreanCharException as error:
            shazam_error = ValueError(str(error))
        except Exception as error:  # noqa: BLE001 - provider errors are reported independently
            shazam_error = error
    if use_netease:
        try:
            netease_result = await asyncio.to_thread(
                lambda: asyncio.run(
                    netease_orig(
                        str(audio),
                        endpoint=netease_endpoint,
                        cookie=netease_cookie,
                        rejects=(),
                        timeout=timeout,
                    )
                )
            )
        except KoreanCharException as error:
            netease_error = ValueError(str(error))
        except Exception as error:  # noqa: BLE001 - provider errors are reported independently
            netease_error = error
    return {
        "shazam": _outcome(shazam_result, shazam_error) if use_shazam else {"status": "disabled"},
        "netease": _outcome(netease_result, netease_error) if use_netease else {"status": "disabled"},
    }


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


def resolve_title_with_model(references: dict[str, Any], model_result: dict[str, Any]) -> tuple[str, str, str]:
    choice = model_result.get("choice")
    if choice not in {"shazam", "netease", "unresolved"}:
        raise ValueError(f"Invalid Qwen title choice: {choice}")
    if choice == "unresolved" or float(model_result.get("confidence", 0)) < 0.85:
        return "", "", "unresolved"
    selected = references.get(choice, {})
    if selected.get("status") != "matched":
        return "", "", "unresolved"
    return selected.get("title", ""), selected.get("artist", ""), "qwen_resolved"
