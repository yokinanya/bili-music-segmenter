import io
from unittest.mock import Mock

import pytest
from workspace_support import add_upload, make_jobs, start, wait_for_job

from segment.music_agent.runtime import Runtime
from segment.workspace_options import default_options
from segment.workspace_records import reduce_event


def test_streaming_digest_same_names_and_aborted_upload(tmp_path):
    jobs = make_jobs(tmp_path)
    try:
        first = add_upload(jobs, "同名.mp4", b"first")
        second = add_upload(jobs, "同名.mp4", b"second")
        assert first["id"] != second["id"] and first["sha256"] != second["sha256"]
        source = jobs.uploads.register({"name": "中断.mp4", "size_bytes": 6})
        with pytest.raises(ValueError, match="提前结束"):
            jobs.uploads.receive(source["id"], io.BytesIO(b"bad"), 6)
        assert jobs.store.get("uploads", source["id"])["state"] == "failed"
        assert not jobs.uploads.path(source["id"]).with_suffix(".part").exists()
        assert jobs.uploads.receive(source["id"], io.BytesIO(b"123456"), 6)["state"] == "ready"
    finally:
        jobs.close()


def test_persistence_restart_and_shared_source_cleanup(tmp_path):
    jobs = make_jobs(tmp_path)
    source = add_upload(jobs)
    first = start(jobs, [source["id"]])
    wait_for_job(jobs, first)
    second = start(jobs, [source["id"]])
    wait_for_job(jobs, second)
    jobs.close()
    restarted = make_jobs(tmp_path)
    try:
        assert restarted.status(first)["state"] == "succeeded"
        restarted.delete(first)
        assert restarted.uploads.path(source["id"]).exists()
        restarted.delete(second)
        assert restarted.store.list("uploads") == []
    finally:
        restarted.close()


def test_restart_marks_unfinished_tasks_and_steps_interrupted(tmp_path):
    jobs = make_jobs(tmp_path)
    identity = start(jobs)
    wait_for_job(jobs, identity)
    jobs.close()
    jobs.store.update(
        "jobs",
        identity,
        lambda job: {
            **job,
            "state": "running",
            "batch": [{**job["batch"][0], "state": "running", "steps": [{"id": "one", "state": "waiting"}]}],
        },
    )
    restarted = make_jobs(tmp_path)
    try:
        job = restarted.status(identity)
        assert job["state"] == "interrupted" and job["batch"][0]["steps"][0]["state"] == "interrupted"
        restarted.retry(identity)
        assert wait_for_job(restarted, identity)["state"] == "succeeded"
    finally:
        restarted.close()


def test_cleanup_error_is_retryable(tmp_path):
    cleanup = Mock(side_effect=RuntimeError("permission denied"))
    jobs = make_jobs(tmp_path, cleanup=cleanup)
    try:
        identity = start(jobs)
        wait_for_job(jobs, identity)
        with pytest.raises(RuntimeError, match="permission"):
            jobs.delete(identity)
        result = jobs.status(identity)
        assert result["state"] == "cleanup_pending" and "permission" in result["cleanup_error"]
        cleanup.side_effect = None
        jobs.delete(identity)
        assert jobs.store.list("jobs") == []
    finally:
        jobs.close()


def runtime(tmp_path, *, report=None, attempt=1):
    return Runtime(
        {
            "checkpoint_dir": str(tmp_path / "checkpoints"),
            "source_digest": "media-digest",
            "attempt": attempt,
            "options": default_options(),
            "owner": "job-one",
            "state_dir": str(tmp_path),
        },
        report=report or (lambda *args: None),
    )


def test_checkpoints_validate_inputs_and_recover_success(tmp_path):
    events = []
    current = runtime(tmp_path, report=lambda prefix, event: events.append(event))
    work = Mock(return_value={"confirmed": True})
    spec = {"id": "scan/1", "label": "第一块", "input": [1, 2]}
    assert current.run(spec, work) == {"confirmed": True}
    resumed = runtime(tmp_path, report=lambda prefix, event: events.append(event), attempt=2)
    resumed.run(spec, work)
    assert work.call_count == 1 and events[-1]["state"] == "reused"
    resumed.run({**spec, "input": [1, 3]}, work)
    assert work.call_count == 2
    with pytest.raises(ValueError):
        resumed.run({"id": "invalid", "label": "校验失败"}, Mock(side_effect=ValueError("bad model")))
    assert resumed.run({"id": "invalid", "label": "校验失败"}, lambda: "valid") == "valid"


def test_out_of_order_progress_and_stale_attempt_ignored(tmp_path):
    jobs = make_jobs(tmp_path)
    try:
        identity = start(jobs)
        job = wait_for_job(jobs, identity)
        event = {"id": "scan", "attempt": 1, "sequence": 5, "state": "running"}
        current = reduce_event(job, 0, kind="progress", event=event, attempt=1)
        assert reduce_event(current, 0, kind="progress", event={**event, "sequence": 4}, attempt=1) == current
        assert reduce_event(current, 0, kind="progress", event=event, attempt=2) == current
    finally:
        jobs.close()
