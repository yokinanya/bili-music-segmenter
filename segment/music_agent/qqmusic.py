"""QQ Music lyric verification using words heard in the actual interval."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable

from opencc import OpenCC

from segment.music_agent.recognition import normalize_title
from segment.music_agent.title_resolution import MINIMUM_TITLE_CONFIDENCE


def normalize_lyrics(value: str) -> str:
    text = OpenCC("t2s").convert(unicodedata.normalize("NFKC", value)).casefold()
    text = text.replace("\\n", "\n").replace("\\r", "\r").replace("著", "着")
    text = re.sub(r"\[[^\]]*\]", "", text)
    return "".join(character for character in text if character.isalnum())


async def verify_lyrics(audio_review: dict | None, search: Callable) -> dict:
    data = (audio_review or {}).get("data", {})
    query = data.get("lyrics_evidence", "")
    confidence = data.get("confidence", 0)
    if not isinstance(query, str):
        raise ValueError("音频复核 lyrics_evidence 必须为文本")
    if type(confidence) not in (int, float) or not 0 <= confidence <= 1:
        raise ValueError("音频复核置信度无效")
    normalized = normalize_lyrics(query)
    if not normalized or confidence < MINIMUM_TITLE_CONFIDENCE:
        return {"status": "insufficient_evidence", "query": query, "reason": "缺少清晰的连续实听歌词，或实听置信度不足"}
    results = await search(query)
    matches = [song for song in results if normalized in normalize_lyrics(song["lyrics"])]
    candidates = [{key: song[key] for key in ("id", "mid", "title", "artist")} for song in matches]
    evidence = {"query": query, "candidates": candidates, "method": "audio_lyrics_exact_match"}
    if not candidates:
        return {**evidence, "status": "no_match"}
    if len({normalize_title(song["title"]) for song in candidates}) != 1:
        return {**evidence, "status": "ambiguous"}
    return {**evidence, "status": "matched", **candidates[0]}


def apply_verification(current: tuple, verification: dict) -> tuple:
    title, artist, status = current
    if verification["status"] != "matched":
        return current
    if title and normalize_title(title) != normalize_title(verification["title"]):
        return "", "", "qqmusic_conflict"
    return title or verification["title"], artist or verification["artist"], "qqmusic_verified"
