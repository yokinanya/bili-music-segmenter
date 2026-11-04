import io
import sys
import time
from uuid import uuid4

import pytest

from segment.webui import create_jobs
from segment.workspace_process import ProcessRunner

TEST_TIMEOUT = 5
POLL_INTERVAL = 0.02


def wait_for(predicate, message="条件未在测试期限内满足"):
    deadline = time.monotonic() + TEST_TIMEOUT
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(POLL_INTERVAL)
    pytest.fail(message)


def wait_for_job(jobs, identity):
    return wait_for(lambda: value if (value := jobs.status(identity))["state"] not in {"running", "queued"} else None)


def make_jobs(root, code="pass", *, cleanup=None):
    runner = ProcessRunner(lambda item: [sys.executable, "-u", "-c", code, item["media"]])
    return create_jobs(root, runner=runner, cleanup=cleanup or (lambda owner: None))


def add_upload(jobs, name="直播.mp4", data=b"media"):
    source = jobs.uploads.register({"name": name, "size_bytes": len(data)})
    return jobs.uploads.receive(source["id"], io.BytesIO(data), len(data))


def start(jobs, ids=None, *, options=None, request_id=None):
    ids = ids or [add_upload(jobs)["id"]]
    return jobs.start({"upload_ids": ids, "options": options or {}, "request_id": request_id or uuid4().hex})
