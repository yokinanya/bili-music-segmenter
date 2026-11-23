"""Clear only explicitly selected, regenerable workspace caches."""

from pathlib import Path

from segment.editor_media import clear_waveforms, waveform_cache_bytes
from segment.music_agent.media_cache import audio_cache_bytes, clear_audio_cache
from segment.workspace_records import ACTIVE_STATES
from segment.workspace_store import DocumentStore

CATEGORIES = ("recognition", "waveform", "audio")


def cache_preview(store: DocumentStore, root: Path) -> dict:
    return {"bytes": {
        "recognition": store.collection_bytes("recognition_results"),
        "waveform": waveform_cache_bytes(root / "editor-cache"),
        "audio": audio_cache_bytes(store, root),
    }}


def clear_caches(store: DocumentStore, root: Path, payload: dict) -> dict:
    categories = payload.get("categories")
    if not isinstance(categories, list) or not categories:
        raise ValueError("请至少选择一项缓存")
    if payload.keys() != {"categories"} or any(category not in CATEGORIES for category in categories):
        raise ValueError("缓存分类无效")
    if "audio" in categories and any(job["state"] in ACTIVE_STATES for job in store.list("jobs")):
        raise ValueError("有任务正在排队或运行，结束后才能清除提取音频缓存")
    removed = {}
    if "audio" in categories:
        removed["audio"] = clear_audio_cache(store, root)
    if "waveform" in categories:
        removed["waveform"] = clear_waveforms(root / "editor-cache")
    if "recognition" in categories:
        removed["recognition"] = store.clear_collection("recognition_results")
    return {"removed": removed}
