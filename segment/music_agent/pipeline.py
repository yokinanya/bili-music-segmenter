"""One dependency-aware video pipeline with ordered, atomic result commits."""

from __future__ import annotations

import asyncio
import math
from dataclasses import asdict
from pathlib import Path

from segment.music_agent.clip_tails import extend_clip_tails
from segment.music_agent.export_inventory import initialize_inventory, remove_superseded_exports
from segment.music_agent.manifest import write_manifest
from segment.music_agent.pipeline_candidates import prepare_candidate, recognize_interval
from segment.music_agent.pipeline_context import PipelineContext
from segment.music_agent.runtime import fingerprint
from segment.music_agent.scan_gemini import Candidate
from segment.workspace_uploads import now

CANDIDATE_CONCURRENCY = 3


async def execute_pipeline(context: PipelineContext) -> Path:
    runtime = context.runtime
    initialize_inventory(context.output)
    duration = await asyncio.to_thread(
        runtime.run, context.spec("probe", "媒体分析", {}), lambda: context.services.calls["duration"](context.media)
    )
    runtime.config["duration"] = duration
    runtime.config["scan_total"] = math.ceil(duration / context.options["chunk_seconds"])
    with runtime.activate():
        candidates, chunks = await _scan(context)
        runtime.config["candidate_total"] = len(candidates)
        records: dict[int, dict] = {}
        counters = (("prepare", "候选处理"), ("finalize", "切分与导出"))
        for identity, label in counters:
            runtime.event(
                identity,
                label,
                total=len(candidates),
                unit="项",
                state="running" if candidates else "skipped",
                finished_at=None if candidates else now(),
            )
        manifest = context.output / f"{context.media.stem}_music_agent.json"

        def persist():
            _persist(context, manifest, chunks, list(records.values()))

        persist()
        try:
            async for candidate, result in _parallel(
                candidates, lambda item: prepare_candidate(item, context), context
            ):
                records[candidate.index] = result
                runtime.advance("prepare", "候选处理", len(candidates))
                persist()
        except Exception as error:
            if candidates:
                _finish(runtime, counters[0], failed=error)
            raise
        if candidates:
            _finish(runtime, counters[0])
        ordered = sorted(records.values(), key=lambda item: item["index"])
        try:
            async for finalized in _finalize(ordered, context):
                records = {record["index"]: record for record in finalized}
                persist()
        except Exception as error:
            if candidates:
                _finish(runtime, counters[1], failed=error)
            raise
        if candidates:
            _finish(runtime, counters[1])
        persist()
        remove_superseded_exports(context.output, list(records.values()))
        runtime.event("complete", "结果整理", state="succeeded", completed=1, total=1)
        return manifest


def _finish(runtime, counter: tuple[str, str], failed: Exception | None = None) -> None:
    """计数步骤只靠 advance 累加 completed，必须补终态，否则界面永远显示进行中。"""
    identity, label = counter
    if failed is None:
        runtime.event(identity, label, state="succeeded", finished_at=now())
    else:
        runtime.event(identity, label, state="failed", error=str(failed), finished_at=now())


async def _finalize(ordered: list, context: PipelineContext):
    resolved = await asyncio.to_thread(
        context.runtime.run,
        context.spec("clip-tails", "延长片段结尾", ordered),
        lambda: extend_clip_tails(ordered, context.runtime.config["duration"]),
    )
    records = {record["index"]: record for record in resolved}
    yield list(records.values())
    async for original, result in _parallel(resolved, lambda item: _export_record(item, context), context):
        records = {**records, original["index"]: result}
        context.runtime.advance("finalize", "切分与导出", len(ordered))
        yield list(records.values())


async def _scan(context: PipelineContext) -> tuple[list, list]:
    def scan():
        candidates, chunks = context.services.calls["scan"](
            context.media,
            context.client,
            chunk_seconds=context.options["chunk_seconds"],
            chunk_context=context.options["chunk_context_seconds"],
            minimum_seconds=context.options["minimum_candidate_seconds"],
        )
        return {"candidates": [asdict(candidate) for candidate in candidates], "chunks": chunks}

    spec = {**context.spec("scan", "分块扫描", {}), "total": context.runtime.config["scan_total"]}
    data = await asyncio.to_thread(context.runtime.run, spec, scan)
    return [Candidate(**item) for item in data["candidates"]], data["chunks"]


async def _parallel(items: list, work, context: PipelineContext):
    queued = iter(items)
    active = {}
    for _ in range(CANDIDATE_CONCURRENCY):
        item = next(queued, None)
        if item is not None:
            active[asyncio.create_task(work(item))] = item
    try:
        while active:
            done, _ = await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
            errors = [task.exception() for task in done if task.exception() is not None]
            for task in done:
                item = active.pop(task)
                if task.exception() is None:
                    yield item, task.result()
            if errors:
                await asyncio.gather(*active, return_exceptions=True)
                for task, item in active.items():
                    if task.exception() is None:
                        yield item, task.result()
                active.clear()
                raise errors[0]
            for _ in done:
                item = next(queued, None)
                if item is not None:
                    active[asyncio.create_task(work(item))] = item
    finally:
        if active:
            await asyncio.gather(*active, return_exceptions=True)


async def _export_record(current: dict, context: PipelineContext) -> dict:
    intervals = []
    for interval in current.get("singing_intervals", []):
        prepared = interval
        if "recognition" not in prepared:
            prepared = {**interval, **await recognize_interval(interval, context)}
        exported = await _export(prepared, current["index"], context)
        intervals.append({**prepared, "file": exported})
    return {
        **current,
        "singing_intervals": intervals,
        "decision": "exported" if intervals else current["decision"],
    }


def export_identity(index: int, interval: dict) -> str:
    """只按源视频位置定位片段：标题或识曲结果变化不应产生新的导出文件。"""
    return fingerprint([index, interval["start_seconds"], interval["end_seconds"]])


def export_folder(output: Path, index: int, interval: dict) -> Path:
    return output / "clips" / export_identity(index, interval)


def export_filename(interval: dict) -> str:
    from segment.music_agent.export import safe_component

    title = safe_component(interval.get("title", ""), "未识别歌名")
    return title.encode("utf-8")[:120].decode("utf-8", errors="ignore") + ".mp4"


async def _export(interval: dict, index: int, context: PipelineContext) -> str:
    """同一时间范围只编码一次；标题变化时改名复用，不重新导出。"""
    folder = export_folder(context.output, index, interval)
    destination = folder / export_filename(interval)
    spec = {
        **context.spec("export/" + export_identity(index, interval), "导出片段", interval),
        "validate": lambda path: Path(path).is_file() and Path(path).stat().st_size > 0,
    }

    def export():
        folder.mkdir(parents=True, exist_ok=True)
        if destination.is_file():
            return str(destination)
        previous = next((item for item in folder.glob("*.mp4") if item.name != "segment.part.mp4"), None)
        if previous is not None:
            # 已编码的同范围片段直接改名，避免改名后重新编码。
            previous.replace(destination)
            return str(destination)
        temporary = folder / "segment.part.mp4"
        context.services.calls["export"](context.media, interval["start_seconds"], interval["end_seconds"], temporary)
        temporary.replace(destination)
        return str(destination)

    return await asyncio.to_thread(context.runtime.run, spec, export)


def _persist(context: PipelineContext, path: Path, chunks: list, records: list) -> None:
    ordered = sorted(records, key=lambda item: item["index"])
    count = sum("file" in interval for item in ordered for interval in item.get("singing_intervals", []))
    write_manifest(
        path,
        media=context.media,
        duration=context.runtime.config["duration"],
        models={
            "audio_scan_and_boundary": context.options["audio_model"],
        },
        policy={key: value for key, value in context.options.items() if key != "netease_cookie"},
        chunks=chunks,
        candidate_count=context.runtime.config["candidate_total"],
        candidates=ordered,
        exported_count=count,
    )
