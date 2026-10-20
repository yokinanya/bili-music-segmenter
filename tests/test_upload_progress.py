import json
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from test_webui import wait_for_job

from segment.music_agent.storage import S3Storage
from segment.upload_progress import UPLOAD_PREFIX, UploadReporter
from segment.webui_jobs import Jobs


@pytest.mark.parametrize("failure", [False, True])
def test_upload_reports_real_callbacks(tmp_path, monkeypatch, capsys, failure):
    monkeypatch.setenv("MUSIC_AGENT_USAGE_EVENTS", "1")
    source = tmp_path / "audio.wav"
    source.write_bytes(b"123456")

    def upload(*args, **kwargs):
        kwargs["Callback"](2)
        if failure:
            raise RuntimeError("upload failed")
        kwargs["Callback"](4)

    storage = S3Storage(Mock(upload_file=upload), "audio")
    if failure:
        with pytest.raises(RuntimeError, match="upload failed"):
            storage.upload("scan.wav", source)
    else:
        storage.upload("scan.wav", source)
    events = [json.loads(line.removeprefix(UPLOAD_PREFIX)) for line in capsys.readouterr().out.splitlines()]
    assert events[0]["state"] == "uploading"
    assert events[0]["total_bytes"] == 6
    assert events[-1]["state"] == ("failed" if failure else "completed")
    assert events[-1]["transferred_bytes"] == (2 if failure else 6)


def test_callbacks_are_thread_safe(monkeypatch, capsys):
    monkeypatch.setenv("MUSIC_AGENT_USAGE_EVENTS", "1")
    progress = UploadReporter("scan.wav", 100)
    with ThreadPoolExecutor() as pool:
        list(pool.map(progress, [1] * 100))
    events = [json.loads(line.removeprefix(UPLOAD_PREFIX)) for line in capsys.readouterr().out.splitlines()]
    assert events[-1]["transferred_bytes"] == 100


def test_upload_progress_crosses_process_pipe(tmp_path):
    event = {"key": "scan.wav", "total_bytes": 100, "transferred_bytes": 40, "state": "failed"}
    code = f"print({(UPLOAD_PREFIX + json.dumps(event))!r})"
    jobs = Jobs(lambda _: [sys.executable, "-c", code])
    try:
        job_id = jobs.start({"outdir": str(tmp_path)})
        result = wait_for_job(jobs, job_id)
        assert result["upload"]["uploads"] == [event]
        assert UPLOAD_PREFIX not in result["log"]
    finally:
        jobs.close()
