"""Relative scan timestamps and the exact audio window supplied to the model."""

from __future__ import annotations

import math

from segment.music_agent.boundary_response import InvalidBoundary
from segment.music_agent.prompts import SCAN_PROMPT


def scan_prompt(window: tuple[float, float, float, float]) -> str:
    core_start, core_end, audio_start, audio_end = window
    duration = audio_end - audio_start
    return (
        f"{SCAN_PROMPT}\n本次输入音频总时长为 {duration:.6f} 秒，时间轴从 0 到 {duration:.6f} 秒。"
        f"核心区间为输入音频的 {core_start - audio_start:.6f} 到 {core_end - audio_start:.6f} 秒，"
        "核心区间前后的输入音频用于判断跨块歌曲。只返回与核心区间相交的候选。"
        f"所有候选必须满足 0 <= start_seconds < end_seconds <= {duration:.6f}。"
        "不得返回原视频绝对时间，也不得把分秒拼接为秒数。"
        "若歌曲跨越输入边缘，只报告本次音频内实际听到的部分，不推测音频之外的时间。"
    )


def scan_times(item: dict, duration: float | None = None) -> tuple[float, float]:
    raw = f"start_seconds={item.get('start_seconds')!r}, end_seconds={item.get('end_seconds')!r}"
    limit = "" if duration is None else f"，输入时长={duration:.6f}秒"
    try:
        start, end = float(item["start_seconds"]), float(item["end_seconds"])
    except (KeyError, TypeError, ValueError) as error:
        raise InvalidBoundary(f"扫描候选时间必须为秒数：{raw}{limit}") from error
    if not all(math.isfinite(value) for value in (start, end)) or not 0 <= start < end:
        raise InvalidBoundary(f"无效候选时间：{raw}{limit}")
    if duration is not None and end > duration:
        raise InvalidBoundary(f"扫描候选超出输入音频范围：{raw}{limit}")
    return start, end
