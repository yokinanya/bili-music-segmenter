"""Persist finished jobs so the page can list history across service restarts."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any

from segment.logs import log_dir

HISTORY_FILE = "webui-history.json"
MAX_ENTRIES = 200


def _history_path() -> Path:
    return log_dir() / HISTORY_FILE


class JobHistory:
    """Append-only list of finished jobs, written atomically and capped in size."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _history_path()
        self._lock = Lock()

    def load(self) -> list[dict[str, Any]]:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def record(self, entry: dict[str, Any]) -> None:
        with self._lock:
            entries = [item for item in self.load() if item.get("id") != entry.get("id")]
            entries.append({**entry, "finished_at": datetime.now().isoformat(timespec="seconds")})
            entries = entries[-MAX_ENTRIES:]
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._path.with_suffix(".tmp")
            temporary.write_text(json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temporary.replace(self._path)
