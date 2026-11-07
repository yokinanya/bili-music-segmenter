"""Discover Bilibili parts before downloading and expand the durable video queue."""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from segment.workspace_downloads import register_download, validate_download
from segment.workspace_records import new_item


def is_bilibili_video(url: str) -> bool:
    parsed = urlsplit(url)
    host = parsed.hostname or ""
    if host == "b23.tv" or host.endswith(".b23.tv"):
        return True
    return host in {"bilibili.com", "www.bilibili.com"} and parsed.path.startswith(("/video/", "/festival/"))


def can_complete_parts(job: dict, store) -> bool:
    if job["state"] != "succeeded" or len(job["batch"]) != 1:
        return False
    item = job["batch"][0]
    if item.get("parts_resolved"):
        return False
    upload = store.get("uploads", item["upload_id"])
    url = upload.get("remote_url", "")
    return upload.get("kind") == "download" and is_bilibili_video(url) and "p" not in parse_qs(urlsplit(url).query)


def discover_parts(config: dict, *, factory, configure_cookies) -> list[dict]:
    options = {"quiet": True, "noprogress": True, "noplaylist": False, "extract_flat": "in_playlist"}
    with factory(options) as downloader:
        configure_cookies(config, downloader)
        info = downloader.extract_info(config["url"], download=False)
        if not isinstance(info, dict):
            raise ValueError("未能读取视频分 P 信息")
        if info.get("_type") != "playlist":
            return [{"url": info.get("webpage_url") or config["url"], "name": info["title"] + ".mkv"}]
        sources = [_part_source(entry, info) for entry in info["entries"]]
    if not sources:
        raise ValueError("视频分 P 列表为空")
    return sources


def _part_source(entry: dict, info: dict) -> dict:
    if not isinstance(entry, dict):
        raise ValueError("分 P 信息缺失")
    url, _ = validate_download({"url": entry.get("url")})
    if not is_bilibili_video(url) or entry.get("ie_key") != "BiliBili":
        raise ValueError("该链接返回的列表不是哔哩哔哩视频分 P")
    part = parse_qs(urlsplit(url).query).get("p", [])
    if not part or not part[0].isdigit() or int(part[0]) <= 0:
        raise ValueError("分 P 地址缺少有效的 p 参数")
    title = entry.get("title") or f"{info['title']} · P{part[0]}"
    return {"url": url, "name": title + ".mkv"}


def resolve_source(config: dict, *, factory, configure_cookies) -> tuple[dict, list[dict]]:
    if not config.get("resolve_parts", is_bilibili_video(config["url"])):
        return config, []
    sources = config.get("resolved_sources")
    if sources is None:
        sources = discover_parts(config, factory=factory, configure_cookies=configure_cookies)
        saved = {**config, "resolved_sources": sources}
        path = Path(config["folder"]) / "download.json"
        temporary = path.with_suffix(".tmp")
        temporary.unlink(missing_ok=True)
        temporary.touch(mode=0o600, exist_ok=False)
        temporary.write_text(json.dumps(saved, ensure_ascii=False), encoding="utf-8")
        temporary.replace(path)
    return {**config, "url": sources[0]["url"]}, sources


def expand_parts(job: dict, index: int, *, sources: list[dict], store, root: Path) -> dict:
    item = job["batch"][index]
    if item.get("parts_resolved"):
        return job
    if not sources:
        raise ValueError("视频分 P 列表为空")
    original = store.get("uploads", item["upload_id"])
    config = json.loads(Path(original["download_config"]).read_text(encoding="utf-8"))
    uploads = [
        register_download(root, store, url=source["url"], cookie=config["cookie"], name=source["name"])
        for source in sources[1:]
    ]
    first = {**item, "media": sources[0]["name"], "parts_resolved": True}
    following = [new_item(upload, root / "jobs" / job["id"]) for upload in uploads]
    return {
        **job,
        "upload_ids": [*job["upload_ids"], *(upload["id"] for upload in uploads)],
        "batch": [*job["batch"][:index], first, *following, *job["batch"][index + 1 :]],
    }
