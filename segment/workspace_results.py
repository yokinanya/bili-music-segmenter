"""Stable result IDs, persisted history summaries and disk-backed ZIP archives."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path


def read_clips(item: dict) -> list[dict]:
    clips = []
    for manifest in Path(item["outdir"]).glob("*_music_agent.json"):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for record in data["candidates"]:
            for interval in record.get("singing_intervals", []):
                if "file" in interval:
                    clips.append(_clip(item, interval))
    return clips


def _clip(item: dict, interval: dict) -> dict:
    path = Path(interval["file"]).resolve()
    if not path.is_relative_to(Path(item["outdir"]).resolve()):
        raise ValueError("结果文件超出任务目录")
    return {
        "id": hashlib.sha256(str(path).encode()).hexdigest(),
        "media_id": item["id"],
        "name": path.name,
        "path": str(path),
        "title": interval.get("title", ""),
        "artist": interval.get("artist", ""),
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
    for manifest in Path(item["outdir"]).glob("*_music_agent.json"):
        archive.write(manifest, prefix + manifest.name)
    for clip in read_clips(item):
        archive.write(clip["path"], prefix + clip["id"][:12] + "_" + clip["name"])
