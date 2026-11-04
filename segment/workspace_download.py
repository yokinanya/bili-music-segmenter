"""yt-dlp child entry: download, merge, persist source, then execute the API pipeline."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import time
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit

from segment.events import emit_event
from segment.music_agent.runtime import file_digest
from segment.workspace_downloads import DOWNLOAD_PREFIX
from segment.workspace_store import DocumentStore

PROGRESS_INTERVAL_SECONDS = 0.25


def cookie_jar(config: dict, downloader) -> None:
    cookie = config["cookie"].strip()
    if not cookie:
        return
    if cookie.startswith("# Netscape HTTP Cookie File") or "\t" in cookie:
        cookie_file = Path(config["folder"]) / "cookies.txt"
        cookie_file.write_text(cookie, encoding="utf-8")
        cookie_file.chmod(0o600)
        downloader.cookiejar.load(str(cookie_file), ignore_discard=True, ignore_expires=True)
        return
    parsed = SimpleCookie()
    parsed.load(cookie.removeprefix("Cookie:").strip())
    if not parsed:
        raise ValueError("Cookie 无法解析，请填写 Cookie 请求头或 Netscape cookies.txt 内容")
    host = urlsplit(config["url"]).hostname
    for name, value in parsed.items():
        entry = http.cookiejar.Cookie(
            0, name, value.value, None, False, host, False, False, "/", True, False, None, True, None, None, {}, False
        )
        downloader.cookiejar.set_cookie(entry)


class DownloadProgress:
    def __init__(self):
        self.last = 0.0

    def progress(self, event: dict) -> None:
        if event["status"] == "error":
            self.report("download", "下载视频", state="failed", error=str(event))
            return
        moment = time.monotonic()
        if moment - self.last < PROGRESS_INTERVAL_SECONDS and event["status"] != "finished":
            return
        self.last = moment
        identity = "download/" + str(event.get("info_dict", {}).get("format_id", "media"))
        self.report(
            identity,
            "下载音视频轨",
            state="succeeded" if event["status"] == "finished" else "running",
            completed=event.get("downloaded_bytes", 0),
            total=event.get("total_bytes"),
            unit="字节",
        )

    def postprocess(self, event: dict) -> None:
        self.report(
            "merge/" + event["postprocessor"],
            "合并与封装",
            state="succeeded" if event["status"] == "finished" else "running",
        )

    @staticmethod
    def report(identity: str, label: str, **changes) -> None:
        emit_event(DOWNLOAD_PREFIX, {"id": identity, "label": label, **changes})


def download_source(config: dict, *, factory, store: DocumentStore) -> Path:
    document = store.get("uploads", config["upload_id"])
    destination = Path(config["folder"]) / "source.mkv"
    progress = DownloadProgress()
    if document["state"] == "ready" and destination.is_file() and file_digest(destination) == document["sha256"]:
        progress.report("download", "复用已下载视频", state="reused")
        _ready_event(document, destination)
        return destination
    options = {
        "outtmpl": str(Path(config["folder"]) / "source.%(ext)s"),
        "noplaylist": True,
        "merge_output_format": "mkv",
        "quiet": True,
        "noprogress": True,
        "progress_hooks": [progress.progress],
        "postprocessor_hooks": [progress.postprocess],
        "postprocessors": [{"key": "FFmpegVideoRemuxer", "preferedformat": "mkv"}],
    }
    store.put("uploads", {**document, "state": "downloading", "error": None})
    try:
        with factory(options) as downloader:
            cookie_jar(config, downloader)
            info = downloader.extract_info(config["url"], download=True)
        if not destination.is_file() or destination.stat().st_size <= 0:
            raise ValueError("yt-dlp 未生成完整的合并视频")
        ready = {
            **document,
            "state": "ready",
            "name": info["title"] + ".mkv",
            "sha256": file_digest(destination),
            "size_bytes": destination.stat().st_size,
            "error": None,
        }
        store.put("uploads", ready)
        _ready_event(ready, destination)
        return destination
    except Exception as error:
        store.put("uploads", {**document, "state": "failed", "error": str(error)})
        progress.report("download", "下载视频", state="failed", error=str(error))
        raise


def _ready_event(document: dict, destination: Path) -> None:
    emit_event(
        DOWNLOAD_PREFIX,
        {"state": "ready", "name": document["name"], "path": str(destination), "sha256": document["sha256"]},
    )


def main() -> None:
    from yt_dlp import YoutubeDL

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-config", type=Path, required=True)
    parser.add_argument("--outdir", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.source_config.read_text(encoding="utf-8"))
    store = DocumentStore(Path(os.environ["MUSIC_AGENT_STATE_DIR"]) / "workspace.sqlite3")
    source = download_source(config, factory=YoutubeDL, store=store)
    os.environ["MUSIC_AGENT_SOURCE_DIGEST"] = store.get("uploads", config["upload_id"])["sha256"]
    sys.argv = ["music-agent", "--media", str(source), "--outdir", str(args.outdir)]
    from segment.music_agent.cli import main as process

    process()


if __name__ == "__main__":
    main()
