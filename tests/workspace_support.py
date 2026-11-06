import io
import os
import sys
import time
from pathlib import Path
from uuid import uuid4

import pytest

from segment.webui import create_jobs
from segment.workspace_process import ProcessRunner

TEST_TIMEOUT = 5
POLL_INTERVAL = 0.02
TESTS_DIR = str(Path(__file__).resolve().parent)


def child_code(source: str) -> str:
    """Run ``source`` in a child that can import the event helpers from tests/."""
    return f"import sys; sys.path.insert(0, {TESTS_DIR!r}); {source}"


class _HelperPathRunner(ProcessRunner):
    """Let spawned children import tests/ so they can send events the way production code does."""

    def run(self, *args, **kwargs):
        previous = os.environ.get("PYTHONPATH")
        os.environ["PYTHONPATH"] = os.pathsep.join(filter(None, (previous, TESTS_DIR)))
        try:
            return super().run(*args, **kwargs)
        finally:
            if previous is None:
                os.environ.pop("PYTHONPATH", None)
            else:
                os.environ["PYTHONPATH"] = previous


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
    runner = _HelperPathRunner(lambda item: [sys.executable, "-u", "-c", code, item["media"]])
    return create_jobs(root, runner=runner, cleanup=cleanup or (lambda owner: None))


def add_upload(jobs, name="直播.mp4", data=b"media"):
    source = jobs.uploads.register({"name": name, "size_bytes": len(data)})
    return jobs.uploads.receive(source["id"], io.BytesIO(data), len(data))


def start(jobs, ids=None, *, options=None, request_id=None):
    ids = ids or [add_upload(jobs)["id"]]
    return jobs.start({"upload_ids": ids, "options": options or {}, "request_id": request_id or uuid4().hex})
