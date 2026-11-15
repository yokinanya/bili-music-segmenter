"""Project analysis and revision-specific export resources."""

import json
import zipfile
from pathlib import Path
from uuid import uuid4

from segment.music_agent.export import safe_component
from segment.workspace_options import validate_options
from segment.workspace_records import new_job
from segment.workspace_results import contained_path, manifest_paths


def start_analysis(handler, project: dict) -> None:
    payload = handler._payload()
    if payload.keys() - {"options", "refresh"}:
        raise ValueError("Unknown analysis fields")
    refresh = payload.get("refresh", False)
    if not isinstance(refresh, bool):
        raise ValueError("refresh must be a boolean")
    jobs = handler.jobs
    options = validate_options(payload.get("options", {}), jobs.defaults)
    source = jobs._ready(project["upload_id"])
    job = {
        **new_job([source], options, uuid4().hex, jobs.root),
        "analysis_only": True,
        "project_id": project["id"],
        "refresh_recognition": refresh,
    }
    jobs.store.put("jobs", job)
    jobs.execution.schedule(job["id"])
    handler._json(201, {"id": job["id"]})


def analysis_results(handler, project: dict, identity: str) -> None:
    job = handler.jobs.store.get("jobs", identity)
    if job.get("project_id") != project["id"]:
        raise ValueError("Analysis belongs to another project")
    clips = []
    for item in job["batch"]:
        for path in manifest_paths(item):
            document = json.loads(path.read_text(encoding="utf-8"))
            for candidate in document["candidates"]:
                for interval in candidate.get("singing_intervals", []):
                    title = interval.get("title", "")
                    clips.append(
                        {
                            "id": uuid4().hex,
                            "start_seconds": interval["start_seconds"],
                            "end_seconds": interval["end_seconds"],
                            "title": title,
                            "artist": interval.get("artist", ""),
                            "name": safe_component(title, "song") + ".mp4",
                            "recognition": interval.get("recognition", {}),
                            "title_resolution": interval.get("title_resolution", {}),
                        }
                    )
    handler._json(200, {"clips": clips, "state": job["state"], "error": job.get("error")})


def export_resource(handler, project: dict, method: str, action: str) -> None:
    parts = action.split("/")
    if len(parts) == 1 and method == "GET":
        tasks = [task for task in handler.jobs.store.list("editor_exports") if task["project_id"] == project["id"]]
        handler._json(200, {"tasks": tasks})
        return
    if len(parts) == 1 and method == "POST":
        payload = handler._payload()
        if (
            payload.keys() - {"revision", "clip_ids", "filename_suffix"}
            or not {"revision", "clip_ids"} <= payload.keys()
            or payload["revision"] != project["revision"]
        ):
            raise ValueError("Export revision conflict: save the current draft first")
        handler._json(
            201,
            handler.jobs.editor_exports.start(
                project, payload["clip_ids"], filename_suffix=payload.get("filename_suffix", "")
            ),
        )
        return
    if len(parts) < 2:
        raise ValueError("Missing export ID")
    task = handler.jobs.store.get("editor_exports", parts[1])
    if task["project_id"] != project["id"]:
        raise ValueError("Export belongs to another project")
    if len(parts) == 2 and method == "GET":
        handler._json(200, task)
    elif len(parts) == 3 and parts[2] == "cancel" and method == "POST":
        handler._json(200, handler.jobs.editor_exports.cancel(task["id"]))
    elif method == "GET":
        _download(handler, task, parts)
    else:
        raise ValueError("Unknown export resource")


def _download(handler, task: dict, parts: list[str]) -> None:
    root = handler.jobs.root / "editor-exports" / task["id"]
    if len(parts) == 4 and parts[2] == "clip":
        clip = next((clip for clip in task["clips"] if clip["id"] == parts[3]), None)
        if clip is None or "path" not in clip:
            raise FileNotFoundError("Clip has not been exported")
        handler._serve_file(contained_path(Path(clip["path"]), root), downloadable=True, filename=clip["name"])
    elif len(parts) == 3 and parts[2] == "archive":
        if task["state"] != "succeeded":
            raise ValueError("Batch archive requires a successful export")
        archive = root / "songs.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as output:
            for index, clip in enumerate(task["clips"], start=1):
                output.write(contained_path(Path(clip["path"]), root), f"{index:03d}_{clip['name']}")
        handler._serve_file(archive, downloadable=True)
    else:
        raise ValueError("Unknown export download")
