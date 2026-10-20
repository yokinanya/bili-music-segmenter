"""Automatic audio-grounded song grouping and context expansion."""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

CONTEXT_GROWTH = 2
MINIMUM_CONTEXT_SECONDS = 20
GROUPING_PROMPT = """\n本次是完整单曲边界复核，必须额外返回 song_groups 数组和 clipped_start、clipped_end 布尔值。
intervals 按时间顺序列出演唱区间；song_groups 每项为属于同一次完整歌曲表演的 intervals 零起始编号数组。
仅有声学证据证明中间为同曲间奏、换气、短暂插话时将区间分到同组；换歌或独立聊天必须分组。
例如同曲三段返回 song_groups=[[0,1,2]]，不同歌曲返回 [[0],[1]]；每个区间必须恰好出现一次。
同组首尾应包含已确认的前奏尾奏。音乐在输入开头已存在且真实前奏未找到时 clipped_start=true；
音乐在输入结束仍继续且真实尾奏未找到时 clipped_end=true，否则 false。不能把未知当作边界已确认。
"""


@dataclass(frozen=True)
class BoundaryOptions:
    start: float
    end: float
    duration: float
    context: float
    minimum_confidence: float


def review_boundaries(options: BoundaryOptions, request: Callable) -> tuple[list[tuple[float, float]], dict]:
    context = max(options.context, 0)
    history = []
    while True:
        start = max(0.0, options.start - context)
        end = min(options.duration, options.end + context)
        response = request(start, end)
        data = response["data"]
        intervals = _parse_intervals(data, end - start, options.minimum_confidence)
        grouped = _group_intervals(intervals, data)
        history.append({"input_start": start, "input_end": end, "response": response})
        left = bool(intervals) and (grouped[0][0] == 0 or data.get("clipped_start") is True)
        right = bool(intervals) and (grouped[-1][1] == end - start or data.get("clipped_end") is True)
        if not ((left and start > 0) or (right and end < options.duration)):
            return [(start + a, start + b) for a, b in grouped], {
                **response,
                "boundary_attempts": history,
                "media_start_reached": left and start == 0,
                "media_end_reached": right and end == options.duration,
            }
        context = min(options.duration, max(MINIMUM_CONTEXT_SECONDS, context * CONTEXT_GROWTH))


def _parse_intervals(data: dict, duration: float, confidence_threshold: float) -> list[tuple[float, float]]:
    confidence = float(data.get("confidence", 0))
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("模型返回了无效置信度")
    if data.get("host_singing_present") is not True or confidence < confidence_threshold:
        return []
    intervals = []
    for item in data.get("intervals", []):
        start, end = float(item["start_seconds"]), float(item["end_seconds"])
        if not all(math.isfinite(x) for x in (start, end)) or not 0 <= start < end <= duration:
            raise ValueError("模型演唱边界超出输入音频或时间无效")
        if intervals and start < intervals[-1][1]:
            raise ValueError("模型演唱区间必须按时间排序且不重叠")
        intervals.append((start, end))
    return intervals


def _group_intervals(intervals: list[tuple[float, float]], data: dict) -> list[tuple[float, float]]:
    if not intervals:
        return []
    groups = data.get("song_groups")
    if groups is None:
        if len(intervals) == 1:
            return intervals
        raise ValueError("多个演唱区间缺少 song_groups，无法确定同曲间奏，不自动拆段")
    if not isinstance(groups, list) or any(not isinstance(group, list) or not group for group in groups):
        raise ValueError("song_groups 格式无效")
    indices = [index for group in groups for index in group]
    if any(type(index) is not int for index in indices) or indices != list(range(len(intervals))):
        raise ValueError("song_groups 必须按时间连续覆盖每个区间且不得重复")
    return [(intervals[group[0]][0], intervals[group[-1]][1]) for group in groups]
