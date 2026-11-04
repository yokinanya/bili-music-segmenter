"""Register remote sources and store download cookies outside task/public data."""

from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from segment.workspace_uploads import now

DOWNLOAD_PREFIX = "__MUSIC_AGENT_DOWNLOAD__"


def validate_download(payload: dict) -> tuple[str, str]:
    if payload.keys() - {"url", "cookie", "options", "request_id"}:
        raise ValueError("包含未知下载字段")
    url, cookie = payload.get("url"), payload.get("cookie", "")
    if not isinstance(url, str):
        raise ValueError("请填写视频链接")
    parsed = urlsplit(url.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("视频链接必须是无内嵌凭据的 HTTP(S) 地址")
    if not isinstance(cookie, str) or "\x00" in cookie:
        raise ValueError("Cookie 格式无效")
    return url.strip(), cookie


def register_download(root: Path, store, *, url: str, cookie: str) -> dict:
    identity = uuid4().hex
    folder = root / "uploads" / identity
    folder.mkdir(parents=True)
    config = folder / "download.json"
    secret = {"url": url, "cookie": cookie, "folder": str(folder), "upload_id": identity}
    with os.fdopen(os.open(config, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as target:
        json.dump(secret, target, ensure_ascii=False)
    document = {
        "id": identity,
        "name": urlsplit(url).hostname + ".mkv",
        "size_bytes": 0,
        "state": "pending",
        "created_at": now(),
        "sha256": "",
        "error": None,
        "kind": "download",
        "remote_url": url,
        "download_config": str(config),
    }
    store.put("uploads", document)
    return {**document, "source_path": str(folder / "source.mkv")}


def update_download(job: dict, index: int, event: dict) -> dict:
    from segment.workspace_records import replace_item

    item = job["batch"][index]
    if event["state"] == "ready":
        return replace_item(
            job, index, {**item, "media": event["name"], "sha256": event["sha256"], "source_path": event["path"]}
        )
    steps = {step["id"]: step for step in item["steps"]}
    identity = event["id"]
    previous = steps.get(identity, {})
    steps[identity] = {
        "id": identity,
        "parent_id": None,
        "label": event["label"],
        "state": event["state"],
        "completed": event.get("completed", 0),
        "total": event.get("total"),
        "unit": event.get("unit"),
        "attempt": job["attempt"],
        "sequence": 0,
        "started_at": previous.get("started_at", now()),
        "finished_at": now() if event["state"] in {"succeeded", "failed", "reused"} else None,
        "error": event.get("error"),
    }
    return replace_item(job, index, {**item, "steps": list(steps.values())})
