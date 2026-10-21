import json
import sys
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from event_capture import capture_events
from test_webui import wait_for, wait_for_job

from segment.music_agent.storage import S3Storage
from segment.upload_progress import UPLOAD_PREFIX, UploadReporter
from segment.webui_jobs import Jobs


@pytest.mark.parametrize("failure", [False, True])
def test_upload_reports_real_callbacks(tmp_path, monkeypatch, failure):
    capture = capture_events(monkeypatch, tmp_path)
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
    events = [json.loads(line.removeprefix(UPLOAD_PREFIX)) for line in capture.lines()]
    assert events[0]["state"] == "uploading"
    assert events[0]["total_bytes"] == 6
    assert events[-1]["state"] == ("failed" if failure else "completed")
    assert events[-1]["transferred_bytes"] == (2 if failure else 6)


def test_callbacks_are_thread_safe(monkeypatch, tmp_path):
    capture = capture_events(monkeypatch, tmp_path)
    progress = UploadReporter("scan.wav", 100)
    with ThreadPoolExecutor() as pool:
        list(pool.map(progress, [1] * 100))
    events = [json.loads(line.removeprefix(UPLOAD_PREFIX)) for line in capture.lines()]
    assert events[-1]["transferred_bytes"] == 100


def test_upload_progress_crosses_process_pipe(tmp_path):
    event = {"key": "scan.wav", "total_bytes": 100, "transferred_bytes": 40, "state": "failed"}
    line = (UPLOAD_PREFIX + json.dumps(event) + "\n").encode()
    code = f"import os; os.write(int(os.environ['MUSIC_AGENT_EVENTS_FD']), {line!r}); print('normal log')"
    jobs = Jobs(lambda _: [sys.executable, "-c", code])
    try:
        job_id = jobs.start({"media": "scan.wav", "outdir": str(tmp_path)})
        result = wait_for_job(jobs, job_id)
        uploads = wait_for(lambda: jobs.status(job_id)["upload"]["uploads"])
        assert uploads == [event]
        assert UPLOAD_PREFIX not in result["log"]
    finally:
        jobs.close()
