import json
import sys
import time
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import quote

import pytest

from segment.webui import Handler
from segment.webui_jobs import JobLimitReached, Jobs, build_batch, build_command, list_inputs

TEST_TIMEOUT = 5
POLL_INTERVAL = 0.02
TOKEN = "test-token"


def make_input(tmp_path, monkeypatch, name):
    """Create one media file inside a temporary input directory and point the WebUI at it."""
    directory = tmp_path / "input"
    directory.mkdir(exist_ok=True)
    media = directory / name
    media.touch()
    monkeypatch.setattr("segment.webui_jobs.input_root", tmp_path)
    monkeypatch.setattr("segment.webui_jobs.CONTAINER_INPUT_DIR", tmp_path / "absent")
    return media


def test_build_command_only_accepts_files_in_input_dir(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / "input").mkdir(parents=True)
    (project / "input" / "直播 视频.mp4").touch()
    monkeypatch.setattr("segment.webui_jobs.input_root", project)
    monkeypatch.setattr("segment.webui_jobs.CONTAINER_INPUT_DIR", tmp_path / "absent")

    command = build_command({"media": "直播 视频.mp4", "outdir": "output"})
    assert command[:4] == [sys.executable, "-u", "-m", "segment.music_agent.cli"]
    assert str((project / "input" / "直播 视频.mp4").resolve()) in command
    assert "--skip-netease" not in command


@pytest.mark.parametrize(
    "media",
    [
        "",
        "absent.mp4",
        "../video.mp4",
        "sub/video.mp4",
        "other.mp4",
        "/etc/passwd",
        "./video.mp4",
        "..",
    ],
)
def test_media_must_be_a_bare_name_inside_input(tmp_path, monkeypatch, media):
    project = tmp_path / "project"
    (project / "input").mkdir(parents=True)
    (project / "input" / "video.mp4").touch()
    (tmp_path / "other.mp4").touch()
    monkeypatch.setattr("segment.webui_jobs.input_root", project)
    monkeypatch.setattr("segment.webui_jobs.CONTAINER_INPUT_DIR", tmp_path / "absent")
    with pytest.raises(ValueError):
        build_command({"media": media, "outdir": str(tmp_path / "out")})


def test_container_input_dir_wins(tmp_path, monkeypatch):
    container = tmp_path / "input"
    container.mkdir()
    (container / "a.mp4").touch()
    monkeypatch.setattr("segment.webui_jobs.CONTAINER_INPUT_DIR", container)
    assert list_inputs() == [{"name": "a.mp4", "size_bytes": 0}]


def test_list_inputs_filters_and_sorts(tmp_path, monkeypatch):
    directory = tmp_path / "input"
    directory.mkdir()
    for name in ("b.mp4", "A.mkv", "notes.txt", "cover.jpg", "c.MP3"):
        (directory / name).write_bytes(b"x")
    monkeypatch.setattr("segment.webui_jobs.input_root", tmp_path)
    monkeypatch.setattr("segment.webui_jobs.CONTAINER_INPUT_DIR", tmp_path / "absent")
    assert [item["name"] for item in list_inputs()] == ["A.mkv", "b.mp4", "c.MP3"]


def test_batch_runs_one_command_per_selected_file(tmp_path, monkeypatch):
    directory = tmp_path / "input"
    directory.mkdir()
    for name in ("a.mp4", "b.mp4"):
        (directory / name).touch()
    monkeypatch.setattr("segment.webui_jobs.input_root", tmp_path)
    monkeypatch.setattr("segment.webui_jobs.CONTAINER_INPUT_DIR", tmp_path / "absent")
    commands = build_batch({"media": ["b.mp4", "a.mp4"], "outdir": str(tmp_path / "out")})
    assert len(commands) == 2
    assert [command[command.index("--media") + 1] for command in commands] == [
        str((directory / "b.mp4").resolve()),
        str((directory / "a.mp4").resolve()),
    ]


@pytest.mark.parametrize("media", [[], ["a.mp4", "a.mp4"], "a.mp4", None])
def test_batch_rejects_empty_duplicate_and_non_list(tmp_path, monkeypatch, media):
    directory = tmp_path / "input"
    directory.mkdir()
    (directory / "a.mp4").touch()
    monkeypatch.setattr("segment.webui_jobs.input_root", tmp_path)
    monkeypatch.setattr("segment.webui_jobs.CONTAINER_INPUT_DIR", tmp_path / "absent")
    if media == "a.mp4":
        assert len(build_batch({"media": media, "outdir": str(tmp_path / "out")})) == 1
        return
    with pytest.raises(ValueError):
        build_batch({"media": media, "outdir": str(tmp_path / "out")})


def test_unsupported_suffix_is_rejected(tmp_path, monkeypatch):
    directory = tmp_path / "input"
    directory.mkdir()
    (directory / "notes.txt").touch()
    monkeypatch.setattr("segment.webui_jobs.input_root", tmp_path)
    monkeypatch.setattr("segment.webui_jobs.CONTAINER_INPUT_DIR", tmp_path / "absent")
    with pytest.raises(ValueError, match="不支持的媒体格式"):
        build_command({"media": "notes.txt", "outdir": str(tmp_path / "out")})


@pytest.mark.parametrize(
    "extra",
    [
        {"minimum_confidence": 0},
        {"minimum_confidence": 1.1},
        {"minimum_singing_seconds": True},
        {"boundary_context": 1.5},
        {"skip_shazam": "yes"},
        {"unknown": 1},
        {"netease_endpoint": "file:///tmp"},
    ],
)
def test_invalid_options(tmp_path, monkeypatch, extra):
    media = make_input(tmp_path, monkeypatch, "video.mp4")
    with pytest.raises(ValueError):
        build_command({"media": media.name, "outdir": str(tmp_path), **extra})


def test_rejects_output_path_that_is_a_file(tmp_path, monkeypatch):
    media = make_input(tmp_path, monkeypatch, "video.mp4")
    outdir = tmp_path / "occupied"
    outdir.touch()
    with pytest.raises(ValueError, match="必须是目录"):
        build_command({"media": media.name, "outdir": str(outdir)})


def test_missing_input(tmp_path, monkeypatch):
    directory = tmp_path / "input"
    directory.mkdir()
    monkeypatch.setattr("segment.webui_jobs.input_root", tmp_path)
    monkeypatch.setattr("segment.webui_jobs.CONTAINER_INPUT_DIR", tmp_path / "absent")
    with pytest.raises(ValueError, match="输入目录中没有该文件"):
        build_command({"media": "missing.mp4", "outdir": str(tmp_path)})


def post_json(host, port, *, body=None, headers=None):
    """Send one POST on a fresh connection, mirroring how the browser issues each fetch."""
    connection = HTTPConnection(host, port, timeout=TEST_TIMEOUT)
    connection.request("POST", "/api/jobs", body=body, headers=headers or {})
    return _Response(connection, connection.getresponse())


class _Response:
    def __init__(self, connection, response):
        self.connection = connection
        self.status = response.status
        self._response = response

    def read(self):
        try:
            return self._response.read()
        finally:
            self.connection.close()


def wait_for_job(jobs, job_id):
    deadline = time.monotonic() + TEST_TIMEOUT
    while time.monotonic() < deadline:
        result = jobs.status(job_id)
        if result["state"] != "running":
            return result
        time.sleep(POLL_INTERVAL)
    pytest.fail("任务未在测试期限内结束")


def wait_for(predicate, message="条件未在测试期限内满足"):
    """Poll until the worker threads have finished collecting events from a completed job."""
    deadline = time.monotonic() + TEST_TIMEOUT
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(POLL_INTERVAL)
    pytest.fail(message)


def wait_for_returncode(jobs, job_id):
    """The exit code becomes visible a moment after a batch item finishes; poll for it."""
    deadline = time.monotonic() + TEST_TIMEOUT
    while time.monotonic() < deadline:
        result = wait_for_job(jobs, job_id)
        if result["returncode"] is not None:
            return result
        time.sleep(POLL_INTERVAL)
    pytest.fail("任务退出码未在测试期限内出现")


def fake_command(code):
    """A command builder that still declares a media name, so Jobs can label batch items."""
    return lambda payload: [sys.executable, "-c", code, payload["media"]]


@pytest.mark.parametrize("exitcode", [0, 7])
def test_jobs_capture_real_process_output(tmp_path, monkeypatch, exitcode, isolated_log_dir):
    make_input(tmp_path, monkeypatch, "video.mp4")
    jobs = Jobs(fake_command(f"print('中文日志'); raise SystemExit({exitcode})"))
    try:
        job_id = jobs.start({"media": "video.mp4", "outdir": str(tmp_path)})
        result = wait_for_returncode(jobs, job_id)
        assert result["returncode"] == exitcode
        assert result["state"] == ("succeeded" if exitcode == 0 else "failed")
        assert "中文日志" in result["log"]
        assert result["log_complete"] is True
        assert result["clips"] == []
        assert result["outdir"] == str(tmp_path)
        log_dir = isolated_log_dir / "logs"
        assert Path(result["log_path"]).parent == log_dir
        assert list(log_dir.glob("webui-*.log"))
        assert not list(tmp_path.glob("webui-*.log"))
    finally:
        jobs.close()


def test_utf8_log_decoded_across_read_boundaries(tmp_path, monkeypatch):
    make_input(tmp_path, monkeypatch, "video.mp4")
    # Decode the raw byte stream instead of each line, so characters split across reads survive.
    code = (
        "import os, sys, time\n"
        "data = '中文日志\\n'.encode()\n"
        "for byte in data:\n"
        "    os.write(1, bytes([byte]))\n"
        "    time.sleep(0.02)\n"
    )
    jobs = Jobs(fake_command(code))
    try:
        job_id = jobs.start({"media": "video.mp4", "outdir": str(tmp_path)})
        result = wait_for_job(jobs, job_id)
        assert result["log"] == "中文日志\n"
    finally:
        jobs.close()


def test_grandchild_processes_do_not_hold_the_event_pipe(tmp_path, monkeypatch):
    make_input(tmp_path, monkeypatch, "video.mp4")
    # A helper process that inherited the event pipe must not keep the reader waiting after exit.
    code = (
        "import subprocess, sys\n"
        "subprocess.run([sys.executable, '-c', 'pass'])\n"
        "print('done', flush=True)\n"
        "raise SystemExit(3)\n"
    )
    jobs = Jobs(fake_command(code), max_jobs=1)
    try:
        job_id = jobs.start({"media": "video.mp4", "outdir": str(tmp_path)})
        result = wait_for_returncode(jobs, job_id)
        assert result["returncode"] == 3
        assert result["state"] == "failed"
        assert result["log_complete"] is True
    finally:
        jobs.close()


def test_batch_processes_files_in_order_and_reports_each(tmp_path, monkeypatch):
    for name in ("a.mp4", "b.mp4"):
        make_input(tmp_path, monkeypatch, name)
    code = "import sys; print('media=' + sys.argv[1], flush=True)"
    jobs = Jobs(lambda payload: [[sys.executable, "-c", code, name] for name in payload["media"]])
    try:
        job_id = jobs.start({"media": ["a.mp4", "b.mp4"], "outdir": str(tmp_path)})
        result = wait_for(
            lambda: jobs.status(job_id)
            if jobs.status(job_id)["state"] != "running" and jobs.status(job_id)["batch_complete"]
            else None
        )
        assert result["state"] == "succeeded"
        assert [item["media"] for item in result["batch"]] == ["a.mp4", "b.mp4"]
        assert [item["state"] for item in result["batch"]] == ["succeeded", "succeeded"]
        assert "media=a" in result["log"] and "media=b" in result["log"]
        assert result["log"].index("media=a") < result["log"].index("media=b")
        assert len({item["log_path"] for item in result["batch"]}) == 2
    finally:
        jobs.close()


def test_batch_continues_after_a_failed_file(tmp_path, monkeypatch):
    for name in ("good.mp4", "bad.mp4"):
        make_input(tmp_path, monkeypatch, name)

    def builder(payload):
        return [[sys.executable, "-c", f"raise SystemExit({1 if 'bad' in name else 0})"] for name in payload["media"]]

    jobs = Jobs(builder)
    try:
        job_id = jobs.start({"media": ["good.mp4", "bad.mp4"], "outdir": str(tmp_path)})
        result = wait_for(
            lambda: jobs.status(job_id)
            if jobs.status(job_id)["state"] != "running" and jobs.status(job_id)["batch_complete"]
            else None
        )
        assert [item["state"] for item in result["batch"]] == ["succeeded", "failed"]
        assert result["state"] == "failed"
        assert result["returncode"] == 1
    finally:
        jobs.close()


def test_stop_cancels_the_remaining_files(tmp_path, monkeypatch):
    for name in ("first.mp4", "second.mp4"):
        make_input(tmp_path, monkeypatch, name)
    code = "import time; time.sleep(10)"
    jobs = Jobs(lambda payload: [[sys.executable, "-c", code] for _ in payload["media"]], max_jobs=1)
    try:
        job_id = jobs.start({"media": ["first.mp4", "second.mp4"], "outdir": str(tmp_path)})
        wait_for(lambda: jobs.status(job_id)["batch"][0]["state"] == "running")
        jobs.stop_current(job_id)
        result = wait_for(
            lambda: jobs.status(job_id)
            if jobs.status(job_id)["state"] != "running" and jobs.status(job_id)["batch_complete"]
            else None
        )
        # Stopping terminates the running file; the remaining files are skipped, not started.
        assert result["state"] == "cancelled"
        assert [item["state"] for item in result["batch"]] == ["cancelled", "cancelled"]
    finally:
        jobs.close()


def test_job_limit_rejects_extra_jobs(tmp_path, monkeypatch):
    make_input(tmp_path, monkeypatch, "video.mp4")
    code = "import time; print('start', flush=True); time.sleep(10)"
    jobs = Jobs(fake_command(code), max_jobs=1)
    try:
        jobs.start({"media": "video.mp4", "outdir": str(tmp_path)})
        with pytest.raises(JobLimitReached):
            jobs.start({"media": "video.mp4", "outdir": str(tmp_path)})
    finally:
        jobs.close()


def test_status_lists_exported_clips_from_manifest(tmp_path):
    clip = tmp_path / "clips" / "001_00-00-10_00-01-00_稻香_周杰伦.mp4"
    manifest = tmp_path / "live_music_agent.json"
    manifest.write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "singing_intervals": [
                            {
                                "start_seconds": 10,
                                "end_seconds": 70,
                                "file": str(clip),
                                "title": "稻香",
                                "artist": "周杰伦",
                            },
                            {"start_seconds": 80, "end_seconds": 90},
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    jobs = Jobs(lambda _: [sys.executable, "-c", "pass"])
    try:
        job_id = jobs.start({"outdir": str(tmp_path)})
        result = wait_for_job(jobs, job_id)
        assert result["clips"] == [
            {
                "name": clip.name,
                "path": str(clip),
                "title": "稻香",
                "artist": "周杰伦",
                "duration_seconds": 60.0,
            }
        ]
    finally:
        jobs.close()


@pytest.fixture
def server():
    jobs = Jobs(build_command)
    handler = partial(Handler, jobs=jobs, token=TOKEN)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=TEST_TIMEOUT)
    connection.host, connection.port = "127.0.0.1", server.server_port
    connection.jobs = jobs  # lets a test start a job on the same instance the server serves
    yield connection
    connection.close()
    server.shutdown()
    server.server_close()
    thread.join(timeout=TEST_TIMEOUT)
    jobs.close()


def test_frontend_bundle_is_served_without_the_token(server):
    # Browser tags cannot send the token header, so assets load openly but expose no data.
    server.request("GET", "/")
    response = server.getresponse()
    page = response.read().decode()
    assert response.status == 200
    assert "<html" in page.lower()
    assert TOKEN not in page


def test_missing_bundle_reports_a_build_hint(server, monkeypatch, tmp_path):
    monkeypatch.setattr("segment.webui.DIST_DIR", tmp_path / "absent")
    server.request("GET", "/")
    response = server.getresponse()
    assert response.status == 503
    assert "前端未构建" in json.loads(response.read())["error"]


def test_static_asset_cannot_escape_the_bundle(server):
    server.request("GET", "/../../segment/webui.py")
    response = server.getresponse()
    # Unknown paths fall back to the SPA entry point instead of leaking files outside the bundle.
    assert b"def " not in response.read()


def test_bootstrap_and_history_endpoints(server):
    server.request("GET", "/api/bootstrap", headers={"X-WebUI-Token": TOKEN})
    response = server.getresponse()
    data = json.loads(response.read())
    assert response.status == 200
    assert Path(data["output_dir"])
    assert "input_dir" in data
    server.request("GET", "/api/history", headers={"X-WebUI-Token": TOKEN})
    response = server.getresponse()
    assert response.status == 200
    assert json.loads(response.read()) == {"entries": []}


def test_http_page_and_errors(server):
    server.request("GET", "/api/usage", headers={"X-WebUI-Token": TOKEN})
    response = server.getresponse()
    assert response.status == 200
    assert json.loads(response.read())["calls"] == 0
    post = partial(post_json, server.host, server.port)
    response = post(body="{}", headers={"Content-Length": "2"})
    assert response.status == 403
    response.read()
    response = post(body="[]", headers={"X-WebUI-Token": TOKEN, "Content-Length": "2"})
    assert response.status == 400
    assert "JSON 对象" in json.loads(response.read())["error"]
    response = post(headers={"X-WebUI-Token": TOKEN, "Content-Length": "0"})
    assert response.status == 400
    assert "不能为空" in json.loads(response.read())["error"]
    # A zero-length or absent body must fail fast instead of blocking the handler thread.
    response = post(headers={"X-WebUI-Token": TOKEN})
    assert response.status == 400
    assert "请求体不能为空" in json.loads(response.read())["error"]
    server.request("GET", "/api/jobs/missing", headers={"X-WebUI-Token": TOKEN})
    response = server.getresponse()
    assert response.status == 404
    response.read()


def test_inputs_endpoint_lists_media_only(server, tmp_path, monkeypatch):
    directory = tmp_path / "input"
    directory.mkdir()
    (directory / "直播.mp4").write_bytes(b"12345")
    (directory / "readme.txt").write_text("ignored")
    monkeypatch.setattr("segment.webui_jobs.input_root", tmp_path)
    monkeypatch.setattr("segment.webui_jobs.CONTAINER_INPUT_DIR", tmp_path / "absent")
    monkeypatch.setattr("segment.webui.input_dir", lambda: directory)
    server.request("GET", "/api/inputs", headers={"X-WebUI-Token": TOKEN})
    response = server.getresponse()
    data = json.loads(response.read())
    assert response.status == 200
    assert [item["name"] for item in data["files"]] == ["直播.mp4"]
    assert data["files"][0]["size_bytes"] == 5


def test_log_endpoint_returns_only_the_tail(server, tmp_path, monkeypatch):
    make_input(tmp_path, monkeypatch, "video.mp4")
    jobs = server.jobs
    code = "print('第一行', flush=True); print('第二行', flush=True)"
    jobs._command_builder = lambda payload: [sys.executable, "-c", code]
    job_id = jobs.start({"media": ["video.mp4"], "outdir": str(tmp_path)})
    wait_for_returncode(jobs, job_id)
    server.request("GET", f"/api/jobs/{job_id}/log", headers={"X-WebUI-Token": TOKEN, "X-Log-Offset": "0"})
    response = server.getresponse()
    first = json.loads(response.read())
    assert "第一行" in first["text"] and "第二行" in first["text"]
    server.request(
        "GET",
        f"/api/jobs/{job_id}/log",
        headers={"X-WebUI-Token": TOKEN, "X-Log-Offset": str(first["offset"])},
    )
    response = server.getresponse()
    assert json.loads(response.read())["text"] == ""
    server.request("GET", f"/api/jobs/{job_id}/log", headers={"X-WebUI-Token": TOKEN, "X-Log-Item": "9"})
    response = server.getresponse()
    assert response.status == 400
    response.read()


def test_clip_endpoint_supports_range_requests(server, tmp_path, monkeypatch):
    make_input(tmp_path, monkeypatch, "video.mp4")
    clips = tmp_path / "clips"
    clips.mkdir()
    clip = clips / "001_00-00-01_00-00-05_稻香.mp4"
    clip.write_bytes(b"0123456789")
    (tmp_path / "video_music_agent.json").write_text(
        json.dumps(
            {
                "candidates": [
                    {
                        "singing_intervals": [
                            {"start_seconds": 1, "end_seconds": 5, "file": str(clip), "title": "稻香", "artist": ""}
                        ]
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    jobs = server.jobs
    code = "pass"
    jobs._command_builder = lambda payload: [sys.executable, "-c", code]
    job_id = jobs.start({"media": ["video.mp4"], "outdir": str(tmp_path)})
    wait_for_returncode(jobs, job_id)
    path = f"/api/jobs/{job_id}/clip/{quote(clip.name)}"
    server.request("GET", path, headers={"X-WebUI-Token": TOKEN, "Range": "bytes=2-5"})
    response = server.getresponse()
    assert response.status == 206
    assert response.read() == b"2345"
    assert response.getheader("Content-Range") == "bytes 2-5/10"
    server.request("GET", path, headers={"X-WebUI-Token": TOKEN, "Range": "bytes=99-200"})
    response = server.getresponse()
    assert response.status == 416
    response.read()
    server.request("GET", f"{path}?token={TOKEN}&download=1")
    response = server.getresponse()
    attachment = response.getheader("Content-Disposition")
    response.read()
    assert attachment and "attachment" in attachment
    assert quote(clip.name) in attachment
    server.request("GET", f"/api/jobs/{job_id}/clip/{quote('missing.mp4')}", headers={"X-WebUI-Token": TOKEN})
    response = server.getresponse()
    assert response.status == 404
    response.read()


def test_rejects_foreign_host(server):
    server.request("GET", "/", headers={"Host": "foreign.example"})
    response = server.getresponse()
    assert response.status == 403
    response.read()
