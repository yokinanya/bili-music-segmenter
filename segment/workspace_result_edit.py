"""Validated result revisions, exported without overwriting an existing clip."""

from __future__ import annotations

import json
import math
from pathlib import Path
from uuid import uuid4

from segment.music_agent.manifest import atomic_write_json
from segment.workspace_records import ACTIVE_STATES
from segment.workspace_results import contained_path, manifest_paths, read_clips

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


def validate_edit(payload: dict, clip: dict, duration: float) -> dict:
    if not payload or payload.keys() - EDIT_FIELDS:
        raise ValueError("编辑必须包含 title、artist、start_seconds 或 end_seconds，且不能包含未知字段")
    values = {field: payload.get(field, clip[field]) for field in EDIT_FIELDS}
    for field in ("title", "artist"):
        if not isinstance(values[field], str) or "\x00" in values[field]:
            raise ValueError(f"{field} 必须是无空字符的文本")
    for field in ("start_seconds", "end_seconds"):
        if type(values[field]) not in (int, float) or not math.isfinite(values[field]):
            raise ValueError(f"{field} 必须是有限数字")
    if not math.isfinite(duration) or not 0 <= values["start_seconds"] < values["end_seconds"] <= duration:
        raise ValueError(f"时间范围必须满足 0 ≤ start_seconds < end_seconds ≤ 源时长 {duration}")
    return values


def edit_result(job: dict, request: dict, services: dict) -> dict:
    if job["state"] in ACTIVE_STATES:
        raise ValueError("任务运行中不能编辑结果")
    item, manifest, document, interval, clip = locate_clip(job, request["clip_id"])
    source = contained_path(Path(item["source_path"]), services["source_root"])
    if not source.is_file():
        raise FileNotFoundError("保留的源文件已缺失，不能重新导出")
    values = validate_edit(request["payload"], clip, services["duration"](source))
    destination = contained_path(Path(item["outdir"]) / f"revision_{uuid4().hex}.mp4", Path(item["outdir"]))
    original = json.loads(json.dumps(document))
    try:
        services["export"](source, values["start_seconds"], values["end_seconds"], destination)
        if not destination.is_file() or not destination.stat().st_size:
            raise RuntimeError("重新导出没有生成有效视频")
        interval.update(
            {
                **values,
                "file": str(destination),
                "clip_id": clip["id"],
                "original_start_seconds": clip["original_start_seconds"],
                "original_end_seconds": clip["original_end_seconds"],
            }
        )
        atomic_write_json(manifest, document)
        updated = {**job, "clips": [value for entry in job["batch"] for value in read_clips(entry)]}
        services["save"](updated)
    except Exception:
        if document != original:
            atomic_write_json(manifest, original)
        destination.unlink(missing_ok=True)
        raise
    return next(value for value in updated["clips"] if value["id"] == clip["id"])
