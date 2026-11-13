"""Concurrent candidate preparation with resumable interval-level decisions."""

from __future__ import annotations

import asyncio
from dataclasses import asdict
from pathlib import Path

from segment.music_agent.pipeline_context import PipelineContext
from segment.music_agent.runtime import fingerprint

TITLE_PIPELINE_VERSION = "recognition-only-v1"


async def prepare_candidate(candidate, context: PipelineContext) -> dict:
    spec = context.spec(
        f"candidate/{candidate.index}", f"候选 {candidate.index}", [TITLE_PIPELINE_VERSION, asdict(candidate)]
    )
    return await context.runtime.async_run(spec, lambda: _prepare(candidate, context))


async def _prepare(candidate, context: PipelineContext) -> dict:
    record = {**asdict(candidate), "singing_intervals": []}
    if candidate.classification == "background_music_chat" or not candidate.host_singing_present:
        return {**record, "decision": "background_music_skipped"}
    if candidate.classification == "uncertain" or candidate.confidence < context.options["minimum_confidence"]:
        return {**record, "decision": "uncertain_or_low_confidence_skipped"}
    # 扫描已直接给出完整歌曲边界，不再逐候选精修。
    start, end = candidate.start, candidate.end
    if end - start < context.options["minimum_singing_seconds"]:
        return {**record, "decision": "no_confident_singing"}
    interval = {"start_seconds": start, "end_seconds": end, "duration_seconds": round(end - start, 3)}
    metadata = await recognize_interval(interval, context, candidate)
    return {
        **record,
        "singing_intervals": [{**interval, **metadata}],
        "decision": "prepared",
    }


async def recognize_interval(interval: dict, context: PipelineContext, candidate=None) -> dict:
    spec = context.spec(
        "identify/" + fingerprint(interval),
        "识曲与标题判断",
        [TITLE_PIPELINE_VERSION, interval, asdict(candidate) if candidate else None],
    )
    return await context.runtime.async_run(spec, lambda: _identify(interval, context, candidate))


async def _identify(interval: dict, context: PipelineContext, candidate) -> dict:
    audio = await asyncio.to_thread(_recognition_audio, interval, context)
    recognition = await context.services.recognize(audio, context)
    errors = [value["error"] for value in recognition.values() if value.get("status") == "error"]
    if errors:
        raise RuntimeError("识曲服务请求失败：" + "；".join(errors))
    if candidate:
        recognition = {
            **recognition,
            "title_hint": candidate.title_hint,
            "announcer_hint": candidate.announcer_hint,
            "candidate_rationale": candidate.rationale,
        }
    # 不做模型二次判断：结论只来自识曲本身，冲突时留空交给人工填写。
    title, artist, status = context.services.choose_title(recognition)
    return {
        "recognition": recognition,
        "title": title or "",
        "artist": artist or "",
        "title_resolution": {"status": status},
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
