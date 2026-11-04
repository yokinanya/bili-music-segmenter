"""Content-addressed local audio shared by retries and independent tasks."""

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
