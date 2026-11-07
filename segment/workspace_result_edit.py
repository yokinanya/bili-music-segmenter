"""Validated result revisions, exported without overwriting an existing clip."""

from __future__ import annotations

import json
import math
from pathlib import Path
from uuid import uuid4

from segment.music_agent.export import safe_component
from segment.music_agent.manifest import atomic_write_json
from segment.music_agent.media_process import reporting_media
from segment.workspace_records import ACTIVE_STATES
from segment.workspace_results import contained_path, manifest_paths, read_clips

DOWNLOAD_NAME_BYTES = 120
EDIT_FIELDS = frozenset({"title", "artist", "start_seconds", "end_seconds"})


def manifest_path(job: dict, media_id: str) -> Path:
    item = next((value for value in job["batch"] if value["id"] == media_id), None)
    if item is None:
        raise KeyError(media_id)
    paths = manifest_paths(item)
    if not paths:
        raise FileNotFoundError("该文件尚无结果清单")
    if len(paths) != 1:
        raise ValueError("该文件存在多个结果清单，无法确定编辑目标")
    return paths[0]


def locate_clip(job: dict, identity: str) -> tuple:
    for item in job["batch"]:
        clips = read_clips(item)
        match = next((clip for clip in clips if clip["id"] == identity), None)
        if match is None:
            continue
        path = manifest_path(job, item["id"])
        document = json.loads(path.read_text(encoding="utf-8"))
        interval = _find_interval(document, match)
        return item, path, document, interval, match
    raise KeyError(identity)


def _find_interval(document: dict, clip: dict) -> dict:
    intervals = (
        interval
        for candidate in document["candidates"]
        for interval in candidate.get("singing_intervals", [])
        if "file" in interval
    )
    return next(interval for interval in intervals if Path(interval["file"]).resolve() == Path(clip["path"]))


def _edit_values(payload: dict, clip: dict) -> dict:
    if not payload or payload.keys() - EDIT_FIELDS:
        raise ValueError("编辑必须包含 title、artist、start_seconds 或 end_seconds，且不能包含未知字段")
    values = {field: payload.get(field, clip[field]) for field in EDIT_FIELDS}
    for field in ("title", "artist"):
        if not isinstance(values[field], str) or "\x00" in values[field]:
            raise ValueError(f"{field} 必须是无空字符的文本")
    for field in ("start_seconds", "end_seconds"):
        if type(values[field]) not in (int, float) or not math.isfinite(values[field]):
            raise ValueError(f"{field} 必须是有限数字")
    if not 0 <= values["start_seconds"] < values["end_seconds"]:
        raise ValueError("时间范围必须满足 0 ≤ start_seconds < end_seconds")
    return values


def validate_edit(payload: dict, clip: dict, duration: float) -> dict:
    values = _edit_values(payload, clip)
    if not math.isfinite(duration) or values["end_seconds"] > duration:
        raise ValueError(f"时间范围必须满足 0 ≤ start_seconds < end_seconds ≤ 源时长 {duration}")
    return values


def edit_result(job: dict, request: dict, services: dict) -> dict:
    if job["state"] in ACTIVE_STATES:
        raise ValueError("任务运行中不能编辑结果")
    item, manifest, document, interval, clip = locate_clip(job, request["clip_id"])
    values = _edit_values(request["payload"], clip)
    if all(values[field] == clip[field] for field in EDIT_FIELDS):
        return clip
    plan = {
        "job": job,
        "item": item,
        "manifest": manifest,
        "document": document,
        "interval": interval,
        "clip": clip,
        "values": values,
    }
    destination = None
    try:
        if any(values[field] != clip[field] for field in ("start_seconds", "end_seconds")):
            destination = _export_revision(plan, services)
        duration = values["end_seconds"] - values["start_seconds"] if destination is not None else None
        _report(
            services,
            {
                "stage": "saving",
                "completed_seconds": duration or 0,
                "total_seconds": duration,
            },
        )
        return _save_revision(plan, destination, services)
    except Exception:
        if destination is not None:
            destination.unlink(missing_ok=True)
        raise


def _export_revision(plan: dict, services: dict) -> Path:
    item, values = plan["item"], plan["values"]
    source = contained_path(Path(item["source_path"]), services["source_root"])
    if not source.is_file():
        raise FileNotFoundError("保留的源文件已缺失，不能重新导出")
    validate_edit(values, plan["clip"], services["duration"](source))
    destination = contained_path(Path(item["outdir"]) / f"revision_{uuid4().hex}.mp4", Path(item["outdir"]))
    try:
        with reporting_media(lambda value: _report(services, value)):
            services["export"](source, values["start_seconds"], values["end_seconds"], destination)
        if not destination.is_file() or not destination.stat().st_size:
            raise RuntimeError("重新导出没有生成有效视频")
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return destination


def _save_revision(plan: dict, destination: Path | None, services: dict) -> dict:
    clip, values = plan["clip"], plan["values"]
    title = safe_component(values["title"], "未识别歌名")
    name = title.encode("utf-8")[:DOWNLOAD_NAME_BYTES].decode("utf-8", errors="ignore") + ".mp4"
    revised = {
        **plan["interval"],
        **values,
        "download_name": name,
        "duration_seconds": round(values["end_seconds"] - values["start_seconds"], 3),
        "clip_id": clip["id"],
        "original_start_seconds": clip["original_start_seconds"],
        "original_end_seconds": clip["original_end_seconds"],
    }
    if destination is not None:
        revised = {**revised, "file": str(destination)}
    document = {
        **plan["document"],
        "candidates": [
            {
                **candidate,
                "singing_intervals": [
                    revised if interval is plan["interval"] else interval
                    for interval in candidate.get("singing_intervals", [])
                ],
            }
            for candidate in plan["document"]["candidates"]
        ],
    }
    try:
        atomic_write_json(plan["manifest"], document)
        updated = {**plan["job"], "clips": [value for item in plan["job"]["batch"] for value in read_clips(item)]}
        services["save"](updated)
    except Exception:
        atomic_write_json(plan["manifest"], plan["document"])
        raise
    return next(value for value in updated["clips"] if value["id"] == clip["id"])


def _report(services: dict, event: dict) -> None:
    if services.get("progress"):
        services["progress"](event)
