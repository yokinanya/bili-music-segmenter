"""Content-addressed audio objects retained until their last task is deleted."""

from __future__ import annotations

from contextlib import nullcontext
from threading import Lock

from segment.music_agent.runtime import CURRENT, fingerprint


class AudioCache:
    def __init__(self, storage, config: dict, store):
        self.storage = storage
        self.config = config
        self.store = store
        self._locks: dict[str, Lock] = {}
        self._lock = Lock()

    def acquire(self, payload: dict, extract) -> str:
        identity = fingerprint([self.storage.identity, payload, "pcm-s16le-24k-mono-v1"])
        key = "/".join(filter(None, (payload["prefix"], "cache", identity + ".wav")))
        with self._lock:
            lock = self._locks.setdefault(identity, Lock())
        with lock:
            self._register(identity, key)
            if self.storage.exists(key):
                self.store.update("audio_cache", identity, lambda item: {**item, "ready": True})
                self._progress(identity, "reused")
                return key
            self._progress(identity, "running", message="缓存未命中，提取并上传音频")
            source = extract()
            scope = CURRENT.get()
            budget = scope.runtime.resource("upload") if scope else nullcontext()
            with budget:
                self.storage.upload(key, source)
            self.store.update("audio_cache", identity, lambda item: {**item, "ready": True})
            self._progress(identity, "succeeded")
            return key

    def _register(self, identity: str, key: str) -> None:
        owner = self.config["owner"]
        try:
            self.store.get("audio_cache", identity)
        except KeyError:
            self.store.put(
                "audio_cache",
                {
                    "id": identity,
                    "key": key,
                    "owners": [],
                    "ready": False,
                    "storage": self.storage.identity,
                },
            )
        self.store.update(
            "audio_cache",
            identity,
            lambda item: {**item, "owners": sorted(set(item["owners"]) | {owner})},
        )

    @staticmethod
    def _progress(identity: str, state: str, **changes) -> None:
        scope = CURRENT.get()
        if scope:
            scope.runtime.event("cache/" + identity, "S3 音频缓存", state=state, **changes)


def clean_audio_cache(store, owner: str, storage) -> None:
    for item in store.list("audio_cache"):
        if owner not in item["owners"]:
            continue
        others = [value for value in item["owners"] if value != owner]
        if others:
            store.update("audio_cache", item["id"], lambda current: {**current, "owners": others})
            continue
        if item["storage"] != storage.identity:
            raise ValueError("缓存的 S3 配置与当前配置不一致，无法清理")
        storage.delete(item["key"])
        store.delete("audio_cache", item["id"])
