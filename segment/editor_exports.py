"""Persistent export snapshots; editing cannot mutate an in-flight export."""

import re
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from segment.music_agent.media_process import reporting_media
from segment.workspace_uploads import now


class Exports:
    def __init__(self, store, root: Path, services: dict):
        self.store, self.root, self.services = store, root, services
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="song-export")
        for task in store.list("editor_exports"):
            if task["state"] in {"queued", "running"}:
                store.put("editor_exports", {**task, "state": "interrupted", "error": "Service restarted"})

    def start(self, project: dict, identities: list[str], *, filename_suffix: str = "") -> dict:
        if not isinstance(filename_suffix, str) or re.search(r'[\\/:*?"<>|\x00-\x1f]', filename_suffix):
            raise ValueError("文件名后缀不能包含路径分隔符、控制字符或非法文件名字符")
        if (
            not isinstance(identities, list)
            or not identities
            or any(not isinstance(value, str) for value in identities)
            or len(identities) != len(set(identities))
        ):
            raise ValueError("Select unique clip IDs for export")
        clips = [deepcopy(clip) for clip in project["clips"] if clip["id"] in identities]
        if len(clips) != len(identities):
            raise ValueError("Export references unknown clips")
        clips = [
            {**clip, "name": Path(clip["name"]).stem + filename_suffix + Path(clip["name"]).suffix} for clip in clips
        ]
        task = {
            "id": uuid4().hex,
            "project_id": project["id"],
            "upload_id": project["upload_id"],
            "revision": project["revision"],
            "clips": clips,
            "filename_suffix": filename_suffix,
            "state": "queued",
            "completed": 0,
            "progress": None,
            "error": None,
            "created_at": now(),
        }
        self.store.put("editor_exports", task)
        self.executor.submit(self._run, task)
        return task

    def _update(self, identity: str, changes: dict) -> dict:
        return self.store.update("editor_exports", identity, lambda task: {**task, **changes})

    def _run(self, snapshot: dict) -> None:
        identity = snapshot["id"]
        self._update(identity, {"state": "running"})
        try:
            source = self.services["source"](snapshot["upload_id"])
            for index, clip in enumerate(snapshot["clips"]):
                task = self.store.get("editor_exports", identity)
                if task.get("cancel_requested"):
                    self._update(identity, {"state": "cancelled"})
                    return
                destination = self.root / "editor-exports" / identity / f"{index}.mp4"
                destination.parent.mkdir(parents=True, exist_ok=True)
                with reporting_media(lambda progress: self._update(identity, {"progress": progress})):
                    self.services["export"](source, clip["start_seconds"], clip["end_seconds"], destination)
                if not destination.is_file() or not destination.stat().st_size:
                    raise RuntimeError("Export did not produce a nonempty video")
                clips = [*task["clips"]]
                clips[index] = {**clip, "path": str(destination)}
                self._update(identity, {"clips": clips, "completed": index + 1})
            self._update(identity, {"state": "succeeded", "progress": None})
        except Exception as error:
            self._update(identity, {"state": "failed", "error": str(error)})

    def cancel(self, identity: str) -> dict:
        task = self.store.get("editor_exports", identity)
        if task["state"] not in {"queued", "running"}:
            raise ValueError("Export is not running")
        return self._update(identity, {"cancel_requested": True})

    def close(self) -> None:
        self.executor.shutdown(wait=True)
