import http.cookiejar
import json
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest
from workspace_support import make_jobs, wait_for_job

from segment.workspace_download import cookie_jar, download_source
from segment.workspace_downloads import register_download, validate_download
from segment.workspace_store import DocumentStore


def test_download_registration_idempotency_and_cookie_storage(tmp_path):
    jobs = make_jobs(tmp_path)
    try:
        payload = {
            "url": "https://www.bilibili.com/video/BVtest",
            "cookie": "SESSION=test-cookie",
            "request_id": "download",
        }
        first = jobs.start_download(payload)
        assert jobs.start_download(payload) == first
        job = wait_for_job(jobs, first)
        assert "test-cookie" not in json.dumps(job)
        assert "download_config" not in job["batch"][0]
        internal_job = jobs.store.get("jobs", first)
        config = Path(internal_job["batch"][0]["download_config"])
        assert config.stat().st_mode & 0o777 == 0o600
        assert json.loads(config.read_text())["cookie"] == payload["cookie"]
        jobs.delete(first)
        assert not config.exists()
    finally:
        jobs.close()


def test_downloader_preserves_source_and_reuses_completed_file(tmp_path):
    store = DocumentStore(tmp_path / "workspace.sqlite3")
    source = register_download(tmp_path, store, url="https://video.test/watch", cookie="")
    config = json.loads(Path(source["download_config"]).read_text())
    options = []

    class Downloader:
        cookiejar = http.cookiejar.MozillaCookieJar()

        def __init__(self, settings):
            options.append(settings)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, *, download):
            assert url == config["url"] and download
            (Path(config["folder"]) / "source.mkv").write_bytes(b"merged-media")
            return {"title": "中文标题"}

    path = download_source(config, factory=Downloader, store=store)
    assert path.read_bytes() == b"merged-media"
    assert options[0]["merge_output_format"] == "mkv" and options[0]["noplaylist"]
    assert download_source(config, factory=Mock(side_effect=AssertionError("redownload")), store=store) == path
    assert store.get("uploads", source["id"])["name"] == "中文标题.mkv"


def test_cookie_parser_scopes_raw_header_and_accepts_netscape_file(tmp_path):
    config = {"url": "https://www.bilibili.com/video/example", "folder": str(tmp_path), "cookie": "a=one; b=two"}
    downloader = Mock(cookiejar=http.cookiejar.MozillaCookieJar())
    cookie_jar(config, downloader)
    assert {entry.name: entry.value for entry in downloader.cookiejar} == {"a": "one", "b": "two"}
    assert all(entry.domain == "www.bilibili.com" for entry in downloader.cookiejar)
    cookie_jar(
        {**config, "cookie": "# Netscape HTTP Cookie File\n.bilibili.com\tTRUE\t/\tTRUE\t0\tsession\tvalue\n"},
        downloader,
    )
    assert "session" in {entry.name for entry in downloader.cookiejar}
    assert (tmp_path / "cookies.txt").stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@example.com", "", 1])
def test_download_rejects_invalid_url(url):
    with pytest.raises(ValueError):
        validate_download({"url": url})


def test_netease_extracted_javascript_calls_upstream_without_service():
    script = """
const assert = require('node:assert/strict');
global.fetch = async (url, options) => {
  assert.equal(url.origin, 'https://interface.music.163.com');
  assert.equal(url.pathname, '/api/music/audio/match');
  assert.equal(url.searchParams.get('rawdata'), 'audio+fingerprint');
  assert.equal(url.searchParams.get('algorithmCode'), 'shazam_v2');
  assert.equal(options.headers.Cookie, 'session=example');
  return {ok:true,json:async()=>({code:200,data:{result:{title:'song',artist:'artist'}}})};
};
const {audioMatch} = require('./vendor/ncm-afp/audio_match.js');
audioMatch({audioFP:'audio+fingerprint',duration:3,cookie:'session=example',timeout:5})
.then(result=>assert.equal(result.data.result.title,'song'))
.catch(error=>{console.error(error);process.exitCode=1});
"""
    subprocess.run(["node", "-e", script], check=True, capture_output=True, timeout=10)


def generate_test_video(destination):
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=s=160x90:d=1",
            "-f",
            "lavfi",
            "-i",
            "sine=duration=1",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(destination),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )


def test_real_ytdlp_download_and_remux_from_http(tmp_path):
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread

    from yt_dlp import YoutubeDL

    served = tmp_path / "served"
    served.mkdir()
    generate_test_video(served / "video.mp4")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(served)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    store = DocumentStore(tmp_path / "workspace.sqlite3")
    try:
        registered = register_download(
            tmp_path, store, url=f"http://127.0.0.1:{server.server_port}/video.mp4", cookie=""
        )
        config = json.loads(Path(registered["download_config"]).read_text())
        source = download_source(config, factory=YoutubeDL, store=store)
        assert source.suffix == ".mkv" and source.stat().st_size > 0
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "json", str(source)],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert {item["codec_type"] for item in json.loads(result.stdout)["streams"]} == {"audio", "video"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
