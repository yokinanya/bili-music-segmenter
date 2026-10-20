"""S3 transfer progress events and thread-safe in-memory state."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock

from segment.events import emit_event

UPLOAD_PREFIX = "__MUSIC_AGENT_UPLOAD__"


@dataclass
class UploadProgress:
    _uploads: dict[str, dict] = field(default_factory=dict, repr=False)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def update(self, event: dict) -> None:
        with self._lock:
            self._uploads[event["key"]] = dict(event)

    def snapshot(self) -> dict:
        with self._lock:
            return {"uploads": [dict(event) for event in self._uploads.values()]}


class UploadReporter:
    def __init__(self, key: str, total_bytes: int) -> None:
        self._lock = Lock()
        self._event = {"key": key, "total_bytes": total_bytes, "transferred_bytes": 0, "state": "uploading"}

    def __call__(self, byte_count: int) -> None:
        with self._lock:
            self._event["transferred_bytes"] += byte_count
            self._emit()

    def state(self, state: str) -> None:
        with self._lock:
            self._event["state"] = state
            self._emit()

    def _emit(self) -> None:
        emit_event(UPLOAD_PREFIX, self._event)
