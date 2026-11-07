import io
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from segment.music_agent import media_process


def process(*, returncode=0, errors=""):
    child = Mock()
    child.stdout = io.StringIO("out_time_us=500000\nprogress=continue\nout_time_us=1000000\nprogress=end\n")
    child.stderr = io.StringIO(errors)
    child.wait.return_value = returncode
    child.__enter__ = Mock(return_value=child)
    child.__exit__ = Mock(return_value=False)
    return child


def test_manual_export_uses_automatic_threads_and_real_measured_progress(monkeypatch):
    popen = Mock(return_value=process())
    monkeypatch.setattr(media_process.subprocess, "Popen", popen)
    updates = []
    with media_process.reporting_media(updates.append):
        media_process.execute_media(["ffmpeg", "-c:v", "libx264", "clip.mp4"], 1)
    invocation = popen.call_args.args[0]
    assert [invocation[index + 1] for index, value in enumerate(invocation) if value == "-threads"] == ["0", "0"]
    assert updates[0]["completed_seconds"] == 0.5 and updates[0]["total_seconds"] == 1
    assert updates[0]["stage"] == "encoding"
    assert media_process.MEDIA_PROGRESS.get() is None


def test_task_exports_keep_the_existing_resource_and_thread_budget(monkeypatch):
    budget = Mock()
    budget.__enter__ = Mock()
    budget.__exit__ = Mock(return_value=False)
    runtime = SimpleNamespace(config={"media_threads": 3}, resource=Mock(return_value=budget), event=Mock())
    popen = Mock(return_value=process())
    monkeypatch.setattr(media_process.subprocess, "Popen", popen)
    token = media_process.CURRENT.set(SimpleNamespace(runtime=runtime))
    try:
        media_process.execute_media(["ffmpeg", "-c:v", "libx264", "clip.mp4"], 1)
    finally:
        media_process.CURRENT.reset(token)
    invocation = popen.call_args.args[0]
    assert [invocation[index + 1] for index, value in enumerate(invocation) if value == "-threads"] == ["3", "3"]
    runtime.resource.assert_called_once_with("media")
    assert runtime.event.call_args.kwargs["state"] == "succeeded"


def test_failed_encoding_surfaces_stderr_and_resets_progress_scope(monkeypatch):
    monkeypatch.setattr(
        media_process.subprocess, "Popen", Mock(return_value=process(returncode=1, errors="codec failed"))
    )
    with pytest.raises(subprocess.CalledProcessError) as failure:
        with media_process.reporting_media(lambda event: None):
            media_process.execute_media(["ffmpeg", "clip.mp4"], 1)
    assert failure.value.stderr == "codec failed"
    assert media_process.MEDIA_PROGRESS.get() is None
