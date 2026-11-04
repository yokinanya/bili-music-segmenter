"""Long-range music scanning and conservative vocal boundary refinement."""

from __future__ import annotations

import logging
import math
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Any

from segment.music_agent.boundary_review import GROUPING_PROMPT, BoundaryOptions, review_boundaries
from segment.music_agent.media import make_windows, media_duration
from segment.music_agent.models import call_with_storage
from segment.music_agent.prompts import BOUNDARY_PROMPT, SCAN_PROMPT
from segment.music_agent.runtime import CURRENT
from segment.music_agent.scan_workers import scan_windows
from segment.music_agent.storage import AudioStorage

LOGGER = logging.getLogger(__name__)
VALID_CLASSES = {"host_singing", "background_music_chat", "mixed_singing_and_chat", "uncertain"}


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


def parse_candidates(data: dict[str, Any], absolute_offset: float) -> list[Candidate]:
    segments = data.get("segments")
    if not isinstance(segments, list):
        raise ValueError("模型扫描结果缺少 segments 数组")
    candidates = []
    for item in segments:
        classification = item.get("classification")
        start = absolute_offset + float(item["start_seconds"])
        end = absolute_offset + float(item["end_seconds"])
        confidence = float(item["confidence"])
        if classification not in VALID_CLASSES:
            raise ValueError(f"无效歌曲分类：{classification}")
        if (
            not all(math.isfinite(x) for x in (start, end, confidence))
            or start < absolute_offset
            or end <= start
            or not 0 <= confidence <= 1
        ):
            raise ValueError(f"无效候选时间：{start}-{end}")
        candidates.append(
            Candidate(
                index=0,
                start=start,
                end=end,
                classification=classification,
                confidence=confidence,
                host_singing_present=item.get("host_singing_present") is True,
                title_hint=str(item.get("title_hint", "")),
                rationale=str(item.get("rationale", "")),
            )
        )
    return candidates


# Adjacent chunks can disagree by a few seconds on where a song starts; treat such reports as one song.
OVERLAP_TOLERANCE_SECONDS = 0.5
BORDER_DUPLICATE_SECONDS = 5.0


def merge_candidates(candidates: list[Candidate], max_gap: float = 0) -> list[Candidate]:
    """Merge candidates that overlap, so border disagreements are not reviewed and recognized twice.

    ``max_gap`` additionally merges candidates separated by at most that many seconds.
    """
    ordered = sorted(candidates, key=lambda item: (item.start, item.end))
    merged: list[Candidate] = []
    for candidate in ordered:
        near = merged and candidate.start < merged[-1].end + max(OVERLAP_TOLERANCE_SECONDS, max_gap)
        if near and _same_song(merged[-1], candidate):
            previous = merged[-1]
            classes = {previous.classification, candidate.classification}
            merged[-1] = Candidate(
                index=0,
                start=previous.start,
                end=max(previous.end, candidate.end),
                classification="mixed_singing_and_chat" if len(classes) > 1 else previous.classification,
                confidence=min(previous.confidence, candidate.confidence),
                host_singing_present=(previous.host_singing_present or candidate.host_singing_present),
                title_hint=previous.title_hint or candidate.title_hint,
                rationale=" ".join(filter(None, (previous.rationale, candidate.rationale))),
            )
        else:
            merged.append(candidate)
    return _reindex(merged)


def _same_song(first: Candidate, second: Candidate) -> bool:
    """Only merge when the reports can be the same song; different titles always stay separate songs."""
    if first.title_hint and second.title_hint:
        return first.title_hint == second.title_hint
    return first.classification == second.classification


def _reindex(candidates: list[Candidate]) -> list[Candidate]:
    return [
        Candidate(index=index, **{key: value for key, value in asdict(item).items() if key != "index"})
        for index, item in enumerate(candidates, start=1)
    ]


@dataclass(frozen=True)
class ScanContext:
    media: Path
    client: Any
    storage: AudioStorage
    prefix: str
    model: str


def scan_candidates(
    media: Path,
    client: Any,
    storage: AudioStorage,
    *,
    chunk_seconds: int,
    chunk_context: int,
    s3_prefix: str,
    model: str,
    scan_concurrency: int = 3,
) -> tuple[list[Candidate], list[dict[str, Any]]]:
    if scan_concurrency <= 0:
        raise ValueError("扫描并发数必须为正整数")
    scope = CURRENT.get()
    duration = scope.runtime.config["duration"] if scope else media_duration(media)
    windows = make_windows(duration, chunk_seconds, chunk_context)
    context = ScanContext(media, client, storage, s3_prefix, model)
    worker = partial(_scan_window, context)
    ordered = scan_windows(windows, worker, scan_concurrency)
    candidates = [candidate for current, _ in ordered for candidate in current]
    metadata = [record for _, record in ordered]
    return _reindex(merge_candidates(candidates, max_gap=BORDER_DUPLICATE_SECONDS)), metadata


def _scan_window(context: ScanContext, item: tuple) -> tuple[list[Candidate], dict]:
    index, window = item
    scope = CURRENT.get()
    if scope:
        spec = {"id": f"scan/{index}", "label": f"扫描分块 {index}", "input": [window, context.model, SCAN_PROMPT]}
        result = scope.runtime.run(spec, lambda: _scan_chunk(context, item))
        scope.runtime.advance("scan", "分块扫描", scope.runtime.config["scan_total"])
    else:
        result = _scan_chunk(context, item)
    return [Candidate(**value) for value in result["candidates"]], result["metadata"]


def _scan_chunk(context: ScanContext, item: tuple) -> dict:
    index, (core_start, core_end, audio_start, audio_end) = item
    response = call_with_storage(
        context.media,
        audio_start,
        audio_end,
        context.client,
        context.storage,
        model=context.model,
        prompt=SCAN_PROMPT,
        s3_prefix=context.prefix,
    )
    current = [
        candidate
        for candidate in parse_candidates(response["data"], audio_start)
        if candidate.end > core_start and candidate.start < core_end
    ]
    if any(candidate.end > audio_end for candidate in current):
        raise ValueError("扫描候选超出输入音频范围")
    return {
        "candidates": [asdict(candidate) for candidate in current],
        "metadata": {
            "chunk": index,
            "core_start": core_start,
            "core_end": core_end,
            "audio_start": audio_start,
            "audio_end": audio_end,
            "candidate_count": len(current),
            "usage": response["usage"],
        },
    }


def refine_candidate(
    media: Path,
    candidate: Candidate,
    client: Any,
    storage: AudioStorage,
    *,
    context_seconds: float,
    s3_prefix: str,
    model: str,
    minimum_confidence: float,
    review_instruction: str = "",
) -> tuple[list[tuple[float, float]], dict[str, Any]]:
    scope = CURRENT.get()
    duration = scope.runtime.config["duration"] if scope else media_duration(media)
    options = BoundaryOptions(candidate.start, candidate.end, duration, context_seconds, minimum_confidence)

    def request(audio_start: float, audio_end: float) -> dict:
        prompt = (
            f"{BOUNDARY_PROMPT}{GROUPING_PROMPT}\n目标候选范围是输入音频 "
            f"{candidate.start - audio_start:.2f}-{candidate.end - audio_start:.2f} 秒。"
        )
        if review_instruction:
            prompt += f"\n待核实疑点（仅为线索）：{review_instruction}"
        return call_with_storage(
            media,
            audio_start,
            audio_end,
            client,
            storage,
            model=model,
            prompt=prompt,
            s3_prefix=s3_prefix,
        )

    return review_boundaries(options, request)
