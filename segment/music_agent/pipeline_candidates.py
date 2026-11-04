"""Concurrent candidate preparation with resumable interval-level decisions."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path

from segment.music_agent.pipeline_context import PipelineContext
from segment.music_agent.runtime import fingerprint


async def prepare_candidate(candidate, context: PipelineContext) -> dict:
    spec = context.spec(f"candidate/{candidate.index}", f"候选 {candidate.index}", asdict(candidate))
    return await context.runtime.async_run(spec, lambda: _prepare(candidate, context))


async def _prepare(candidate, context: PipelineContext) -> dict:
    record = {**asdict(candidate), "singing_intervals": []}
    if candidate.classification == "background_music_chat" or not candidate.host_singing_present:
        return {**record, "decision": "background_music_skipped"}
    if candidate.classification == "uncertain" or candidate.confidence < context.options["minimum_confidence"]:
        return {**record, "decision": "uncertain_or_low_confidence_skipped"}
    spec = context.spec(f"boundary/{candidate.index}", "边界复核", asdict(candidate))
    intervals, boundary = await asyncio.to_thread(
        context.runtime.run, spec, lambda: context.services.refine(candidate, context)
    )
    prepared = []
    for start, end in intervals:
        if end - start < context.options["minimum_singing_seconds"]:
            continue
        interval = {"start_seconds": start, "end_seconds": end, "duration_seconds": round(end - start, 3)}
        metadata = await recognize_interval(interval, context, candidate)
        prepared.append({**interval, **metadata})
    return {
        **record,
        "boundary_review": boundary,
        "singing_intervals": prepared,
        "decision": "prepared" if prepared else "no_confident_singing",
    }


async def recognize_interval(interval: dict, context: PipelineContext, candidate=None) -> dict:
    spec = context.spec(
        "identify/" + fingerprint(interval), "识曲与标题判断", [interval, asdict(candidate) if candidate else None]
    )
    return await context.runtime.async_run(spec, lambda: _identify(interval, context, candidate))


async def _identify(interval: dict, context: PipelineContext, candidate) -> dict:
    audio = await asyncio.to_thread(_recognition_audio, interval, context)
    recognition = await context.services.recognize(audio, context)
    errors = [value["error"] for value in recognition.values() if value.get("status") == "error"]
    if errors:
        raise RuntimeError("识曲服务请求失败：" + "；".join(errors))
    if candidate:
        recognition = {**recognition, "title_hint": candidate.title_hint, "candidate_rationale": candidate.rationale}
    title, artist, status = context.services.choose_title(recognition)
    text_review = None
    if status == "conflict" and context.options["use_title_model"]:
        text_spec = context.spec("text-title/" + fingerprint(interval), "标题冲突复核", recognition)
        result = await asyncio.to_thread(context.runtime.run, text_spec, lambda: _text_title(recognition, context))
        text_review, (title, artist, status) = result
    audio_review = None
    if context.services.needs_audio(recognition, status):
        spec = context.spec("audio-title/" + fingerprint(interval), "音频标题复核", recognition)
        result = await asyncio.to_thread(
            context.runtime.run, spec, lambda: context.services.audio_title(interval, recognition, context)
        )
        title, artist, status = result["title"], result["artist"], result["status"]
        audio_review = result["audio_review"]
    return {
        "recognition": recognition,
        "title": title or "",
        "artist": artist or "",
        "title_resolution": {"status": status, "text": text_review, "audio": audio_review},
    }


def _recognition_audio(interval: dict, context: PipelineContext) -> Path:
    payload = {
        "start": interval["start_seconds"],
        "end": interval["end_seconds"],
        "suffix": ".mp3",
        "format": "mp3-128k-44100-mono",
    }

    def extract(destination):
        context.services.extract_reference(context.media, payload["start"], payload["end"], destination)

    spec = {
        **context.spec("reference/" + fingerprint(interval), "提取识曲音频", interval),
        "validate": lambda value: Path(value).is_file(),
    }
    return Path(context.runtime.run(spec, lambda: str(context.runtime.local_cache.acquire(payload, extract))))


def _text_title(recognition: dict, context: PipelineContext) -> list:
    response = context.services.text_title(recognition, context)
    return [response, context.services.resolve_text(recognition, response["data"])]
