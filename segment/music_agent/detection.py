"""Long-range music scanning and conservative vocal boundary refinement."""

from __future__ import annotations

import logging
import math
import tempfile
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import asdict, dataclass
from functools import partial
from pathlib import Path
from typing import Any

from segment.music_agent.boundary_review import GROUPING_PROMPT, BoundaryOptions, review_boundaries
from segment.music_agent.media import extract_wav, make_windows, media_duration
from segment.music_agent.models import audio_model_call, call_with_storage
from segment.music_agent.prompts import BOUNDARY_PROMPT, SCAN_PROMPT
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
    run_id: str


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
    windows = make_windows(media_duration(media), chunk_seconds, chunk_context)
    context = ScanContext(media, client, storage, s3_prefix, model, uuid.uuid4().hex)
    worker = partial(_scan_window, context)
    results: dict[int, tuple[list[Candidate], dict]] = {}
    with ThreadPoolExecutor(max_workers=scan_concurrency) as executor:
        # Submit lazily: after a failure no further chunk is extracted, uploaded or sent to the model.
        slots: list = []
        submitted: dict[object, int] = {}
        queued = iter(enumerate(windows, 1))
        while len(slots) < scan_concurrency:
            item = next(queued, None)
            if item is None:
                break
            future = executor.submit(worker, item)
            slots.append(future)
            submitted[future] = item[0]
        while slots:
            done, _ = wait(slots, return_when=FIRST_COMPLETED)
            for future in done:
                slots.remove(future)
                if future.exception() is not None:
                    for other in slots:
                        other.cancel()
                    raise future.exception()
                results[submitted[future]] = future.result()
                item = next(queued, None)
                if item is not None:
                    future = executor.submit(worker, item)
                    slots.append(future)
                    submitted[future] = item[0]
    ordered = [results[index] for index in sorted(results)]
    candidates = [candidate for current, _ in ordered for candidate in current]
    metadata = [record for _, record in ordered]
    return _reindex(merge_candidates(candidates, max_gap=BORDER_DUPLICATE_SECONDS)), metadata


def _scan_window(context: ScanContext, item: tuple) -> tuple[list[Candidate], dict]:
    chunk_index, (core_start, core_end, audio_start, audio_end) = item
    with tempfile.TemporaryDirectory(prefix="music-scan-") as directory:
        wav = Path(directory) / "chunk.wav"
        # Upload only the core range: the surrounding context of every chunk was already another chunk's core.
        extract_wav(context.media, core_start, core_end, wav)
        key = "/".join(filter(None, (context.prefix, context.run_id, f"scan-{chunk_index:04d}.wav")))
        context.storage.upload(key, wav)
        try:
            audio_url = context.storage.signed_url(key)
            response = audio_model_call(context.client, context.model, SCAN_PROMPT, audio_url)
            found = parse_candidates(response["data"], core_start)
            current = [candidate for candidate in found if candidate.start < core_end]
            LOGGER.info(
                "Scanned chunk %d: input %.0f-%.0fs, %d candidates",
                chunk_index,
                core_start,
                core_end,
                len(current),
            )
            record = {
                "chunk": chunk_index,
                "core_start": core_start,
                "core_end": core_end,
                "candidate_count": len(current),
                "usage": response["usage"],
            }
            return current, record
        finally:
            context.storage.delete(key)


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
    duration = media_duration(media)
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
