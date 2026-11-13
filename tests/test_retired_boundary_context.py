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

    # 识曲额度降低到 2：网易云上游对高并发敏感，一次请求失败会使整首歌无法识别。
    assert FIXED_BUDGETS == {
        "model": 3,
        "recognizer": 2,
        "netease": 1,
        "media": min(2, os.cpu_count() or 1),
    }


def test_netease_has_its_own_lower_budget() -> None:
    """网易云上游对并发敏感，且单次识别内部已串行采样四点，必须比 Shazam 额度低。"""
    from segment.music_agent.runtime import FIXED_BUDGETS

    assert FIXED_BUDGETS["netease"] == 1
    assert FIXED_BUDGETS["netease"] < FIXED_BUDGETS["recognizer"]


def test_netease_budget_limits_only_netease(monkeypatch) -> None:
    """网易云走专属额度，Shazam 仍用共享额度。"""
    import asyncio

    from segment.music_agent import recognition

    seen = []

    class Tracking(asyncio.Semaphore):
        def __init__(self, value, name):
            super().__init__(value)
            self.name = name

        async def __aenter__(self):
            seen.append(self.name)
            return await super().__aenter__()

    async def fake_shazam(audio, timeout):
        return {"status": "matched", "title": "歌", "artist": "人"}

    async def fake_netease(audio, timeout):
        return {"status": "matched", "title": "歌", "artist": "人"}

    async def run():
        return await recognition.recognize_audio(
            Path("a.mp3"),
            use_shazam=True,
            use_netease=True,
            budget=Tracking(3, "shared"),
            netease_budget=Tracking(1, "netease"),
        )

    monkeypatch.setattr(recognition, "_run_shazam", fake_shazam)

    async def to_thread(fn, *args):
        return fn(*args)

    monkeypatch.setattr(recognition.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(recognition, "netease_orig", lambda *a, **k: (["歌", "人"], {"name": "歌"}))
    result = asyncio.run(run())
    assert result["shazam"]["status"] == "matched" and result["netease"]["status"] == "matched"
    assert sorted(seen) == ["netease", "shared"]
