"""Stable result IDs, persisted history summaries and disk-backed ZIP archives."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


def read_clips(item: dict) -> list[dict]:
    clips = []
    for manifest in manifest_paths(item):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for record in data["candidates"]:
            for interval in record.get("singing_intervals", []):
                if "file" in interval:
                    clips.append(_clip(item, interval, data))
    return clips


def manifest_paths(item: dict) -> list[Path]:
    return [
        contained_path(path, Path(item["outdir"])) for path in sorted(Path(item["outdir"]).glob("*_music_agent.json"))
    ]


def contained_path(path: Path, root: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError("结果文件超出任务目录")
    return resolved


def _clip(item: dict, interval: dict, manifest: dict) -> dict:
    path = contained_path(Path(interval["file"]), Path(item["outdir"]))
    return {
        "id": interval.get("clip_id", hashlib.sha256(str(path).encode()).hexdigest()),
        "media_id": item["id"],
        "name": path.name,
        "path": str(path),
        "title": interval.get("title", ""),
        "artist": interval.get("artist", ""),
        "source_name": item["media"],
        "start_seconds": interval["start_seconds"],
        "end_seconds": interval["end_seconds"],
        "original_start_seconds": interval.get("original_start_seconds", interval["start_seconds"]),
        "original_end_seconds": interval.get("original_end_seconds", interval["end_seconds"]),
        "source_duration_seconds": manifest.get("duration_seconds"),
        "recognition": interval.get("recognition", {}),
        "title_resolution": interval.get("title_resolution", {}),
        "duration_seconds": round(interval["end_seconds"] - interval["start_seconds"], 3),
    }


def history_entry(job: dict) -> dict:
    return {
        "id": job["id"],
        "state": job["state"],
        "started_at": job["started_at"],
        "finished_at": job["finished_at"],
        "medias": [item["media"] for item in job["batch"]],
        "clip_count": len(job.get("clips", [])),
        "usage": job["usage"],
        "attempt": job["attempt"],
        "upload_ids": job["upload_ids"],
        "options": job["options"],
        "legacy": False,
    }


def make_archive(job: dict, root: Path) -> Path:
    if job["state"] in {"running", "queued"}:
        raise ValueError("任务结束后才能下载整批结果")
    destination = root / "results.zip"
    temporary = destination.with_suffix(".zip.part")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED) as archive:
        for item in job["batch"]:
            _archive_item(archive, item)
    temporary.replace(destination)
    return destination


def _archive_item(archive, item: dict) -> None:
    prefix = item["id"] + "/"
    for manifest in manifest_paths(item):
        archive.write(manifest, prefix + manifest.name)
    for clip in read_clips(item):
        archive.write(clip["path"], prefix + clip["id"][:12] + "_" + clip["name"])
