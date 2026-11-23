"""Content-addressed local audio shared by retries and independent tasks."""

import re
from pathlib import Path
from threading import Lock

from segment.music_agent.runtime import fingerprint

CACHE_VERSION = "audio-extract-1"


class LocalMediaCache:
    def __init__(self, store, config: dict):
        self.store, self.config = store, config
        self._lock = Lock()
        self._locks = {}

    def acquire(self, payload: dict, extract) -> Path:
        identity = fingerprint([CACHE_VERSION, self.config["source_digest"], payload])
        path = Path(self.config["state_dir"]) / "audio" / (identity + payload["suffix"])
        with self._lock:
            lock = self._locks.setdefault(identity, Lock())
        with lock:
            self._register(identity, path)
            if path.is_file() and path.stat().st_size > 0:
                return path
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.stem + ".part" + path.suffix)
            extract(temporary)
            if not temporary.is_file() or temporary.stat().st_size <= 0:
                raise ValueError("音频提取结果为空")
            temporary.replace(path)
            return path

    def _register(self, identity: str, path: Path) -> None:
        existing = {item["id"] for item in self.store.list("local_cache")}
        if identity not in existing:
            self.store.put("local_cache", {"id": identity, "path": str(path), "owners": []})
        self.store.update(
            "local_cache",
            identity,
            lambda item: {
                **item,
                "owners": sorted(set(item["owners"]) | {self.config["owner"]}),
            },
        )


def _managed_audio(root: Path, item: dict) -> tuple[Path, ...] | None:
    identity = item["id"]
    if not re.fullmatch(r"[0-9a-f]{64}", identity):
        return None
    path = root / "audio" / f"{identity}.mp3"
    if Path(item["path"]) != path or path.parent.resolve() != path.parent:
        return None
    return path, path.with_suffix(".part.mp3")


def _managed_audio_entries(store, root: Path):
    for item in store.list("local_cache"):
        paths = _managed_audio(root, item)
        if paths is not None and not any(path.is_symlink() for path in paths):
            yield item["id"], paths


def _audio_file_bytes(path: Path) -> int:
    try:
        return path.stat().st_size if path.is_file() else 0
    except FileNotFoundError:
        # A worker can rename the partial file while the preview is being read.
        return 0


def audio_cache_bytes(store, root: Path) -> int:
    return sum(_audio_file_bytes(path) for _, paths in _managed_audio_entries(store, root) for path in paths)


def clear_audio_cache(store, root: Path) -> int:
    removed = 0
    for identity, paths in _managed_audio_entries(store, root):
        for path in paths:
            if path.is_file():
                path.unlink()
                removed += 1
        store.delete("local_cache", identity)
    return removed


def clean_local_cache(store, owner: str) -> None:
    for item in store.list("local_cache"):
        if owner not in item["owners"]:
            continue
        others = [value for value in item["owners"] if value != owner]
        if others:
            store.update("local_cache", item["id"], lambda current: {**current, "owners": others})
            continue
        path = Path(item["path"])
        path.unlink(missing_ok=True)
        path.with_name(path.stem + ".part" + path.suffix).unlink(missing_ok=True)
        store.delete("local_cache", item["id"])
