"""Persistent front-end operated workspace; execution survives browser disconnects."""

from __future__ import annotations

import shutil
from pathlib import Path
from threading import RLock

from segment.music_agent.export import export_video
from segment.music_agent.media import media_duration
from segment.music_agent.runtime import fingerprint
from segment.workspace_downloads import register_download, validate_download
from segment.workspace_options import RETIRED_OPTIONS, default_options, validate_options
from segment.workspace_parts import can_complete_parts, is_bilibili_video
from segment.workspace_records import ACTIVE_STATES, end_steps, new_job
from segment.workspace_result_edit import edit_result, manifest_path
from segment.workspace_results import history_entry, make_archive, read_clips

LOG_READ_BYTES = 256 * 1024


class Jobs:
    def __init__(self, store, uploads, services: dict):
        self.store, self.uploads = store, uploads
        self.root = services["root"]
        self.execution = services["execution"]
        self.cleanup = services["cleanup"]
        self.usage = services["usage"]
        self.defaults = default_options()
        self.result_services = {
            "export": services.get("export", export_video),
            "duration": services.get("duration", media_duration),
            "source_root": self.root / "uploads",
            "save": lambda job: self.store.put("jobs", job),
        }
        self._lock = RLock()
        self._job_locks = {}
        self._reconcile()

    def _reconcile(self) -> None:
        for job in self.store.list("jobs"):
            if job["state"] not in ACTIVE_STATES:
                continue
            items = [
                end_steps({**item, "state": "interrupted"}, "interrupted") if item["state"] in ACTIVE_STATES else item
                for item in job["batch"]
            ]
            self.store.put(
                "jobs",
                {
                    **job,
                    "state": "interrupted",
                    "batch": items,
                    "current_index": None,
                    "error": "服务重启，执行已中断，请点击续跑",
                },
            )
        for upload in self.store.list("uploads"):
            if upload["state"] in {"uploading", "downloading"}:
                self.store.put("uploads", {**upload, "state": "failed", "error": "上传中断，请重新选择文件上传"})

    def start(self, payload: dict) -> str:
        with self._lock:
            ids, options, request = self._validate(payload)
            for job in self.store.list("jobs"):
                if job.get("request_id") != request:
                    continue
                if job["upload_ids"] != ids or job["options"] != options:
                    raise ValueError("同一请求 ID 对应的文件或参数不一致")
                return job["id"]
            uploads = [self._ready(identity) for identity in ids]
            job = new_job(uploads, options, request, self.root)
            self.store.put("jobs", job)
            self.execution.schedule(job["id"])
            return job["id"]

    def start_download(self, payload: dict) -> str:
        url, cookie = validate_download(payload)
        options = validate_options(payload.get("options", {}), self.defaults)
        request = payload.get("request_id")
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request_id 不能为空")
        stamp = fingerprint([url, cookie, options])
        with self._lock:
            for previous in self.store.list("jobs"):
                if previous["request_id"] == request:
                    if previous.get("remote_fingerprint") != stamp:
                        raise ValueError("同一请求 ID 对应的下载参数不一致")
                    return previous["id"]
            upload = register_download(
                self.root, self.store, url=url, cookie=cookie, resolve_parts=is_bilibili_video(url)
            )
            job = {**new_job([upload], options, request, self.root), "remote_fingerprint": stamp}
            self.store.put("jobs", job)
            self.execution.schedule(job["id"])
            return job["id"]

    def _validate(self, payload: dict) -> tuple:
        if payload.keys() - {"upload_ids", "options", "request_id"}:
            raise ValueError("包含未知任务字段")
        ids, request = payload.get("upload_ids"), payload.get("request_id")
        if not isinstance(ids, list) or not ids or any(not isinstance(value, str) for value in ids):
            raise ValueError("请选择已上传文件")
        if len(set(ids)) != len(ids):
            raise ValueError("任务中不能重复引用同一个文件 ID")
        if not isinstance(request, str) or not request.strip():
            raise ValueError("request_id 不能为空")
        return ids, validate_options(payload.get("options", {}), self.defaults), request

    def _ready(self, identity: str) -> dict:
        item = self.store.get("uploads", identity)
        path = self._source_path(item)
        if item["state"] != "ready" or not path.is_file():
            raise ValueError(f"源文件未完成上传或已缺失：{item['name']}")
        return {**{key: value for key, value in item.items() if key != "download_config"}, "source_path": str(path)}

    def _source_path(self, upload: dict) -> Path:
        if upload.get("kind") == "download":
            return self.root / "uploads" / upload["id"] / "source.mkv"
        return self.uploads.path(upload["id"])

    def _public_item(self, item: dict) -> dict:
        upload = self.store.get("uploads", item["upload_id"])
        return {
            **{key: value for key, value in item.items() if key != "download_config"},
            "source_type": upload.get("kind", "upload"),
            "source_url": upload.get("remote_url"),
            "can_reuse": upload["state"] == "ready" and self._source_path(upload).is_file(),
        }

    def status(self, identity: str) -> dict:
        job = self.store.get("jobs", identity)
        return {
            **job,
            "options": {key: value for key, value in job["options"].items() if key not in RETIRED_OPTIONS},
            "can_complete_parts": can_complete_parts(job, self.store),
            "batch": [self._public_item(item) for item in job["batch"]],
            "clips": [clip for item in job["batch"] for clip in read_clips(item)],
        }

    def _job_lock(self, identity: str):
        with self._lock:
            return self._job_locks.setdefault(identity, RLock())

    def manifest(self, identity: str, media_id: str) -> Path:
        with self._job_lock(identity):
            return manifest_path(self.store.get("jobs", identity), media_id)

    def edit_clip(self, identity: str, clip_id: str, payload: dict, *, progress=None) -> dict:
        if progress:
            progress({"stage": "preparing", "completed_seconds": 0, "total_seconds": None})
        with self._job_lock(identity):
            return edit_result(
                self.store.get("jobs", identity),
                {"clip_id": clip_id, "payload": payload},
                {**self.result_services, "progress": progress},
            )

    def history(self) -> list[dict]:
        current = [history_entry(self.status(job["id"])) for job in self.store.list("jobs")]
        return sorted([*self.store.list("legacy"), *current], key=lambda item: item["started_at"], reverse=True)

    def retry(self, identity: str) -> str:
        with self._job_lock(identity), self._lock:
            job = self.store.get("jobs", identity)
            complete_parts = can_complete_parts(job, self.store)
            if job["state"] in ACTIVE_STATES or job["state"] == "cleanup_pending":
                raise ValueError("当前任务不能续跑")
            if job["state"] == "succeeded" and not complete_parts:
                raise ValueError("当前任务不能续跑")
            for upload in job["upload_ids"]:
                if self.store.get("uploads", upload).get("kind") != "download":
                    self._ready(upload)
            items = [
                {
                    **item,
                    "last_sequence": 0,
                    "state": "queued",
                    "error": None,
                    "steps": [],
                    **({"discover_only": True} if complete_parts else {}),
                }
                if item["state"] != "succeeded" or complete_parts
                else item
                for item in job["batch"]
            ]
            self.store.put(
                "jobs",
                {
                    **job,
                    "batch": items,
                    "attempt": job["attempt"] + 1,
                    "state": "queued",
                    "finished_at": None,
                    "stop_requested": False,
                    "error": None,
                },
            )
            self.execution.schedule(identity)
        return identity

    def stop_current(self, identity: str) -> None:
        if self.store.get("jobs", identity)["state"] not in ACTIVE_STATES:
            raise ValueError("任务当前没有运行")
        self.execution.stop(identity)

    def log_chunk(self, identity: str, index: int, offset: int) -> dict:
        item = self.store.get("jobs", identity)["batch"][index]
        path = Path(item["log_path"])
        if not path.exists() and item["state"] == "queued":
            return {"text": "", "offset": 0, "complete": False}
        with path.open("rb") as source:
            source.seek(offset)
            data = source.read(LOG_READ_BYTES)
        # Leave an incomplete UTF-8 code point for the next read.
        text = data.decode("utf-8", errors="strict") if not data else self._decode(data)
        return {"text": text, "offset": offset + len(text.encode()), "complete": item["state"] not in ACTIVE_STATES}

    @staticmethod
    def _decode(data: bytes) -> str:
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as error:
            if error.reason != "unexpected end of data":
                raise
            return data[: error.start].decode("utf-8")

    def clip_info(self, identity: str, clip_id: str) -> dict:
        for clip in self.status(identity)["clips"]:
            if clip["id"] == clip_id:
                path = Path(clip["path"])
                if path.is_file():
                    return clip
        raise KeyError(clip_id)

    def clip_path(self, identity: str, clip_id: str) -> Path:
        return Path(self.clip_info(identity, clip_id)["path"])

    def archive(self, identity: str) -> Path:
        with self._job_lock(identity):
            return make_archive(self.status(identity), self.root / "jobs" / identity)

    def delete(self, identity: str) -> None:
        with self._job_lock(identity), self._lock:
            job = self.store.get("jobs", identity)
            if job["state"] in ACTIVE_STATES:
                raise ValueError("请先停止任务再删除")
            self.store.put("jobs", {**job, "state": "cleanup_pending", "cleanup_error": None})
            try:
                self.cleanup(identity)
                directory = self.root / "jobs" / identity
                if directory.exists():
                    shutil.rmtree(directory)
                self._remove_sources(job["upload_ids"], excluding=identity)
                self.store.delete("jobs", identity)
            except Exception as error:
                self.store.put("jobs", {**job, "state": "cleanup_pending", "cleanup_error": str(error)})
                raise

    def _remove_sources(self, identities: list[str], *, excluding: str) -> None:
        remaining = [job for job in self.store.list("jobs") if job["id"] != excluding]
        for identity in identities:
            if any(identity in job["upload_ids"] for job in remaining):
                continue
            if any(source["id"] == identity for source in self.store.list("uploads")):
                self.uploads.remove(identity, excluding_job=excluding)

    def close(self) -> None:
        self.execution.close()
