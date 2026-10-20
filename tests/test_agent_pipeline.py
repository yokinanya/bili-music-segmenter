import asyncio
import json
from types import SimpleNamespace

import pytest

from segment.music_agent import agent, detection, models
from segment.music_agent.config import ApiConfig, load_config
from segment.music_agent.detection import Candidate


def test_base_url_is_required(monkeypatch):
    monkeypatch.setattr("segment.music_agent.config.load_dotenv", lambda *args: None)
    monkeypatch.delenv("DASHSCOPE_BASE_URL", raising=False)
    with pytest.raises(ValueError, match="DASHSCOPE_BASE_URL"):
        load_config()


def test_audio_and_text_requests_use_different_content_types():
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))], usage=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    models.audio_model_call(client, "qwen3.8-omni-flash", "audio", "https://example.com/audio")
    models.text_model_call(client, "qwen3.8-flash", "text")
    assert isinstance(requests[0]["messages"][0]["content"], list)
    assert requests[1]["messages"][0]["content"] == "text"


def test_boundaries_can_extend_into_context_but_not_outside_audio(monkeypatch):
    monkeypatch.setattr(detection, "media_duration", lambda _: 300)
    monkeypatch.setattr(
        detection,
        "call_with_oss",
        lambda *args, **kwargs: {
            "data": {
                "host_singing_present": True,
                "confidence": 0.9,
                "intervals": [{"start_seconds": 10, "end_seconds": 90}],
            },
            "usage": None,
        },
    )
    candidate = Candidate(1, 100, 150, "host_singing", 0.9, True, "", "")
    intervals, _ = detection.refine_candidate(
        None,
        candidate,
        None,
        None,
        context_seconds=20,
        oss_prefix="test",
        model="qwen3.8-omni-flash",
        minimum_confidence=0.85,
    )
    assert intervals == [(90, 170)]


def test_background_skip_and_successful_export_pipeline(tmp_path, monkeypatch):
    config = ApiConfig("test", "https://example.com/v1", "id", "secret", "endpoint", "bucket", "test")
    monkeypatch.setattr(agent, "load_config", lambda: config)
    monkeypatch.setattr("oss2.Bucket", lambda *args: None)
    monkeypatch.setattr("oss2.Auth", lambda *args: None)
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: None)
    monkeypatch.setattr(agent, "media_duration", lambda _: 300)
    candidates = [
        Candidate(1, 0, 80, "background_music_chat", 0.99, False, "", "聊天"),
        Candidate(2, 100, 200, "host_singing", 0.9, True, "", "唱歌"),
    ]
    monkeypatch.setattr(agent, "scan_candidates", lambda *args, **kwargs: (candidates, []))
    monkeypatch.setattr(agent, "refine_candidate", lambda *args, **kwargs: ([(110, 150)], {}))
    monkeypatch.setattr(agent, "extract_wav", lambda *args: None)
    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: None)
    calls = []

    async def recognize(*args, **kwargs):
        calls.append(args)
        return {"shazam": {"status": "matched", "title": "稻香", "artist": "周杰伦"}}

    monkeypatch.setattr(agent, "recognize_audio", recognize)
    monkeypatch.setattr(agent, "export_video", lambda *args: args[-1].write_bytes(b"clip"))
    media = tmp_path / "input.mp4"
    media.touch()
    manifest = asyncio.run(agent.run_agent(media, tmp_path / "out"))
    result = json.loads(manifest.read_text())
    assert len(calls) == 1
    assert result["exported_count"] == 1
    assert result["candidates_completed"] == 2
    assert result["candidates"][0]["decision"] == "background_music_skipped"
    assert "稻香" in result["candidates"][1]["singing_intervals"][0]["file"]


def test_zero_candidates_still_produces_manifest(tmp_path, monkeypatch):
    config = ApiConfig("test", "https://example.com/v1", "id", "secret", "endpoint", "bucket", "test")
    monkeypatch.setattr(agent, "load_config", lambda: config)
    monkeypatch.setattr("oss2.Bucket", lambda *args: None)
    monkeypatch.setattr("oss2.Auth", lambda *args: None)
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: None)
    monkeypatch.setattr(agent, "media_duration", lambda _: 300)
    monkeypatch.setattr(agent, "scan_candidates", lambda *args, **kwargs: ([], []))
    media = tmp_path / "input.mp4"
    media.touch()
    path = asyncio.run(agent.run_agent(media, tmp_path / "out"))
    assert json.loads(path.read_text())["exported_count"] == 0
