"""Explicit, auditable correction requests for invalid audio boundaries."""

from __future__ import annotations

import json
import logging
import os

from segment.music_agent.runtime import CURRENT

LOGGER = logging.getLogger(__name__)
DEFAULT_BOUNDARY_RETRIES = 2
BOUNDARY_RETRIES_ENV = "MUSIC_AGENT_BOUNDARY_RETRIES"


class InvalidBoundary(ValueError):
    pass


def checked_boundary(request, window: dict, validate):
    retries = int(os.getenv(BOUNDARY_RETRIES_ENV, str(DEFAULT_BOUNDARY_RETRIES)))
    if retries < 0:
        raise ValueError(f"{BOUNDARY_RETRIES_ENV} 不能为负")
    correction = ""
    failures = []
    for attempt in range(retries + 1):
        response = (
            request(window["start"], window["end"], correction=correction)
            if correction
            else request(window["start"], window["end"])
        )
        try:
            result = validate(response)
        except InvalidBoundary as error:
            failure = {"attempt": attempt + 1, "error": str(error), "response": response}
            failures.append(failure)
            LOGGER.warning(
                "Invalid model boundary: window=%s attempt=%s/%s failure=%s",
                window,
                attempt + 1,
                retries + 1,
                json.dumps(failure, ensure_ascii=False),
            )
            if attempt == retries:
                raise InvalidBoundary(f"{error}；连续 {attempt + 1} 次校验失败，原始响应见日志") from error
            correction = _correction(window, failure)
            scope = CURRENT.get()
            if scope:
                scope.runtime.event(scope.step_id, "边界纠正", state="retrying", message=str(error))
            continue
        if failures:
            result[0] = {**result[0], "boundary_corrections": failures}
        return result
    raise AssertionError("边界调用未执行")


def _correction(window: dict, failure: dict) -> str:
    duration = window["end"] - window["start"]
    data = failure["response"]["data"]
    return (
        f"上次回答未通过音频校验：{failure['error']}。请重新听同一段音频，根据具体错误纠正回答。"
        f"本次输入以0秒起算，总时长为{duration:.6f}秒，必须满足0 <= start_seconds < end_seconds <= {duration:.6f}。"
        "不得返回原视频绝对时间，不得把分秒拼接为秒数。仅报告实际输入中能听到的区间。"
        f"{_grouping_correction(data)}"
        f"上次回答：{json.dumps(data, ensure_ascii=False)}"
    )


def _grouping_correction(data: dict) -> str:
    intervals = data.get("intervals")
    if not isinstance(intervals, list):
        return ""
    expected = list(range(len(intervals)))
    return (
        f"上次 intervals 有 {len(intervals)} 项，对应零起始编号 {expected!r}。"
        "重新确定属于同一次歌曲表演的连续区间并返回 song_groups，组内和组间按时间排列。"
        "编号必须为整数，每个区间恰好出现一次。若调整 intervals 数量，按新数组重新编号后再分组。"
    )
