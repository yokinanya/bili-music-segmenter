import json
from http.client import HTTPConnection
from pathlib import Path
from threading import Event, Thread
from urllib.parse import quote

from test_result_review import result as result_fixture
from test_webui import TOKEN, request
from test_webui import jobs as jobs_fixture
from test_webui import server as server_fixture
from workspace_support import start, wait_for_job

from segment.music_agent.media_process import MEDIA_PROGRESS

jobs = jobs_fixture
server = server_fixture
result = result_fixture
STREAM_HEADERS = {"Accept": "application/x-ndjson"}


def test_metadata_only_skips_source_probe_and_transcoding(server, jobs, result):
    identity, clip, _ = result
    source = Path(jobs.status(identity)["batch"][0]["source_path"])
    source.unlink()
    jobs.result_services["duration"].side_effect = AssertionError("metadata must not probe source")
    revised = jobs.edit_clip(
        identity,
        clip["id"],
        {
            "title": "新歌名",
            "artist": "新歌手",
            "start_seconds": 1.0,
            "end_seconds": 5.0,
        },
    )
    assert revised["id"] == clip["id"] and revised["path"] == clip["path"]
    assert revised["name"] == "新歌名.mp4" and revised["artist"] == "新歌手"
    assert Path(revised["path"]).read_bytes() == b"original"
    jobs.result_services["export"].assert_not_called()
    jobs.result_services["duration"].assert_not_called()
    status, data, headers = request(server, "GET", f"/api/jobs/{identity}/clip/{clip['id']}?download=1")
    assert status == 200 and data == b"original" and quote("新歌名.mp4") in headers["Content-Disposition"]


def test_unchanged_values_do_not_rewrite_manifest_or_probe(jobs, result):
    identity, clip, manifest = result
    before = manifest.read_bytes(), jobs.store.get("jobs", identity)
    assert jobs.edit_clip(identity, clip["id"], {"title": clip["title"]}) == clip
    assert before == (manifest.read_bytes(), jobs.store.get("jobs", identity))
    jobs.result_services["export"].assert_not_called()
    jobs.result_services["duration"].assert_not_called()


def test_http_progress_arrives_during_export_and_other_jobs_remain_usable(server, jobs, result):
    identity, clip, _ = result
    other_id = start(jobs)
    other_item = wait_for_job(jobs, other_id)["batch"][0]
    other_manifest = Path(other_item["outdir"]) / "other_music_agent.json"
    other_manifest.write_text('{"candidates": []}')
    entered, release = Event(), Event()

    def export(source, start, end, destination):
        progress = MEDIA_PROGRESS.get()
        progress({"stage": "encoding", "completed_seconds": 1, "total_seconds": end - start})
        entered.set()
        assert release.wait(5), "export test release timed out"
        destination.write_bytes(b"revision")

    jobs.result_services["export"] = export
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    connection.request(
        "PUT",
        f"/api/jobs/{identity}/clip/{clip['id']}",
        body=json.dumps({"start_seconds": 2}),
        headers={**STREAM_HEADERS, "X-WebUI-Token": TOKEN},
    )
    response = connection.getresponse()
    try:
        assert response.status == 200 and response.getheader("Content-Type") == "application/x-ndjson"
        assert json.loads(response.readline())["stage"] == "preparing"
        event = json.loads(response.readline())
        assert event["stage"] == "encoding" and event["completed_seconds"] == 1
        assert entered.wait(5)
        route = f"/api/jobs/{other_id}/manifest/{other_item['id']}"
        assert request(server, "GET", route)[0] == 200
        assert request(server, "GET", f"/api/jobs/{identity}")[0] == 200
    finally:
        release.set()
    events = [json.loads(line) for line in response.read().splitlines()]
    connection.close()
    assert [event["stage"] for event in events] == ["saving", "succeeded"]
    assert events[-1]["clip"]["start_seconds"] == 2


def test_streamed_failures_are_explicit_and_original_is_preserved(server, jobs, result):
    identity, clip, manifest = result
    original = manifest.read_bytes()
    jobs.result_services["export"].side_effect = RuntimeError("编码失败详情")
    status, body, _ = request(
        server, "PUT", f"/api/jobs/{identity}/clip/{clip['id']}", data={"start_seconds": 2}, headers=STREAM_HEADERS
    )
    events = [json.loads(line) for line in body.splitlines()]
    assert status == 200
    assert events[-1]["stage"] == "failed" and "编码失败详情" in events[-1]["error"]
    assert not any(event["stage"] == "succeeded" for event in events)
    assert manifest.read_bytes() == original and Path(clip["path"]).read_bytes() == b"original"
    assert not list(manifest.parent.glob("revision_*.mp4"))


def test_metadata_stream_has_saving_and_completion_without_encoding(server, jobs, result):
    identity, clip, _ = result
    status, body, _ = request(
        server, "PUT", f"/api/jobs/{identity}/clip/{clip['id']}", data={"title": "仅改名字"}, headers=STREAM_HEADERS
    )
    events = [json.loads(line) for line in body.splitlines()]
    assert status == 200 and [event["stage"] for event in events] == ["preparing", "saving", "succeeded"]
    assert events[1]["total_seconds"] is None and events[1]["completed_seconds"] == 0
    jobs.result_services["export"].assert_not_called()


def test_edits_of_the_same_job_do_not_lose_either_revision(jobs, result):
    identity, clip, _ = result
    entered, release = Event(), Event()
    results, errors = [], []

    def export(source, start, end, destination):
        entered.set()
        assert release.wait(5)
        destination.write_bytes(b"revision")

    def edit(payload):
        try:
            results.append(jobs.edit_clip(identity, clip["id"], payload))
        except Exception as error:
            errors.append(error)

    jobs.result_services["export"] = export
    first = Thread(target=lambda: edit({"start_seconds": 2}))
    second = Thread(target=lambda: edit({"title": "随后修改的歌名"}))
    first.start()
    try:
        assert entered.wait(5)
        second.start()
    finally:
        release.set()
        first.join(timeout=5)
        if second.ident is not None:
            second.join(timeout=5)
    assert not errors and len(results) == 2
    revised = jobs.status(identity)["clips"][0]
    assert revised["start_seconds"] == 2 and revised["title"] == "随后修改的歌名"
