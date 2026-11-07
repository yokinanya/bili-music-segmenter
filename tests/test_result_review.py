import json
import shutil
import subprocess
from pathlib import Path
from threading import Event, Thread
from unittest.mock import Mock

import pytest
from test_webui import TOKEN, request
from test_webui import jobs as jobs_fixture
from test_webui import server as server_fixture
from workspace_support import start, wait_for_job

from segment.workspace_downloads import register_download

jobs = jobs_fixture
server = server_fixture


@pytest.fixture
def result(jobs):
    identity = start(jobs)
    job = wait_for_job(jobs, identity)
    item = job["batch"][0]
    folder = Path(item["outdir"])
    path = folder / "song.mp4"
    path.write_bytes(b"original")
    document = {
        "media": item["source_path"],
        "duration_seconds": 10,
        "candidates": [
            {
                "singing_intervals": [
                    {
                        "start_seconds": 1,
                        "end_seconds": 5,
                        "file": str(path),
                        "title": "Song",
                        "artist": "Singer",
                        "recognition": {"shazam": {"status": "matched"}},
                    }
                ]
            }
        ],
    }
    manifest = folder / "source_music_agent.json"
    manifest.write_text(json.dumps(document), encoding="utf-8")
    jobs.result_services["duration"] = Mock(return_value=10)
    jobs.result_services["export"] = Mock(side_effect=lambda source, start, end, dest: dest.write_bytes(b"revision"))
    return identity, jobs.status(identity)["clips"][0], manifest


def test_metadata_and_manifest_transport(server, jobs, result):
    identity, clip, manifest = result
    assert clip["start_seconds"] == clip["original_start_seconds"] == 1
    assert clip["end_seconds"] == clip["original_end_seconds"] == 5
    assert clip["source_duration_seconds"] == 10 and clip["source_name"] == "直播.mp4"
    assert clip["recognition"]["shazam"]["status"] == "matched"
    item = jobs.status(identity)["batch"][0]
    assert item["source_type"] == "upload" and item["can_reuse"] is True
    route = f"/api/jobs/{identity}/manifest/{item['id']}"
    status, body, _ = request(server, "GET", route)
    assert status == 200 and json.loads(body) == json.loads(manifest.read_text(encoding="utf-8"))
    status, _, headers = request(server, "GET", route + f"?download=1&token={TOKEN}", headers={"X-WebUI-Token": ""})
    assert status == 200 and "attachment" in headers["Content-Disposition"]
    assert request(server, "GET", route, headers={"X-WebUI-Token": "invalid"})[0] == 403


def test_edit_persists_stable_id_evidence_and_original_bounds(server, jobs, result):
    identity, clip, manifest = result
    route = f"/api/jobs/{identity}/clip/{clip['id']}"
    status, body, _ = request(
        server, "PUT", route, data={"title": "新标题", "artist": "新歌手", "start_seconds": 2, "end_seconds": 6}
    )
    revised = json.loads(body)["clip"]
    assert status == 200 and revised["id"] == clip["id"]
    assert revised["title"] == "新标题" and revised["artist"] == "新歌手"
    assert revised["duration_seconds"] == 4 and revised["start_seconds"] == 2
    assert revised["original_start_seconds"] == 1 and revised["original_end_seconds"] == 5
    assert revised["recognition"] == clip["recognition"]
    assert Path(clip["path"]).read_bytes() == b"original"
    assert jobs.store.get("jobs", identity)["clips"] == [revised]
    record = json.loads(manifest.read_text(encoding="utf-8"))["candidates"][0]["singing_intervals"][0]
    assert record["title"] == "新标题" and record["clip_id"] == clip["id"]
    assert request(server, "GET", route)[1] == b"revision"
    second = jobs.edit_clip(identity, clip["id"], {"title": "Again"})
    assert second["original_start_seconds"] == 1 and second["start_seconds"] == 2


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"start_seconds": -1},
        {"end_seconds": 11},
        {"end_seconds": 1},
        {"start_seconds": True},
        {"start_seconds": float("nan")},
        {"title": 4},
        {"file": "escape.mp4"},
        {"artist": "bad\x00name"},
        {"end_seconds": float("inf")},
    ],
)
def test_invalid_edits_do_not_export(jobs, result, payload):
    identity, clip, _ = result
    with pytest.raises(ValueError):
        jobs.edit_clip(identity, clip["id"], payload)
    jobs.result_services["export"].assert_not_called()


def test_active_and_missing_source_are_explicit_errors(jobs, result):
    identity, clip, _ = result
    jobs.store.update("jobs", identity, lambda job: {**job, "state": "running"})
    with pytest.raises(ValueError, match="运行中"):
        jobs.edit_clip(identity, clip["id"], {"title": "edit", "start_seconds": 2})
    jobs.store.update("jobs", identity, lambda job: {**job, "state": "succeeded"})
    Path(jobs.status(identity)["batch"][0]["source_path"]).unlink()
    assert jobs.status(identity)["batch"][0]["can_reuse"] is False
    with pytest.raises(FileNotFoundError, match="源文件"):
        jobs.edit_clip(identity, clip["id"], {"title": "edit", "start_seconds": 2})


def test_failed_export_preserves_manifest_clip_and_job(jobs, result):
    identity, clip, manifest = result
    before = manifest.read_bytes(), jobs.store.get("jobs", identity)

    def failed(source, start, end, destination):
        destination.write_bytes(b"broken")
        raise RuntimeError("ffmpeg failed")

    jobs.result_services["export"] = failed
    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        jobs.edit_clip(identity, clip["id"], {"title": "edit", "start_seconds": 2})
    assert (manifest.read_bytes(), jobs.store.get("jobs", identity)) == before
    assert Path(clip["path"]).read_bytes() == b"original"
    assert not list(manifest.parent.glob("revision_*.mp4"))


@pytest.mark.parametrize("operation", ["retry", "delete"])
def test_edit_serializes_retry_and_delete(jobs, result, operation):
    identity, clip, _ = result
    entered, release, attempted, completed = Event(), Event(), Event(), Event()
    errors = []
    jobs.store.update("jobs", identity, lambda job: {**job, "state": "failed"})

    def export(source, start, end, destination):
        entered.set()
        assert release.wait(5), "edit test release timed out"
        destination.write_bytes(b"revision")

    def edit():
        try:
            jobs.edit_clip(identity, clip["id"], {"title": "edit", "start_seconds": 2})
        except Exception as error:
            errors.append(error)

    def competing_operation():
        attempted.set()
        try:
            getattr(jobs, operation)(identity)
        except Exception as error:
            errors.append(error)
        finally:
            completed.set()

    jobs.result_services["export"] = export
    editor = Thread(target=edit)
    competitor = Thread(target=competing_operation)
    editor.start()
    try:
        assert entered.wait(5)
        competitor.start()
        assert attempted.wait(5)
        assert not completed.wait(0.1)
    finally:
        release.set()
        editor.join(timeout=5)
        if competitor.ident is not None:
            competitor.join(timeout=5)
    assert not editor.is_alive() and not competitor.is_alive() and not errors
    if operation == "retry":
        assert wait_for_job(jobs, identity)["clips"][0]["title"] == "edit"
    else:
        with pytest.raises(KeyError):
            jobs.status(identity)


def test_failed_persistence_rolls_back_manifest_and_revision(jobs, result):
    identity, clip, manifest = result
    before = json.loads(manifest.read_text(encoding="utf-8"))
    jobs.result_services["save"] = Mock(side_effect=RuntimeError("database failed"))
    with pytest.raises(RuntimeError, match="database failed"):
        jobs.edit_clip(identity, clip["id"], {"title": "edit", "start_seconds": 2})
    assert json.loads(manifest.read_text(encoding="utf-8")) == before
    assert Path(clip["path"]).read_bytes() == b"original"
    assert not list(manifest.parent.glob("revision_*.mp4"))


def test_http_edit_errors_are_visible(server, jobs, result):
    identity, clip, _ = result
    route = f"/api/jobs/{identity}/clip/{clip['id']}"
    assert request(server, "PUT", route, data={"end_seconds": 99})[0] == 400
    assert request(server, "PUT", f"/api/jobs/{identity}/clip/missing", data={"title": "edit"})[0] == 404
    jobs.result_services["export"] = Mock(side_effect=RuntimeError("ffmpeg failed"))
    status, body, _ = request(server, "PUT", route, data={"title": "edit", "start_seconds": 2})
    assert status == 500 and "ffmpeg failed" in json.loads(body)["error"]


def test_rejects_source_path_escape(jobs, result):
    identity, clip, _ = result
    jobs.store.update(
        "jobs",
        identity,
        lambda job: {**job, "batch": [{**job["batch"][0], "source_path": str(jobs.root / "outside.mp4")}]},
    )
    with pytest.raises(ValueError, match="超出"):
        jobs.edit_clip(identity, clip["id"], {"title": "edit", "start_seconds": 2})
    jobs.result_services["export"].assert_not_called()


def test_rejects_manifest_and_clip_path_escape(jobs, result):
    identity, clip, manifest = result
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["candidates"][0]["singing_intervals"][0]["file"] = str(manifest.parent.parent / "outside.mp4")
    manifest.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="超出"):
        jobs.status(identity)
    with pytest.raises(ValueError, match="超出"):
        jobs.edit_clip(identity, clip["id"], {"title": "edit", "start_seconds": 2})


def test_download_public_metadata_and_reuse(server, jobs):
    upload = register_download(jobs.root, jobs.store, url="https://example.test/video", cookie="secret")
    source = Path(upload["source_path"])
    source.write_bytes(b"downloaded")
    jobs.store.put("uploads", {**jobs.store.get("uploads", upload["id"]), "state": "ready", "name": "Title.mkv"})
    identity = start(jobs, [upload["id"]])
    wait_for_job(jobs, identity)
    status, body, _ = request(server, "GET", f"/api/jobs/{identity}")
    assert status == 200
    item = json.loads(body)["batch"][0]
    assert item["source_type"] == "download" and item["source_url"] == "https://example.test/video"
    assert item["can_reuse"] is True and "download_config" not in item
    assert "download_config" not in jobs.store.get("jobs", identity)["batch"][0]
    assert b"download_config" not in request(server, "GET", "/api/uploads")[1]
    internal = jobs.store.get("jobs", identity)
    jobs.store.put(
        "jobs", {**internal, "batch": [{**internal["batch"][0], "download_config": upload["download_config"]}]}
    )
    public_body = request(server, "GET", f"/api/jobs/{identity}")[1]
    assert b"download_config" not in public_body and b"secret" not in public_body
    Path(upload["source_path"]).unlink()
    assert jobs.status(identity)["batch"][0]["can_reuse"] is False


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="ffmpeg/ffprobe required")
def test_real_ffmpeg_reexport(jobs, result):
    from segment.music_agent.export import export_video
    from segment.music_agent.media import media_duration

    identity, clip, _ = result
    source = Path(jobs.status(identity)["batch"][0]["source_path"])
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:r=10",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440",
            "-t",
            "2",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        timeout=15,
    )
    jobs.result_services.update({"export": export_video, "duration": media_duration})
    updates = []
    revised = jobs.edit_clip(
        identity, clip["id"], {"start_seconds": 0.25, "end_seconds": 1.25}, progress=updates.append
    )
    assert any(event["stage"] == "encoding" and event["total_seconds"] == 1 for event in updates)
    assert 0.9 <= media_duration(Path(revised["path"])) <= 1.2
    assert Path(clip["path"]).read_bytes() == b"original"
