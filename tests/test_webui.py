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
