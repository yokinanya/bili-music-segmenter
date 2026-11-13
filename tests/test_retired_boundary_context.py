"""边界精修移除后，边界上下文参数不得再出现在任务参数中。"""

from __future__ import annotations

import os
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


def test_retired_internal_tuning_defaults() -> None:
    options = default_options()
    assert options["chunk_seconds"] == 1200 and options["chunk_context_seconds"] == 30
    for name in ("candidate_concurrency", "model_concurrency", "media_concurrency"):
        assert name not in options


def test_webui_exposes_only_task_decisions() -> None:
    root = Path(__file__).resolve().parents[1] / "webui" / "src"
    parameters = (root / "components" / "Parameters.tsx").read_text(encoding="utf-8")
    names = set(re.findall(r"name: '(\w+)'", parameters)) | set(re.findall(r"\['(\w+)', '", parameters))
    assert names == {
        "minimum_confidence",
        "minimum_singing_seconds",
        "minimum_candidate_seconds",
        "recognizer_timeout",
    }


def test_runtime_budgets_are_fixed() -> None:
    from segment.music_agent.runtime import FIXED_BUDGETS

    assert FIXED_BUDGETS == {"model": 3, "recognizer": 3, "media": min(2, os.cpu_count() or 1)}
