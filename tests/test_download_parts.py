import http.cookiejar
import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from workspace_support import make_jobs, wait_for_job

from segment.workspace_download import cookie_jar, download_source
from segment.workspace_downloads import register_download
from segment.workspace_parts import discover_parts, is_bilibili_video, resolve_source
from segment.workspace_store import DocumentStore

VIDEO_URL = "https://www.bilibili.com/video/BVexample"
SOURCES = [
    {"url": VIDEO_URL + "?p=1", "name": "歌曲 P1.mkv"},
    {"url": VIDEO_URL + "?p=2", "name": "歌曲 P2.mkv"},
    {"url": VIDEO_URL + "?p=3", "name": "歌曲 P3.mkv"},
]


def metadata_factory(info):
    downloader = Mock(cookiejar=http.cookiejar.MozillaCookieJar())
    downloader.extract_info.return_value = info
    downloader.__enter__ = Mock(return_value=downloader)
    downloader.__exit__ = Mock(return_value=False)
    return Mock(return_value=downloader), downloader


def playlist():
    return {
        "_type": "playlist",
        "title": "多 P 视频",
        "entries": ({"url": source["url"], "title": source["name"][:-4], "ie_key": "BiliBili"} for source in SOURCES),
    }


def test_discovery_reads_all_parts_and_applies_cookie(tmp_path):
    factory, downloader = metadata_factory(playlist())
    config = {"url": VIDEO_URL, "cookie": "SESSDATA=example", "folder": str(tmp_path)}
    assert discover_parts(config, factory=factory, configure_cookies=cookie_jar) == SOURCES
    assert factory.call_args.args[0]["noplaylist"] is False
    assert factory.call_args.args[0]["extract_flat"] == "in_playlist"
    downloader.extract_info.assert_called_once_with(VIDEO_URL, download=False)
    assert next(iter(downloader.cookiejar)).value == "example"


def test_short_link_raw_cookie_is_scoped_to_bilibili_destination(tmp_path):
    from urllib.request import Request

    downloader = Mock(cookiejar=http.cookiejar.MozillaCookieJar())
    config = {"url": "https://b23.tv/example", "cookie": "SESSDATA=example", "folder": str(tmp_path)}
    cookie_jar(config, downloader)
    destination = Request(VIDEO_URL)
    downloader.cookiejar.add_cookie_header(destination)
    assert destination.get_header("Cookie") == "SESSDATA=example"
    short_link = Request(config["url"])
    downloader.cookiejar.add_cookie_header(short_link)
    assert short_link.get_header("Cookie") is None


@pytest.mark.parametrize("url", [VIDEO_URL, VIDEO_URL + "?p=2", "https://b23.tv/example"])
def test_single_part_and_redirect_use_extracted_address(tmp_path, url):
    canonical = VIDEO_URL + "?p=2"
    factory, _ = metadata_factory({"title": "第二 P", "webpage_url": canonical})
    config = {"url": url, "cookie": "", "folder": str(tmp_path)}
    assert discover_parts(config, factory=factory, configure_cookies=cookie_jar) == [
        {"url": canonical, "name": "第二 P.mkv"}
    ]


@pytest.mark.parametrize(
    "info",
    [None, {"_type": "playlist", "entries": []}, {"_type": "playlist", "entries": [None]}],
)
def test_invalid_metadata_is_an_explicit_failure(tmp_path, info):
    factory, _ = metadata_factory(info)
    with pytest.raises(ValueError):
        discover_parts(
            {"url": VIDEO_URL, "cookie": "", "folder": str(tmp_path)},
            factory=factory,
            configure_cookies=cookie_jar,
        )


def test_resolution_persists_parts_for_retry_without_reprobing(tmp_path):
    store = DocumentStore(tmp_path / "workspace.sqlite3")
    upload = register_download(tmp_path, store, url=VIDEO_URL, cookie="session=test", resolve_parts=True)
    path = Path(upload["download_config"])
    factory, _ = metadata_factory(playlist())
    config, sources = resolve_source(json.loads(path.read_text()), factory=factory, configure_cookies=cookie_jar)
    assert config["url"] == SOURCES[0]["url"] and sources == SOURCES
    saved = json.loads(path.read_text())
    assert saved["url"] == VIDEO_URL and saved["resolved_sources"] == SOURCES
    assert path.stat().st_mode & 0o777 == 0o600
    again, _ = resolve_source(saved, factory=Mock(side_effect=AssertionError("reprobe")), configure_cookies=cookie_jar)
    assert again["url"] == config["url"]


def queue_program():
    return f"""
import os, sys
from segment.events import emit_event
from segment.workspace_downloads import DOWNLOAD_PREFIX
if sys.argv[1] == 'www.bilibili.com.mkv':
    emit_event(DOWNLOAD_PREFIX, {{'state': 'sources', 'sources': {SOURCES!r}}})
    emit_event(DOWNLOAD_PREFIX, {{'state': 'sources', 'sources': {SOURCES!r}}})
if sys.argv[1] == '歌曲 P2.mkv' and os.environ['MUSIC_AGENT_ATTEMPT'] == '1':
    raise RuntimeError('P2 download failed')
print(sys.argv[1])
"""


def test_normal_download_entry_expands_queue_and_retry_preserves_completed_parts(tmp_path):
    jobs = make_jobs(tmp_path, queue_program())
    payload = {"url": VIDEO_URL, "cookie": "session=private", "request_id": "parts"}
    try:
        identity = jobs.start_download(payload)
        job = wait_for_job(jobs, identity)
        assert job["state"] == "failed"
        assert [item["state"] for item in job["batch"]] == ["succeeded", "failed", "succeeded"]
        assert [item["media"] for item in job["batch"]] == [source["name"] for source in SOURCES]
        assert len({item["source_path"] for item in job["batch"]}) == len(SOURCES)
        assert len({item["outdir"] for item in job["batch"]}) == len(SOURCES)
        assert jobs.start_download(payload) == identity
        assert len(jobs.store.list("uploads")) == len(SOURCES)
        assert "session=private" not in json.dumps(job)
        jobs.retry(identity)
        retried = wait_for_job(jobs, identity)
        assert retried["state"] == "succeeded" and len(retried["batch"]) == len(SOURCES)
        assert retried["batch"][0]["started_at"] == job["batch"][0]["started_at"]
        for item in jobs.store.get("jobs", identity)["batch"]:
            config = json.loads(Path(item["download_config"]).read_text())
            assert config["cookie"] == payload["cookie"]
        jobs.delete(identity)
        assert not jobs.store.list("uploads")
    finally:
        jobs.close()


def test_discovered_first_part_downloads_exact_address_and_keeps_cache(tmp_path, monkeypatch):
    store = DocumentStore(tmp_path / "workspace.sqlite3")
    upload = register_download(tmp_path, store, url=VIDEO_URL, cookie="", resolve_parts=True)
    config = json.loads(Path(upload["download_config"]).read_text())
    metadata, _ = metadata_factory(playlist())
    actual, downloader = metadata_factory({"title": "歌曲 P1"})
    destination = Path(config["folder"]) / "source.mkv"

    def extract(url, *, download):
        assert url == SOURCES[0]["url"] and download
        destination.write_bytes(b"part-one")
        return {"title": "歌曲 P1"}

    downloader.extract_info.side_effect = extract
    events = []
    monkeypatch.setattr("segment.workspace_download.emit_event", lambda prefix, event: events.append(event))
    factory = Mock(side_effect=[metadata.return_value, actual.return_value])
    assert download_source(config, factory=factory, store=store) == destination
    assert factory.call_args_list[1].args[0]["noplaylist"] is True
    assert next(event for event in events if event["state"] == "sources")["sources"] == SOURCES
    saved = json.loads(Path(upload["download_config"]).read_text())
    assert download_source(saved, factory=Mock(side_effect=AssertionError("redownload")), store=store) == destination
    assert store.get("uploads", upload["id"])["remote_url"] == VIDEO_URL


@pytest.mark.parametrize(
    "url",
    [
        "https://bilibili.com.evil.test/x",
        "https://example.com/video",
        "https://live.bilibili.com/123",
        "https://www.bilibili.com/bangumi/play/ep123",
    ],
)
def test_unrelated_hosts_do_not_trigger_bilibili_discovery(url):
    assert not is_bilibili_video(url)
