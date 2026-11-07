"""Extend confirmed song tails within the media and the next performance."""

from __future__ import annotations

import math

TAIL_EXTENSION_SECONDS = 2.0


def extend_clip_tails(records: list[dict], duration: float) -> list[dict]:
    if not math.isfinite(duration) or duration <= 0:
        raise ValueError("切片尾部延长需要有效的源视频时长")
    entries = sorted(
        (interval["start_seconds"], interval["end_seconds"], row, column)
        for row, record in enumerate(records)
        for column, interval in enumerate(record.get("singing_intervals", []))
    )
    revised = {}
    for position, (start, end, row, column) in enumerate(entries):
        limit = min(duration, entries[position + 1][0]) if position + 1 < len(entries) else duration
        if not 0 <= start < end <= limit:
            raise ValueError(f"切片边界无效或仍有重叠：{start}–{end}，允许的结束上限为 {limit}")
        interval = records[row]["singing_intervals"][column]
        revised[row, column] = _extend_interval(interval, limit)
    return [
        {
            **record,
            "singing_intervals": [revised[row, column] for column, _ in enumerate(record.get("singing_intervals", []))],
        }
        for row, record in enumerate(records)
    ]


def _extend_interval(interval: dict, limit: float) -> dict:
    end = interval["end_seconds"]
    extended = min(end + TAIL_EXTENSION_SECONDS, limit)
    return {
        **interval,
        "end_seconds": extended,
        "duration_seconds": round(extended - interval["start_seconds"], 3),
        "tail_extension": {
            "original_end_seconds": end,
            "requested_seconds": TAIL_EXTENSION_SECONDS,
            "applied_seconds": round(extended - end, 3),
        },
    }
