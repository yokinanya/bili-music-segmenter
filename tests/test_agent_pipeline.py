"""端到端流水线：Gemini 出点位、自动识曲、切分导出。"""

import asyncio
import json

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
