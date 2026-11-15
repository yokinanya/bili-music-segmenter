"""Gemini 一次出点位：整场或分块扫描，直接给出完整歌曲边界。"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from contextvars import copy_context
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

from google.genai.errors import APIError
from httpx import HTTPError

from segment.music_agent.boundaries import InvalidBoundary
from segment.music_agent.media import extract_wav, make_windows, media_duration
from segment.music_agent.prompts import SCAN_PROMPT
from segment.music_agent.runtime import CURRENT, FIXED_BUDGETS

VALID_CLASSES = {"host_singing", "background_music_chat", "mixed_singing_and_chat", "uncertain"}
# 相邻分块的边界分歧：相差不到该秒数的候选视为同一首。
BORDER_DUPLICATE_SECONDS = 5.0
# 与 runtime 的 model 预算一致：超过这个并发数只会在预算上排队。
SCAN_CONCURRENCY = FIXED_BUDGETS["model"]
MAX_SCAN_ATTEMPTS = 2
SCAN_VALIDATION_VERSION = "validated-chunks-v1"

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


def scan_schema(window: Window) -> dict:
    schema = deepcopy(SEGMENT_SCHEMA)
    properties = schema["properties"]["segments"]["items"]["properties"]
    for name in ("start_seconds", "end_seconds"):
        properties[name].update(minimum=0, maximum=window.audio_end - window.audio_start)
    properties["confidence"].update(minimum=0, maximum=1)
    properties["title_hint"]["description"] = "仅作品正式名称；无法确认时为空，不包含说明、推理或备选名。"
    properties["rationale"]["description"] = "简要说明演唱者归属及切点依据；解释只放在此字段。"
    return schema


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
    """扫描整场音频；分块时并发调用模型，再按核心区间去重合并。

    每个分块是独立的模型请求，串行会把总耗时放大成窗口数量倍。
    """
    duration = media_duration(media)
    windows = [Window(*item) for item in make_windows(duration, chunk_seconds, chunk_context)]
    scanned = _scan_windows(media, client, windows, concurrent=len(windows) > 1)
    collected: list[Candidate] = []
    chunks = []
    for number, (window, result) in enumerate(scanned, start=1):
        current = [Candidate(**item) for item in result["candidates"]]
        collected.extend(current)
        chunks.append(
            {
                **window.__dict__,
                "chunk": number,
                **{key: value for key, value in result.items() if key != "candidates"},
                "candidate_count": len(current),
            }
        )
    merged = merge_candidates(collected, BORDER_DUPLICATE_SECONDS)
    kept = [item for item in merged if item.end - item.start >= minimum_seconds]
    return _reindex(kept), chunks


def _scan_windows(media: Path, client: Any, windows: list[Window], *, concurrent: bool):
    """按窗口顺序返回结果，模型并发不改变候选顺序和去重语义。"""

    def scan(number: int, window: Window):
        return window, _scan_window(media, client, (number, window))

    if not windows:
        return []
    if not concurrent:
        return [scan(1, windows[0])]
    return run_parallel([partial(scan, number, window) for number, window in enumerate(windows, start=1)])


def run_parallel(work: list) -> list:
    """保留任务上下文与输入顺序，共享媒体预算和检查点。"""
    with ThreadPoolExecutor(max_workers=min(SCAN_CONCURRENCY, len(work))) as pool:
        futures = [pool.submit(copy_context().run, item) for item in work]
        return [future.result() for future in futures]


def _scan_window(media: Path, client: Any, numbered: tuple[int, Window]) -> dict:
    number, window = numbered
    scope = CURRENT.get()
    spec = {
        "id": f"scan-window/{number}",
        "label": f"校验扫描分块 {number}",
        "input": [
            SCAN_VALIDATION_VERSION,
            window.__dict__,
            scan_prompt(window),
            scan_schema(window),
            getattr(client, "model", None),
        ],
    }
    work = partial(_request_window, media, client, numbered)
    try:
        return scope.runtime.run(spec, work) if scope else work()
    except (ValueError, KeyError, TypeError, RuntimeError, OSError, APIError, HTTPError) as error:
        return {"candidates": [], "usage": None, "state": "failed", "error": f"{type(error).__name__}: {error}"}


def _request_window(media: Path, client: Any, numbered: tuple[int, Window]) -> dict:
    number, window = numbered
    wav = _extract(client, media, window)
    errors = []
    scope = CURRENT.get()
    for attempt in range(MAX_SCAN_ATTEMPTS):
        correction = (
            ""
            if not errors
            else (
                f"\n上次响应无效：{errors[-1]}。请重新听本段音频后输出完整 JSON，不要续写残缺响应。"
                "时间必须是本段音频内的相对秒数，start_seconds 严格小于 end_seconds；"
                "不要交换、猜测或截断错误点位。说明保持简短，但不得省略歌曲。"
            )
        )
        budget = scope.runtime.resource("model") if scope else nullcontext()
        try:
            with budget:
                retry_options = {"cache": False} if attempt else {}
                response = client.json_call(
                    wav,
                    scan_prompt(window) + correction,
                    scan_schema(window),
                    label=f"扫描分块 {number}",
                    **retry_options,
                )
            candidates = _core_only(parse_candidates(response["data"], window), window)
            if scope:
                scope.runtime.event(f"scan-window/{number}", f"校验扫描分块 {number}", error=None)
            return {
                "candidates": [item.__dict__ for item in candidates],
                "usage": response["usage"],
                "state": "succeeded",
                "attempt_errors": errors,
            }
        except (ValueError, KeyError, TypeError) as error:
            errors.append(f"{type(error).__name__}: {error}")
            if scope:
                scope.runtime.event(
                    f"scan-window/{number}", f"校验扫描分块 {number}", attempt_errors=list(errors), error=errors[-1]
                )
            if attempt + 1 == MAX_SCAN_ATTEMPTS:
                raise ValueError(f"分块 {number} 校验失败：" + "；".join(errors)) from error
    raise AssertionError("MAX_SCAN_ATTEMPTS must be positive")


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
