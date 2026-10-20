"""Long-range music scanning and conservative vocal boundary refinement."""

from __future__ import annotations

import logging
import math
import tempfile
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from segment.music_agent.media import extract_wav, make_windows, media_duration
from segment.music_agent.models import audio_model_call, call_with_oss
from segment.music_agent.prompts import BOUNDARY_PROMPT, SCAN_PROMPT

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


def merge_candidates(candidates: list[Candidate], max_gap: float) -> list[Candidate]:
    ordered = sorted(candidates, key=lambda item: (item.start, item.end))
    merged: list[Candidate] = []
    for candidate in ordered:
        if (
            merged
            and candidate.start < merged[-1].end
            and candidate.classification == merged[-1].classification
            and candidate.title_hint == merged[-1].title_hint
        ):
            previous = merged[-1]
            classes = {previous.classification, candidate.classification}
            merged[-1] = Candidate(
                index=0,
                start=previous.start,
                end=max(previous.end, candidate.end),
                classification=(
                    "mixed_singing_and_chat"
                    if len(classes) > 1 or "mixed_singing_and_chat" in classes
                    else previous.classification
                ),
                confidence=min(previous.confidence, candidate.confidence),
                host_singing_present=(previous.host_singing_present or candidate.host_singing_present),
                title_hint=previous.title_hint or candidate.title_hint,
                rationale=" ".join(filter(None, (previous.rationale, candidate.rationale))),
            )
        else:
            merged.append(candidate)
    return [
        Candidate(index=index, **{key: value for key, value in asdict(item).items() if key != "index"})
        for index, item in enumerate(merged, start=1)
    ]


def scan_candidates(
    media: Path,
    client: Any,
    bucket: Any,
    *,
    chunk_seconds: int,
    chunk_context: int,
    oss_prefix: str,
    model: str,
) -> tuple[list[Candidate], list[dict[str, Any]]]:
    duration = media_duration(media)
    windows = make_windows(duration, chunk_seconds, chunk_context)
    candidates = []
    metadata = []
    run_id = uuid.uuid4().hex
    for chunk_index, (core_start, core_end, audio_start, audio_end) in enumerate(windows, 1):
        with tempfile.TemporaryDirectory(prefix="music-scan-") as directory:
            wav = Path(directory) / "chunk.wav"
            extract_wav(media, audio_start, audio_end, wav)
            key = f"{oss_prefix}/{run_id}/scan-{chunk_index:04d}.wav"
            try:
                bucket.put_object_from_file(key, str(wav))
                audio_url = bucket.sign_url("GET", key, 3600, slash_safe=True)
                prompt = (
                    f"{SCAN_PROMPT}\n核心范围是输入音频 {core_start - audio_start:.2f}-"
                    f"{core_end - audio_start:.2f} 秒；只记录起点在核心范围的音乐候选。"
                )
                response = audio_model_call(client, model, prompt, audio_url)
                found = parse_candidates(response["data"], audio_start)
                current = [item for item in found if core_start <= item.start < core_end]
                candidates.extend(current)
                metadata.append(
                    {
                        "chunk": chunk_index,
                        "core_start": core_start,
                        "core_end": core_end,
                        "candidate_count": len(current),
                        "usage": response["usage"],
                    }
                )
                LOGGER.info("Scanned chunk %d/%d", chunk_index, len(windows))
            finally:
                bucket.delete_object(key)
    return merge_candidates(candidates, max_gap=0), metadata


def refine_candidate(
    media: Path,
    candidate: Candidate,
    client: Any,
    bucket: Any,
    *,
    context_seconds: float,
    oss_prefix: str,
    model: str,
    minimum_confidence: float,
) -> tuple[list[tuple[float, float]], dict[str, Any]]:
    duration = media_duration(media)
    audio_start = max(0.0, candidate.start - context_seconds)
    audio_end = min(duration, candidate.end + context_seconds)
    prompt = (
        f"{BOUNDARY_PROMPT}\n目标候选范围是输入音频 "
        f"{candidate.start - audio_start:.2f}-{candidate.end - audio_start:.2f} 秒。"
    )
    response = call_with_oss(
        media,
        audio_start,
        audio_end,
        client,
        bucket,
        model=model,
        prompt=prompt,
        oss_prefix=oss_prefix,
    )
    data = response["data"]
    confidence = float(data.get("confidence", 0))
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("模型返回了无效置信度")
    if data.get("host_singing_present") is not True or confidence < minimum_confidence:
        return [], {"data": data, "usage": response["usage"]}
    intervals = []
    for item in data.get("intervals", []):
        local_start, local_end = float(item["start_seconds"]), float(item["end_seconds"])
        if (
            not all(math.isfinite(x) for x in (local_start, local_end))
            or not 0 <= local_start < local_end <= audio_end - audio_start
        ):
            raise ValueError("模型演唱边界超出输入音频或时间无效")
        start = audio_start + local_start
        end = audio_start + local_end
        if end > start:
            intervals.append((start, end))
    return intervals, {"data": data, "usage": response["usage"]}


def merge_intervals(intervals: list[tuple[float, float]], max_gap: float) -> list[tuple[float, float]]:
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if merged and start - merged[-1][1] <= max_gap:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(start, end) for start, end in merged]
