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
    return (
        f"上次回答未通过时间校验：{failure['error']}。请重新听同一段音频纠正，不沿用无效时间。"
        f"本次输入以0秒起算，总时长为{duration:.6f}秒，必须满足0 <= start_seconds < end_seconds <= {duration:.6f}。"
        "不得返回原视频绝对时间，不得把分秒拼接为秒数；若音乐超出输入，请用clipped_start/clipped_end表达。"
        f"上次回答：{json.dumps(failure['response']['data'], ensure_ascii=False)}"
    )
