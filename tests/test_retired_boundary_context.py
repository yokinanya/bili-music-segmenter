"""边界精修移除后，边界上下文参数不得再出现在任务参数中。"""

from __future__ import annotations

import re
from pathlib import Path

from segment.workspace_options import RETIRED_OPTIONS, default_options


def test_boundary_context_is_retired() -> None:
    assert "boundary_context_seconds" in RETIRED_OPTIONS
    assert "boundary_context_seconds" not in default_options()


def test_webui_exposes_only_current_options() -> None:
    root = Path(__file__).resolve().parents[1] / "webui" / "src"
    types = (root / "lib" / "types.ts").read_text(encoding="utf-8")
    block = re.search(r"interface RunOptions \{(.*?)\n\}", types, re.S)
    assert block is not None
    names = set(re.findall(r"(\w+):", block.group(1)))
    assert names == set(default_options())


def test_child_environment_passes_recognizer_timeout() -> None:
    from segment.workspace_process import child_environment

    job = {"id": "job", "attempt": 1, "options": {"recognizer_timeout": 90, "boundary_context_seconds": 20}}
    item = {"sha256": "digest", "source_path": "a.mp4", "outdir": "out"}
    env = child_environment(job, item, event_fd=3, state_dir=Path("state"))
    assert env["MUSIC_AGENT_RECOGNIZER_TIMEOUT"] == "90"
    assert "MUSIC_AGENT_BOUNDARY_CONTEXT" not in env
