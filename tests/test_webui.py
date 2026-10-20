import json
import re
import sys
import time
from functools import partial
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from threading import Thread

import pytest

from segment.webui import Handler
from segment.webui_jobs import Jobs, build_command

TEST_TIMEOUT = 5
POLL_INTERVAL = 0.02
TOKEN = "test-token"


def test_build_command_validates_and_preserves_paths(tmp_path):
    media = tmp_path / "直播 视频.mp4"
    media.touch()
    command = build_command(
        {
            "media": str(media),
            "outdir": str(tmp_path / "output"),
        }
    )
    assert command[:4] == [sys.executable, "-u", "-m", "segment.music_agent.cli"]
    assert str(media) in command
    assert "--skip-netease" not in command


@pytest.mark.parametrize(
    "extra",
    [
        {"minimum_confidence": 0},
        {"minimum_confidence": 1.1},
        {"merge_gap": -1},
        {"merge_gap": float("nan")},
        {"minimum_singing_seconds": True},
        {"boundary_context": 1.5},
        {"skip_shazam": "yes"},
        {"unknown": 1},
        {"netease_endpoint": "file:///tmp"},
    ],
)
def test_invalid_options(tmp_path, extra):
    media = tmp_path / "video.mp4"
    media.touch()
    with pytest.raises(ValueError):
        build_command({"media": str(media), "outdir": str(tmp_path), **extra})


def test_missing_input(tmp_path):
    with pytest.raises(ValueError, match="输入文件不存在"):
        build_command({"media": str(tmp_path / "missing"), "outdir": str(tmp_path)})


def wait_for_job(jobs, job_id):
    deadline = time.monotonic() + TEST_TIMEOUT
    while time.monotonic() < deadline:
        result = jobs.status(job_id)
        if result["state"] != "running":
            return result
        time.sleep(POLL_INTERVAL)
    pytest.fail("任务未在测试期限内结束")


@pytest.mark.parametrize("exitcode", [0, 7])
def test_jobs_capture_real_process_output(tmp_path, exitcode):
    jobs = Jobs(lambda _: [sys.executable, "-c", f"print('中文日志'); raise SystemExit({exitcode})"])
    try:
        job_id = jobs.start({"outdir": str(tmp_path)})
        result = wait_for_job(jobs, job_id)
        assert result["returncode"] == exitcode
        assert result["state"] == ("succeeded" if exitcode == 0 else "failed")
        assert "中文日志" in result["log"]
        assert result["outdir"] == str(tmp_path)
        assert list(tmp_path.glob("webui-*.log"))
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
    yield connection
    connection.close()
    server.shutdown()
    server.server_close()
    thread.join(timeout=TEST_TIMEOUT)
    jobs.close()


def test_http_page_and_errors(server):
    server.request("GET", "/")
    response = server.getresponse()
    page = response.read().decode()
    assert response.status == 200
    assert "API 自动歌切" in page
    assert re.search("const token = 'test-token'", page)
    assert "__TOKEN__" not in page
    assert "高级设置" not in page
    assert "Token 用量与费用估算" in page
    server.request("GET", "/api/usage", headers={"X-WebUI-Token": TOKEN})
    response = server.getresponse()
    assert response.status == 200
    assert json.loads(response.read())["calls"] == 0
    server.request("POST", "/api/jobs", body="{}")
    response = server.getresponse()
    assert response.status == 403
    response.read()
    server.request("POST", "/api/jobs", body="[]", headers={"X-WebUI-Token": TOKEN})
    response = server.getresponse()
    assert response.status == 400
    assert "JSON 对象" in json.loads(response.read())["error"]
    server.request("GET", "/api/jobs/missing", headers={"X-WebUI-Token": TOKEN})
    response = server.getresponse()
    assert response.status == 404
    response.read()


def test_rejects_foreign_host(server):
    server.request("GET", "/", headers={"Host": "foreign.example"})
    response = server.getresponse()
    assert response.status == 403
    response.read()
