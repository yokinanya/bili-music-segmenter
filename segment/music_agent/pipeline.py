"""One dependency-aware video pipeline with ordered, atomic result commits."""

from __future__ import annotations

import asyncio
import math
from dataclasses import asdict
from pathlib import Path

from segment.music_agent.clip_tails import extend_clip_tails
from segment.music_agent.detection import Candidate
from segment.music_agent.export_inventory import initialize_inventory, remove_superseded_exports
from segment.music_agent.final_review import apply_recheck, request_audit
from segment.music_agent.manifest import write_manifest
from segment.music_agent.overlap_review import reconcile_overlaps
from segment.music_agent.pipeline_candidates import prepare_candidate, recognize_interval
from segment.music_agent.pipeline_context import PipelineContext
from segment.music_agent.runtime import fingerprint


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
        for identity, label in (("prepare", "候选处理"), ("finalize", "最终复核与导出")):
            runtime.event(
                identity, label, total=len(candidates), unit="项", state="running" if candidates else "skipped"
            )
        summary = None
        manifest = context.output / f"{context.media.stem}_music_agent.json"

        def persist():
            _persist(context, manifest, chunks, list(records.values()), summary)

        persist()
        async for candidate, result in _parallel(candidates, lambda item: prepare_candidate(item, context), context):
            records[candidate.index] = result
            runtime.advance("prepare", "候选处理", len(candidates))
            persist()
        ordered = sorted(records.values(), key=lambda item: item["index"])
        spec = context.spec("audit", "全场审核", ordered)
        summary, requests = await asyncio.to_thread(
            runtime.run,
            spec,
            lambda: request_audit(ordered, context.services.review_context(context), context.services.calls["text"]),
        )
        async for finalized in _finalize(ordered, requests, context):
            records = {record["index"]: record for record in finalized}
            persist()
        persist()
        remove_superseded_exports(context.output, list(records.values()))
        runtime.event("complete", "结果整理", state="succeeded", completed=1, total=1)
        return manifest


async def _finalize(ordered: list, requests: list, context: PipelineContext):
    records = {record["index"]: record for record in ordered}
    by_index = {item["candidate_index"]: item for item in requests}
    async for original, result in _parallel(
        ordered, lambda item: _finish_record(item, by_index.get(item["index"]), context), context
    ):
        records = {**records, original["index"]: result}
        yield list(records.values())
    reviewed = sorted(records.values(), key=lambda item: item["index"])
    resolved = await asyncio.to_thread(
        context.runtime.run,
        context.spec("overlap-review", "跨候选联合复核", reviewed),
        lambda: reconcile_overlaps(reviewed, context),
    )
    resolved = extend_clip_tails(resolved, context.runtime.config["duration"])
    records = {record["index"]: record for record in resolved}
    yield list(records.values())
    async for original, result in _parallel(resolved, lambda item: _export_record(item, context), context):
        records = {**records, original["index"]: result}
        context.runtime.advance("finalize", "最终复核与导出", len(ordered))
        yield list(records.values())


async def _scan(context: PipelineContext) -> tuple[list, list]:
    def scan():
        candidates, chunks = context.services.calls["scan"](
            context.media,
            context.client,
            context.storage,
            chunk_seconds=context.options["chunk_seconds"],
            scan_concurrency=context.options["scan_concurrency"],
            chunk_context=context.options["chunk_context_seconds"],
            s3_prefix=context.prefix,
            model=context.options["audio_model"],
        )
        return {"candidates": [asdict(candidate) for candidate in candidates], "chunks": chunks}

    spec = {**context.spec("scan", "分块扫描", {}), "total": context.runtime.config["scan_total"]}
    data = await asyncio.to_thread(context.runtime.run, spec, scan)
    return [
        Candidate(**item)
        for item in data["candidates"]
        if item["end"] - item["start"] >= context.options["minimum_candidate_seconds"]
    ], data["chunks"]


async def _parallel(items: list, work, context: PipelineContext):
    queued = iter(items)
    active = {}
    for _ in range(context.options["candidate_concurrency"]):
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


async def _finish_record(record: dict, request: dict | None, context: PipelineContext) -> dict:
    current = record
    if request:
        spec = context.spec(f"recheck/{record['index']}", "追加音频复核", [record, request])
        current = await asyncio.to_thread(
            context.runtime.run,
            spec,
            lambda: apply_recheck(
                record,
                request,
                context=context.services.review_context(context),
                refine=context.services.calls["refine"],
            ),
        )
    return current


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


async def _export(interval: dict, index: int, context: PipelineContext) -> str:
    identity = fingerprint([index, interval])
    spec = {
        **context.spec("export/" + identity, "导出片段", interval),
        "validate": lambda path: Path(path).is_file() and Path(path).stat().st_size > 0,
    }

    def export():
        folder = context.output / "clips" / identity
        folder.mkdir(parents=True, exist_ok=True)
        from segment.music_agent.export import safe_component

        title = safe_component(interval.get("title", ""), "未识别歌名")
        destination = folder / (title.encode("utf-8")[:120].decode("utf-8", errors="ignore") + ".mp4")
        temporary = folder / "segment.part.mp4"
        context.services.calls["export"](context.media, interval["start_seconds"], interval["end_seconds"], temporary)
        temporary.replace(destination)
        return str(destination)

    return await asyncio.to_thread(context.runtime.run, spec, export)


def _persist(context: PipelineContext, path: Path, chunks: list, records: list, summary) -> None:
    ordered = sorted(records, key=lambda item: item["index"])
    count = sum("file" in interval for item in ordered for interval in item.get("singing_intervals", []))
    write_manifest(
        path,
        media=context.media,
        duration=context.runtime.config["duration"],
        models={
            "audio_scan_and_boundary": context.options["audio_model"],
            "title_resolution": context.options["title_model"] if context.options["use_title_model"] else None,
            "final_summary": context.options["summary_model"],
        },
        policy={key: value for key, value in context.options.items() if key != "netease_cookie"},
        chunks=chunks,
        candidate_count=context.runtime.config["candidate_total"],
        candidates=ordered,
        exported_count=count,
        final_summary=summary,
    )
