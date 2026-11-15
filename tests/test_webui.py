import io
import json
import zipfile
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread

import pytest
from workspace_support import add_upload, make_jobs, start, wait_for, wait_for_job

from segment.webui import Handler

TOKEN = "workspace-test-token"


@pytest.fixture
def jobs(tmp_path):
    value = make_jobs(tmp_path)
    yield value
    value.close()


@pytest.fixture
def server(jobs):
    instance = ThreadingHTTPServer(("127.0.0.1", 0), partial(Handler, jobs=jobs, token=TOKEN))
    thread = Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.shutdown()
    instance.server_close()
    thread.join(timeout=5)


def request(server, method, path, *, data=None, raw=None, headers=None):
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    body = json.dumps(data).encode() if data is not None else raw
    connection.request(method, path, body=body, headers={"X-WebUI-Token": TOKEN, **(headers or {})})
    response = connection.getresponse()
    content = response.read()
    result = response.status, content, dict(response.getheaders())
    connection.close()
    return result


def test_static_bootstrap_and_auth(server):
    status, body, _ = request(server, "GET", "/")
    assert status == 200 and b"<html" in body and TOKEN.encode() not in body
    status, body, _ = request(server, "GET", "/api/bootstrap")
    assert status == 200
    data = json.loads(body)
    assert data["version"] == 3 and data["defaults"]["chunk_seconds"] == 1200
    assert "input_dir" not in data
    assert request(server, "GET", "/api/uploads", headers={"X-WebUI-Token": "wrong"})[0] == 403
    assert request(server, "GET", "/api/bootstrap?token=" + TOKEN, headers={"X-WebUI-Token": ""})[0] == 403
    assert request(server, "GET", "/", headers={"Host": "foreign.example"})[0] == 403
    assert b"def " not in request(server, "GET", "/../../segment/webui.py")[1]


def test_browser_upload_and_idempotent_job(server, jobs):
    status, body, _ = request(server, "POST", "/api/uploads", data={"name": "视频.mp4", "size_bytes": 5})
    assert status == 201
    source = json.loads(body)
    assert request(server, "PUT", "/api/uploads/" + source["id"], raw=b"12345")[0] == 200
    payload = {"upload_ids": [source["id"]], "options": {}, "request_id": "one-click"}
    first = request(server, "POST", "/api/jobs", data=payload)
    second = request(server, "POST", "/api/jobs", data=payload)
    assert json.loads(first[1]) == json.loads(second[1])
    identity = json.loads(first[1])["id"]
    assert wait_for_job(jobs, identity)["state"] == "succeeded"
    assert request(server, "PUT", "/api/uploads/" + source["id"], raw=b"54321")[0] == 400
    assert request(server, "POST", "/api/jobs", data={**payload, "options": {"scan_concurrency": 1}})[0] == 400
    assert request(server, "GET", "/api/inputs")[0] == 404


def test_http_input_errors(server):
    assert request(server, "POST", "/api/jobs", data=[])[0] == 400
    assert request(server, "POST", "/api/jobs", data={"media": "video.mp4", "outdir": "/tmp"})[0] == 400
    assert request(server, "POST", "/api/jobs", raw=b"")[0] == 400
    assert request(server, "POST", "/api/uploads", data={"name": "test.txt", "size_bytes": 3})[0] == 400
    assert request(server, "GET", "/api/jobs/missing")[0] == 404


def test_project_api_saves_and_serves_source_range(server, jobs):
    source = add_upload(jobs, data=b"0123456789")
    jobs.result_services["duration"] = lambda path: 120
    status, body, _ = request(server, "POST", "/api/projects", data={"upload_id": source["id"]})
    assert status == 201
    project = json.loads(body)
    path = "/api/projects/" + project["id"]
    clip = {"id": "song", "start_seconds": 10, "end_seconds": 20, "title": "Song", "artist": "", "name": "Song.mp4"}
    status, body, _ = request(server, "PUT", path, data={"revision": 0, "clips": [clip]})
    assert status == 200 and json.loads(body)["revision"] == 1
    status, body, headers = request(
        server, "GET", path + "/source?token=" + TOKEN, headers={"X-WebUI-Token": "", "Range": "bytes=2-5"}
    )
    assert status == 206 and body == b"2345"
    assert headers["Content-Range"] == "bytes 2-5/10"
    assert request(server, "GET", path + "/source", headers={"X-WebUI-Token": ""})[0] == 403


def test_project_export_list_restores_completed_and_running_tasks(server, jobs):
    source = add_upload(jobs)
    jobs.result_services["duration"] = lambda path: 120
    project = json.loads(request(server, "POST", "/api/projects", data={"upload_id": source["id"]})[1])
    jobs.store.put("editor_exports", {"id": "done", "project_id": project["id"], "state": "succeeded"})
    jobs.store.put("editor_exports", {"id": "other", "project_id": "elsewhere", "state": "succeeded"})
    status, body, _ = request(server, "GET", f"/api/projects/{project['id']}/exports")
    assert status == 200
    assert [task["id"] for task in json.loads(body)["tasks"]] == ["done"]


def test_flv_preview_reads_original_ranges_without_creating_a_proxy(server, jobs):
    source = add_upload(jobs, name="live.flv", data=b"FLV-original-video")
    jobs.result_services["duration"] = lambda path: 120
    project = json.loads(request(server, "POST", "/api/projects", data={"upload_id": source["id"]})[1])
    path = "/api/projects/" + project["id"]
    status, body, headers = request(
        server, "GET", path + "/source?token=" + TOKEN,
        headers={"X-WebUI-Token": "", "Range": "bytes=4-11"},
    )
    assert status == 206 and body == b"original"
    assert headers["Content-Type"] == "video/x-flv"
    assert headers["Content-Range"] == "bytes 4-11/18"
    assert request(server, "POST", path + "/preview", data={})[0] == 404
    assert request(server, "GET", path + "/preview-progress")[0] == 404
    assert not list((jobs.root / "editor-cache").glob("preview-*"))


@pytest.mark.parametrize("refresh", [None, False, True])
def test_analysis_refresh_option_reaches_worker_runtime(server, jobs, tmp_path, monkeypatch, refresh):
    from segment.music_agent.runtime import create_runtime
    from segment.workspace_process import child_environment

    source = add_upload(jobs)
    jobs.result_services["duration"] = lambda path: 120
    project = json.loads(request(server, "POST", "/api/projects", data={"upload_id": source["id"]})[1])
    payload = {} if refresh is None else {"refresh": refresh}
    status, body, _ = request(server, "POST", f"/api/projects/{project['id']}/analyze", data=payload)
    assert status == 201
    job = jobs.store.get("jobs", json.loads(body)["id"])
    assert job["refresh_recognition"] is bool(refresh)
    environment = child_environment(job, job["batch"][0], event_fd=1, state_dir=tmp_path)
    monkeypatch.setenv("MUSIC_AGENT_REFRESH_RECOGNITION", environment["MUSIC_AGENT_REFRESH_RECOGNITION"])
    worker = create_runtime(Path(job["batch"][0]["source_path"]), tmp_path / "runtime", job["options"])
    assert worker.config["refresh_recognition"] is bool(refresh)


def test_project_starts_analysis_without_automatic_export(server, jobs):
    source = add_upload(jobs)
    jobs.result_services["duration"] = lambda path: 120
    project = json.loads(request(server, "POST", "/api/projects", data={"upload_id": source["id"]})[1])
    path = "/api/projects/" + project["id"]
    status, body, _ = request(server, "POST", path + "/analyze", data={"options": {}})
    assert status == 201
    identity = json.loads(body)["id"]
    assert jobs.store.get("jobs", identity)["analysis_only"] is True
    assert jobs.store.get("jobs", identity)["project_id"] == project["id"]


def test_project_export_endpoint_downloads_snapshot(server, jobs):
    source = add_upload(jobs)
    jobs.result_services["duration"] = lambda path: 120
    jobs.editor_exports.services["export"] = lambda src, start, end, dest: dest.write_bytes(b"exported-video")
    project = json.loads(request(server, "POST", "/api/projects", data={"upload_id": source["id"]})[1])
    path = "/api/projects/" + project["id"]
    clip = {"id": "song", "start_seconds": 1, "end_seconds": 10, "title": "Song", "artist": "", "name": "Song.mp4"}
    request(server, "PUT", path, data={"revision": 0, "clips": [clip]})
    status, body, _ = request(server, "POST", path + "/exports", data={"revision": 1, "clip_ids": ["song"]})
    assert status == 201
    task = json.loads(body)
    export_path = path + "/exports/" + task["id"]
    wait_for(lambda: jobs.store.get("editor_exports", task["id"])["state"] == "succeeded")
    assert (
        request(server, "GET", export_path + "/clip/song?token=" + TOKEN, headers={"X-WebUI-Token": ""})[1]
        == b"exported-video"
    )
    assert request(server, "GET", export_path + "/archive?token=" + TOKEN, headers={"X-WebUI-Token": ""})[0] == 200


def test_logs_clips_range_and_archive(server, jobs):
    identity = start(jobs)
    job = wait_for_job(jobs, identity)
    item = job["batch"][0]
    Path(item["log_path"]).write_text("第一行\n第二行\n", encoding="utf-8")
    folder = Path(item["outdir"])
    clip = folder / "稻香.mp4"
    clip.write_bytes(b"0123456789")
    manifest = {
        "candidates": [
            {
                "singing_intervals": [
                    {"start_seconds": 1, "end_seconds": 5, "file": str(clip), "title": "稻香", "artist": ""}
                ]
            }
        ]
    }
    (folder / "source_music_agent.json").write_text(json.dumps(manifest), encoding="utf-8")
    chunk = json.loads(request(server, "GET", f"/api/jobs/{identity}/log")[1])
    assert chunk["text"] == "第一行\n第二行\n"
    assert (
        json.loads(
            request(server, "GET", f"/api/jobs/{identity}/log", headers={"X-Log-Offset": str(chunk["offset"])})[1]
        )["text"]
        == ""
    )
    result = jobs.status(identity)["clips"][0]
    path = f"/api/jobs/{identity}/clip/{result['id']}"
    status, body, headers = request(server, "GET", path, headers={"Range": "bytes=2-5"})
    assert status == 206 and body == b"2345" and headers["Content-Range"] == "bytes 2-5/10"
    assert request(server, "GET", path, headers={"Range": "bytes=99-100"})[0] == 416
    status, _, headers = request(server, "GET", path + f"?token={TOKEN}&download=1", headers={"X-WebUI-Token": ""})
    assert status == 200 and "attachment" in headers["Content-Disposition"]
    status, archive, _ = request(server, "GET", f"/api/jobs/{identity}/archive")
    assert status == 200
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        assert len(zipped.namelist()) == 2
        assert any(name.endswith(".json") for name in zipped.namelist())


def test_real_process_logs_and_stop(tmp_path):
    jobs = make_jobs(tmp_path, "import time; print('中文日志', flush=True); time.sleep(10)")
    try:
        ids = [add_upload(jobs, name)["id"] for name in ("第一.mp4", "第二.mp4")]
        identity = start(jobs, ids)
        wait_for(lambda: jobs.status(identity)["batch"][0]["state"] == "running")
        wait_for(lambda: Path(jobs.status(identity)["batch"][0]["log_path"]).exists())
        jobs.stop_current(identity)
        result = wait_for_job(jobs, identity)
        assert result["state"] == "cancelled"
        assert [item["state"] for item in result["batch"]] == ["cancelled", "cancelled"]
    finally:
        jobs.close()


def test_order_failure_continuation_and_resume(tmp_path):
    code = "import sys; print(sys.argv[1]); raise SystemExit(1 if '坏' in sys.argv[1] else 0)"
    jobs = make_jobs(tmp_path, code)
    try:
        ids = [add_upload(jobs, name)["id"] for name in ("好.mp4", "坏.mp4")]
        identity = start(jobs, ids)
        first = wait_for_job(jobs, identity)
        assert [item["state"] for item in first["batch"]] == ["succeeded", "failed"]
        jobs.execution.runner.command = lambda item: [__import__("sys").executable, "-c", "print('retry')"]
        jobs.retry(identity)
        second = wait_for_job(jobs, identity)
        assert second["state"] == "succeeded" and second["attempt"] == 2
        assert len(second["attempts"]) == 2
        assert jobs.log_chunk(identity, 0, 0)["text"].count("好.mp4") == 1
    finally:
        jobs.close()


def test_clear_history_removes_records_and_keeps_usage_totals(server, jobs):
    source = add_upload(jobs)
    identity = start(jobs, [source["id"]])
    wait_for_job(jobs, identity)
    jobs.store.update(
        "jobs",
        identity,
        lambda job: {
            **job,
            "usage_events": [
                {
                    "model": "gemini-3.8-flash",
                    "usage": {"total_input_tokens": 10, "total_output_tokens": 2},
                    "attempt": 1,
                    "media_id": "m",
                    "at": "2026-01-01T00:00:00+08:00",
                }
            ],
        },
    )
    before = jobs.usage.snapshot()
    status, body, _ = request(server, "POST", "/api/history/clear", data={})
    assert status == 200 and json.loads(body) == {"removedJobs": 1, "removedLegacy": 0}
    assert jobs.store.list("jobs") == []
    assert jobs.history() == []
    assert jobs.usage.snapshot() == before


def test_project_delete_removes_source_and_project(server, jobs):
    source = add_upload(jobs)
    jobs.result_services["duration"] = lambda path: 120
    project = json.loads(request(server, "POST", "/api/projects", data={"upload_id": source["id"]})[1])
    path = "/api/projects/" + project["id"]
    assert request(server, "DELETE", path)[0] == 200
    assert jobs.store.list("projects") == []
    assert request(server, "GET", path)[0] == 404
    assert all(value["id"] != source["id"] for value in jobs.store.list("uploads"))
