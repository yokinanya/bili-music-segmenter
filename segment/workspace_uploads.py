"""Stream browser media into files identified independently of their names."""

from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import BinaryIO
from uuid import uuid4

from segment.workspace_store import DocumentStore

COPY_BYTES = 256 * 1024
MEDIA_SUFFIXES = frozenset(".mp4 .mkv .flv .ts .mov .m4v .webm .mp3 .m4a .aac .wav .flac .ogg".split())


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Uploads:
    def __init__(self, root: Path, store: DocumentStore):
        self.root = root
        self.store = store
        self._lock = Lock()
        self._receiving: set[str] = set()

    def register(self, payload: dict) -> dict:
        name, size = payload.get("name"), payload.get("size_bytes")
        if not isinstance(name, str) or not name.strip() or "\x00" in name:
            raise ValueError("文件名无效")
        if Path(name).suffix.lower() not in MEDIA_SUFFIXES:
            raise ValueError("不支持的媒体格式")
        if type(size) is not int or size <= 0:
            raise ValueError("文件大小必须是正整数")
        document = {
            "id": uuid4().hex,
            "name": name,
            "size_bytes": size,
            "state": "pending",
            "created_at": now(),
            "sha256": "",
            "error": None,
        }
        self.store.put("uploads", document)
        return document

    def path(self, identity: str) -> Path:
        document = self.store.get("uploads", identity)
        return self.root / identity / ("source" + Path(document["name"]).suffix.lower())

    def receive(self, identity: str, stream: BinaryIO, size: int) -> dict:
        document = self.store.get("uploads", identity)
        if any(identity in job["upload_ids"] for job in self.store.list("jobs")):
            raise ValueError("源文件已被任务引用，不能覆盖")
        if size != document["size_bytes"]:
            raise ValueError("上传长度与登记的文件大小不一致")
        with self._lock:
            if identity in self._receiving:
                raise ValueError("该文件正在上传")
            self._receiving.add(identity)
        try:
            return self._receive(document, stream)
        finally:
            with self._lock:
                self._receiving.remove(identity)

    def _receive(self, document: dict, stream: BinaryIO) -> dict:
        destination = self.path(document["id"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_suffix(".part")
        self.store.put("uploads", {**document, "state": "uploading", "error": None})
        try:
            digest = self._copy(stream, temporary, document["size_bytes"])
            temporary.replace(destination)
        except Exception as error:
            temporary.unlink(missing_ok=True)
            self.store.put("uploads", {**document, "state": "failed", "error": str(error)})
            raise
        complete = {**document, "state": "ready", "sha256": digest, "error": None}
        self.store.put("uploads", complete)
        return complete

    @staticmethod
    def _copy(stream: BinaryIO, destination: Path, size: int) -> str:
        remaining, digest = size, hashlib.sha256()
        with destination.open("wb") as target:
            while remaining:
                chunk = stream.read(min(COPY_BYTES, remaining))
                if not chunk:
                    raise ValueError("上传提前结束，请重新上传此文件")
                target.write(chunk)
                digest.update(chunk)
                remaining -= len(chunk)
        return digest.hexdigest()

    def remove(self, identity: str, *, excluding_job: str | None = None) -> None:
        with self._lock:
            if identity in self._receiving:
                raise ValueError("请先取消正在进行的上传")
            if any(
                identity in job.get("upload_ids", []) for job in self.store.list("jobs") if job["id"] != excluding_job
            ):
                raise ValueError("源文件仍被任务引用")
            folder = self.path(identity).parent
            if folder.exists():
                shutil.rmtree(folder)
            self.store.delete("uploads", identity)
