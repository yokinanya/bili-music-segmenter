"""Checkpoint reuse must not depend on the Windows ANSI code page."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from segment.music_agent.runtime import Runtime
from segment.workspace_options import default_options


@pytest.mark.parametrize("asynchronous", [False, True])
def test_chinese_checkpoints_reused_under_gbk_locale(tmp_path, monkeypatch, asynchronous):
    read_text = Path.read_text

    def windows_read(path, encoding=None, errors=None):
        return read_text(path, encoding=encoding or "gbk", errors=errors)

    monkeypatch.setattr(Path, "read_text", windows_read)
    configuration = {
        "checkpoint_dir": str(tmp_path / "checkpoints"),
        "source_digest": "digest",
        "attempt": 1,
        "options": default_options(),
        "owner": "test-job",
        "state_dir": str(tmp_path),
    }
    events = []
    value = {"title": "中文歌曲与演唱边界", "rationale": "完整保留前奏"}
    work = AsyncMock(return_value=value) if asynchronous else Mock(return_value=value)
    spec = {"id": "scan", "label": "扫描", "input": [1, 2]}

    def execute(attempt):
        runtime = Runtime({**configuration, "attempt": attempt}, report=lambda prefix, event: events.append(event))
        if asynchronous:
            return asyncio.run(runtime.async_run(spec, work))
        return runtime.run(spec, work)

    assert execute(1) == value
    assert execute(2) == value
    assert work.call_count == 1
    assert events[-1]["state"] == "reused"
