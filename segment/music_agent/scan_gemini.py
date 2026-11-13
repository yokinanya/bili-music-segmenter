"""Gemini 一次出点位：整场或分块扫描，直接给出完整歌曲边界。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from segment.music_agent.boundaries import InvalidBoundary
from segment.music_agent.media import extract_wav, make_windows, media_duration
from segment.music_agent.prompts import SCAN_PROMPT

VALID_CLASSES = {"host_singing", "background_music_chat", "mixed_singing_and_chat", "uncertain"}
# 相邻分块的边界分歧：相差不到该秒数的候选视为同一首。
BORDER_DUPLICATE_SECONDS = 5.0

SEGMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_seconds": {"type": "number"},
                    "end_seconds": {"type": "number"},
                    "classification": {"type": "string", "enum": sorted(VALID_CLASSES)},
                    "confidence": {"type": "number"},
                    "host_singing_present": {"type": "boolean"},
                    "title_hint": {"type": "string"},
                    "announcer_hint": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["start_seconds", "end_seconds", "classification"],
            },
        }
    },
    "required": ["segments"],
}


@dataclass(frozen=True)
class Candidate:
    index: int
    start: float
    end: float
    classification: str
    confidence: float
    host_singing_present: bool
    title_hint: str
    rationale: str
    announcer_hint: str = ""


@dataclass(frozen=True)
class Window:
    core_start: float
    core_end: float
    audio_start: float
    audio_end: float


def scan_prompt(window: Window) -> str:
    duration = window.audio_end - window.audio_start
    text = (
        f"{SCAN_PROMPT}\n本次输入音频总时长为 {duration:.3f} 秒，时间轴从 0 到 {duration:.3f} 秒。"
        f"所有候选必须满足 0 <= start_seconds < end_seconds <= {duration:.3f}。"
        "不得返回原视频绝对时间，也不得把分秒拼接为秒数。"
    )
    if (window.core_start, window.core_end) != (window.audio_start, window.audio_end):
        text += (
            f"核心区间为输入音频的 {window.core_start - window.audio_start:.3f} 到 "
            f"{window.core_end - window.audio_start:.3f} 秒，只返回与核心区间相交的候选；"
            "前后的附加音频仅用于判断跨块歌曲，边界可落在附加音频内，但不得超出总时长。"
        )
    else:
        text += "本次是整场音频，返回全部与主播演唱相关的候选，不因音频很长而合并或省略。"
    return text


def scan_candidates(media: Path, client: Any, *, chunk_seconds: int, chunk_context: int, minimum_seconds: float):
    """扫描整场音频；分块时按核心区间去重合并。"""
    duration = media_duration(media)
    windows = [Window(*item) for item in make_windows(duration, chunk_seconds, chunk_context)]
    collected: list[Candidate] = []
    chunks = []
    for number, window in enumerate(windows, start=1):
        wav = _extract(client, media, window)
        response = client.json_call(wav, scan_prompt(window), SEGMENT_SCHEMA, label=f"扫描分块 {number}")
        current = parse_candidates(response["data"], window)
        if len(windows) > 1:
            current = _core_only(current, window)
        collected.extend(current)
        chunks.append({**window.__dict__, "chunk": number, "candidate_count": len(current), "usage": response["usage"]})
    merged = merge_candidates(collected, BORDER_DUPLICATE_SECONDS)
    kept = [item for item in merged if item.end - item.start >= minimum_seconds]
    return _reindex(kept), chunks


def parse_candidates(data: dict, window: Window) -> list[Candidate]:
    limit = window.audio_end - window.audio_start
    items = data.get("segments")
    if not isinstance(items, list):
        raise ValueError("扫描结果缺少 segments 数组")
    candidates = []
    for item in items:
        start, end = float(item["start_seconds"]), float(item["end_seconds"])
        if not all(math.isfinite(value) for value in (start, end)) or not 0 <= start < end <= limit + 1.0:
            raise InvalidBoundary(f"扫描候选超出输入范围：{start}-{end}（上限 {limit:.3f}）")
        classification = item.get("classification")
        if classification not in VALID_CLASSES:
            raise ValueError(f"无效歌曲分类：{classification}")
        confidence = float(item.get("confidence", 0))
        if not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError(f"无效候选置信度：{confidence}")
        candidates.append(
            Candidate(
                index=0,
                start=window.audio_start + start,
                end=window.audio_start + end,
                classification=classification,
                confidence=confidence,
                host_singing_present=item.get("host_singing_present") is True,
                title_hint=str(item.get("title_hint", "")),
                rationale=str(item.get("rationale", "")),
                announcer_hint=str(item.get("announcer_hint", "")),
            )
        )
    return candidates


def merge_candidates(candidates: list[Candidate], max_gap: float = 0) -> list[Candidate]:
    """合并重叠或边界分歧在容差内的候选，跨块结果不会被重复处理和识别。"""
    merged: list[Candidate] = []
    for candidate in sorted(candidates, key=lambda item: (item.start, item.end)):
        if merged and _same_song(merged[-1], candidate) and candidate.start < merged[-1].end + max(0.5, max_gap):
            previous = merged[-1]
            classes = {previous.classification, candidate.classification}
            merged[-1] = Candidate(
                index=0,
                start=previous.start,
                end=max(previous.end, candidate.end),
                classification="mixed_singing_and_chat" if len(classes) > 1 else previous.classification,
                confidence=min(previous.confidence, candidate.confidence),
                host_singing_present=previous.host_singing_present or candidate.host_singing_present,
                title_hint=previous.title_hint or candidate.title_hint,
                announcer_hint=previous.announcer_hint or candidate.announcer_hint,
                rationale=" ".join(filter(None, (previous.rationale, candidate.rationale))),
            )
        else:
            merged.append(candidate)
    return merged


def _same_song(first: Candidate, second: Candidate) -> bool:
    """只有能确认是同一首歌时才合并；歌名不同或类别不同都保持独立。"""
    if first.title_hint and second.title_hint:
        return first.title_hint == second.title_hint
    return first.classification == second.classification


def _core_only(candidates: list[Candidate], window: Window) -> list[Candidate]:
    return [item for item in candidates if item.end > window.core_start and item.start < window.core_end]


def _reindex(candidates: list[Candidate]) -> list[Candidate]:
    return [
        Candidate(
            index=index,
            **{key: value for key, value in candidate.__dict__.items() if key != "index"},
        )
        for index, candidate in enumerate(candidates, start=1)
    ]


def _extract(client: Any, media: Path, window: Window) -> Path:
    return client.audio_window(media, window.audio_start, window.audio_end, extract_wav)
