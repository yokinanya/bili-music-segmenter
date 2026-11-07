import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from segment.music_agent import pipeline_candidates
from segment.music_agent.pipeline_services import PipelineServices
from segment.music_agent.recognition import deterministic_title_choice
from segment.music_agent.title_resolution import needs_audio_title

LYRICS = "紧紧握着青花信物信守着承诺"


class Runtime:
    async def async_run(self, spec, work):
        return await work()

    def run(self, spec, work):
        return work()


def make_context(provider, search):
    services = PipelineServices(
        {
            "recognize": AsyncMock(return_value={"shazam": provider}),
            "choose_title": deterministic_title_choice,
            "needs_audio": needs_audio_title,
            "audio_title": lambda *args: {
                "title": "",
                "artist": "",
                "status": "unresolved",
                "audio_review": {"data": {"confidence": 0.9, "lyrics_evidence": LYRICS}},
            },
            "audio": None,
            "qqmusic": search,
        },
        asyncio.Semaphore(1),
    )
    return SimpleNamespace(
        services=services,
        runtime=Runtime(),
        media=Path("source.mp4"),
        client=None,
        storage=None,
        prefix="",
        options={
            "use_title_model": True,
            "audio_model": "audio",
            "netease_cookie": "",
            "recognizer_timeout": 60,
            "use_shazam": True,
            "use_netease": False,
        },
        spec=lambda identity, label, payload: {"id": identity, "input": payload},
    )


@pytest.mark.parametrize(
    "provider,expected",
    [
        ({"status": "no_match"}, "青花"),
        ({"status": "matched", "title": "青花", "artist": "作品歌手"}, "青花"),
        ({"status": "matched", "title": "其他歌", "artist": "作品歌手"}, ""),
    ],
)
def test_normal_identification_entry_uses_qq_without_faking_fingerprint_matches(monkeypatch, provider, expected):
    search = AsyncMock(
        return_value=[
            {
                "id": 1,
                "mid": "mid",
                "title": "青花",
                "artist": "作品歌手",
                "lyrics": LYRICS,
            }
        ]
    )
    context = make_context(provider, search)
    monkeypatch.setattr(pipeline_candidates, "_recognition_audio", lambda *args: Path("audio.mp3"))
    result = asyncio.run(pipeline_candidates.recognize_interval({"start_seconds": 0, "end_seconds": 30}, context))
    assert result["title"] == expected
    assert result["recognition"]["shazam"] == provider
    assert result["title_resolution"]["qqmusic"]["status"] == "matched"
    if not expected:
        assert result["title_resolution"]["status"] == "qqmusic_conflict"


def test_qq_no_match_preserves_existing_chinese_identification(monkeypatch):
    provider = {"status": "matched", "title": "青花", "artist": "作品歌手"}
    context = make_context(provider, AsyncMock(return_value=[]))
    monkeypatch.setattr(pipeline_candidates, "_recognition_audio", lambda *args: Path("audio.mp3"))
    result = asyncio.run(pipeline_candidates.recognize_interval({"start_seconds": 0, "end_seconds": 30}, context))
    assert result["title"] == "青花"
    assert result["title_resolution"]["status"] == "single_provider"
    assert result["title_resolution"]["qqmusic"]["status"] == "no_match"
