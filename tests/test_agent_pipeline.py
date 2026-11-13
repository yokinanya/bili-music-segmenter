"""端到端流水线：Gemini 出点位、自动识曲、切分导出。"""

import asyncio
import json
from types import SimpleNamespace

import pytest

from segment.music_agent import agent
from segment.music_agent.config import ApiConfig
from segment.music_agent.gemini import GeminiConfig
from segment.music_agent.scan_gemini import Candidate


def fake_config():
    return ApiConfig(GeminiConfig(api_key="test", proxy=None, base_url=None))


class StubGemini:
    """流水线只用模型出点位；任何额外的模型调用都应让测试失败。"""

    def __init__(self):
        self.calls = []

    def close(self):
        pass

    def audio_window(self, media, start, end, extract):
        return f"{media}#{start}-{end}"

    def json_call(self, audio, prompt, schema, *, model=None, label=""):
        self.calls.append({"audio": audio, "label": label, "model": model})
        raise AssertionError(f"未预期的模型调用：{label}")


@pytest.fixture
def pipeline(monkeypatch):
    stub = StubGemini()
    monkeypatch.setattr(agent, "load_config", fake_config)
    monkeypatch.setattr(agent, "GeminiClient", lambda *args, **kwargs: stub)
    monkeypatch.setattr(agent, "media_duration", lambda _: 300)
    monkeypatch.setattr(agent, "extract_recognition_audio", lambda *args: args[-1].write_bytes(b"audio"))
    return stub


def install_services(monkeypatch, candidates, recognize):
    monkeypatch.setattr(agent, "scan_candidates", lambda *args, **kwargs: (candidates, []))
    monkeypatch.setattr(agent, "recognize_audio", recognize)


def test_background_skip_and_successful_export(tmp_path, monkeypatch, pipeline):
    candidates = [
        Candidate(1, 0, 80, "background_music_chat", 0.99, False, "", "聊天"),
        Candidate(2, 100, 200, "host_singing", 0.9, True, "", "唱歌"),
    ]
    calls = []

    async def recognize(*args, **kwargs):
        calls.append(args)
        return {"shazam": {"status": "matched", "title": "稻香", "artist": "周杰伦"}}

    install_services(monkeypatch, candidates, recognize)
    monkeypatch.setattr(agent, "extract_recognition_audio", lambda *args: args[-1].write_bytes(b"audio"))
    exports = []

    def export(src, start, end, dest):
        exports.append((start, end))
        dest.write_bytes(b"clip")

    monkeypatch.setattr(agent, "export_video", export)
    media = tmp_path / "input.mp4"
    media.touch()
    manifest = asyncio.run(agent.run_agent(media, tmp_path / "out"))
    result = json.loads(manifest.read_text())

    assert len(calls) == 1
    assert result["exported_count"] == 1
    assert result["candidates"][0]["decision"] == "background_music_skipped"
    interval = result["candidates"][1]["singing_intervals"][0]
    assert "稻香" in interval["file"]
    assert interval["title_resolution"] == {"status": "single_provider"}


def test_zero_candidates_still_produces_manifest(tmp_path, monkeypatch, pipeline):
    install_services(monkeypatch, [], lambda *args, **kwargs: pytest.fail("不应识曲"))
    media = tmp_path / "input.mp4"
    media.touch()
    path = asyncio.run(agent.run_agent(media, tmp_path / "out"))
    assert json.loads(path.read_text())["exported_count"] == 0


def test_prepare_and_finalize_reach_terminal_state(monkeypatch, tmp_path):
    """计数步骤必须落到终态；只累加 completed 会让界面永远显示进行中。"""
    import asyncio

    from segment.music_agent.pipeline import execute_pipeline

    events = []

    class Runtime:
        def __init__(self):
            self.config = {
                "checkpoint_dir": str(tmp_path / "cp"),
                "source_digest": "d",
                "attempt": 1,
                "owner": "o",
                "state_dir": str(tmp_path),
            }
            self._steps = {}

        def event(self, identity, label, **changes):
            event = {**self._steps.get(identity, {}), **changes}
            event.setdefault("completed", 0)
            event.setdefault("total", None)
            event["id"], event["label"] = identity, label
            self._steps[identity] = event
            events.append(dict(event))

        def advance(self, identity, label, total):
            self.event(identity, label, completed=self._steps[identity]["completed"] + 1, total=total)

        def run(self, spec, work):
            return work()

        async def async_run(self, spec, work):
            return await work()

        def activate(self, identity=""):
            from contextlib import nullcontext

            return nullcontext()

        def resource(self, name):
            from contextlib import nullcontext

            return nullcontext()

    services = SimpleNamespace(
        calls={
            "duration": lambda path: 100.0,
            "scan": lambda *a, **k: ([], []),
            "recognize": None,
            "choose_title": None,
            "extract_reference": None,
            "export": None,
        },
        recognize=None,
    )
    context = SimpleNamespace(
        media=tmp_path / "a.mp4",
        output=tmp_path,
        options={
            "chunk_seconds": 1200,
            "chunk_context_seconds": 30,
            "minimum_candidate_seconds": 30,
            "audio_model": "m",
            "netease_cookie": "",
        },
        services=services,
        runtime=Runtime(),
        client=None,
        spec=lambda identity, label, payload: {"id": identity, "label": label, "input": payload},
    )
    asyncio.run(execute_pipeline(context))
    prepare = [event for event in events if event["id"] == "prepare"]
    finalize = [event for event in events if event["id"] == "finalize"]
    # 候选为 0 时是 skipped，但同样要有终态时间戳。
    assert prepare[-1]["state"] == "skipped" and prepare[-1].get("finished_at")
    assert finalize[-1]["state"] == "skipped" and finalize[-1].get("finished_at")


def test_prepare_step_marks_failure(monkeypatch, tmp_path):
    """候选处理抛错时，计数步骤必须是 failed 并带上错误，不能停在 running。"""
    from segment.music_agent.pipeline import execute_pipeline

    events = {}

    class Runtime:
        def __init__(self):
            self.config = {
                "checkpoint_dir": str(tmp_path / "cp"),
                "source_digest": "d",
                "attempt": 1,
                "owner": "o",
                "state_dir": str(tmp_path),
            }
            self._steps = {}

        def event(self, identity, label, **changes):
            event = {**self._steps.get(identity, {}), **changes}
            event.setdefault("completed", 0)
            event.setdefault("total", None)
            event["id"], event["label"] = identity, label
            self._steps[identity] = event
            events[identity] = dict(event)

        def advance(self, identity, label, total):
            self.event(identity, label, completed=self._steps[identity]["completed"] + 1, total=total)

        def run(self, spec, work):
            return work()

        async def async_run(self, spec, work):
            return await work()

        def activate(self, identity=""):
            from contextlib import nullcontext

            return nullcontext()

        def resource(self, name):
            from contextlib import nullcontext

            return nullcontext()

    candidate = Candidate(
        index=1,
        start=10.0,
        end=200.0,
        classification="host_singing",
        confidence=0.95,
        host_singing_present=True,
        title_hint="a",
        rationale="r",
    )
    services = SimpleNamespace(
        calls={
            "duration": lambda path: 100.0,
            "scan": lambda *a, **k: ([candidate], []),
            "recognize": None,
            "choose_title": None,
            "extract_reference": None,
            "export": None,
        },
    )
    context = SimpleNamespace(
        media=tmp_path / "a.mp4",
        output=tmp_path,
        options={
            "chunk_seconds": 1200,
            "chunk_context_seconds": 30,
            "minimum_candidate_seconds": 30,
            "audio_model": "m",
            "netease_cookie": "",
        },
        services=services,
        runtime=Runtime(),
        client=None,
        spec=lambda identity, label, payload: {"id": identity, "label": label, "input": payload},
    )

    async def boom(item, ctx):
        raise RuntimeError("识曲失败")

    monkeypatch.setattr("segment.music_agent.pipeline.prepare_candidate", boom)
    with pytest.raises(RuntimeError, match="识曲失败"):
        asyncio.run(execute_pipeline(context))
    assert events["prepare"]["state"] == "failed"
    assert "识曲失败" in events["prepare"]["error"]
    assert events["prepare"]["finished_at"]
