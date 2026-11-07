import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from workspace_support import make_jobs, wait_for_job

from segment.workspace_download import main
from segment.workspace_parts import discover_parts
from segment.workspace_process import command_for

VIDEO_URL = "https://www.bilibili.com/video/BVexample"
SOURCES = [
    {"url": VIDEO_URL + "?p=1", "name": "原视频 · P1.mkv"},
    {"url": VIDEO_URL + "?p=2", "name": "原视频 · P2.mkv"},
]


def save_existing_result(item):
    directory = Path(item["outdir"])
    clip = directory / "song.mp4"
    clip.write_bytes(b"existing-clip")
    manifest = directory / "source_music_agent.json"
    manifest.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "singing_intervals": [
                            {
                                "clip_id": "existing-song",
                                "file": str(clip),
                                "title": "原有歌曲",
                                "start_seconds": 1,
                                "end_seconds": 5,
                            }
                        ]
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest, clip


@pytest.mark.parametrize("interrupt_discovery", [False, True])
def test_legacy_p1_completion_preserves_clips_and_only_discovers_first_item(tmp_path, interrupt_discovery):
    jobs = make_jobs(tmp_path)
    try:
        identity = jobs.start_download({"url": VIDEO_URL, "request_id": "old"})
        old = wait_for_job(jobs, identity)
        assert old["can_complete_parts"]
        item = jobs.store.get("jobs", identity)["batch"][0]
        config_path = Path(item["download_config"])
        config = json.loads(config_path.read_text())
        config_path.write_text(json.dumps({key: value for key, value in config.items() if key != "resolve_parts"}))
        manifest, clip = save_existing_result(item)
        original_bytes = manifest.read_bytes()
        calls = []

        def run(job, current, **services):
            calls.append((current["id"], current.get("discover_only", False)))
            if current.get("discover_only"):
                assert "--discover-only" in command_for(current)
                services["report"]("download", {"state": "sources", "sources": SOURCES})
                if interrupt_discovery and job["attempt"] == 2:
                    return 1
            else:
                assert current["id"] != item["id"]
            return 0

        jobs.execution.runner = Mock(run=run)
        jobs.retry(identity)
        result = wait_for_job(jobs, identity)
        if interrupt_discovery:
            assert result["state"] == "failed"
            jobs.retry(identity)
            result = wait_for_job(jobs, identity)
        assert result["state"] == "succeeded" and len(result["batch"]) == len(SOURCES)
        assert not result["can_complete_parts"]
        assert all(discovery for media_id, discovery in calls if media_id == item["id"])
        assert manifest.read_bytes() == original_bytes and clip.read_bytes() == b"existing-clip"
        assert result["clips"][0]["id"] == "existing-song"
        assert result["clips"][0]["media_id"] == item["id"]
        assert len(jobs.store.list("uploads")) == len(SOURCES)
    finally:
        jobs.close()


def test_discovery_only_cli_never_downloads_or_starts_analysis(tmp_path, monkeypatch):
    config = tmp_path / "download.json"
    config.write_text(json.dumps({"url": VIDEO_URL, "cookie": "", "folder": str(tmp_path)}))
    monkeypatch.setattr(
        "sys.argv",
        ["download", "--source-config", str(config), "--outdir", str(tmp_path), "--discover-only"],
    )
    resolve = Mock()
    monkeypatch.setattr("segment.workspace_download._resolve", resolve)
    monkeypatch.setattr("segment.workspace_download.download_source", Mock(side_effect=AssertionError("download")))
    monkeypatch.setattr("segment.music_agent.cli.main", Mock(side_effect=AssertionError("analysis")))
    main()
    assert resolve.call_args.args[0]["resolve_parts"] is True


def test_real_bilibili_extractor_playlist_flows_into_part_discovery(tmp_path, monkeypatch):
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.bilibili import BiliBiliIE

    state = {"videoData": {"bvid": "BVexample", "title": "原视频"}}
    webpage = "<script>window.__INITIAL_STATE__=" + json.dumps(state) + ";</script>"
    monkeypatch.setattr(
        BiliBiliIE, "_download_webpage_handle", lambda self, url, *args, **kwargs: (webpage, SimpleNamespace(url=url))
    )
    monkeypatch.setattr(
        BiliBiliIE,
        "_download_json",
        lambda self, *args, **kwargs: {"data": [{"page": 1, "part": "第一 P"}, {"page": 2, "part": "第二 P"}]},
    )
    config = {"url": VIDEO_URL, "cookie": "", "folder": str(tmp_path)}
    assert discover_parts(config, factory=YoutubeDL, configure_cookies=lambda *args: None) == SOURCES


def test_explicit_part_success_does_not_offer_completion(tmp_path):
    jobs = make_jobs(tmp_path)
    try:
        identity = jobs.start_download({"url": VIDEO_URL + "?p=2", "request_id": "selected"})
        job = wait_for_job(jobs, identity)
        assert not job["can_complete_parts"]
        with pytest.raises(ValueError, match="不能续跑"):
            jobs.retry(identity)
    finally:
        jobs.close()
