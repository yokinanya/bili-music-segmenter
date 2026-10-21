import asyncio
import time
from pathlib import Path
from threading import Lock
from unittest.mock import Mock

import pytest

from segment.music_agent.title_resolution import TitleContext, needs_audio_title, resolve_audio_title
from segment.shazam import parse_shazam_response


def test_shazam_no_match_is_not_key_error():
    assert parse_shazam_response({"matches": []}) is None
    with pytest.raises(ValueError, match="缺少 track"):
        parse_shazam_response({"matches": [{"id": "test"}]})
    with pytest.raises(ValueError):
        parse_shazam_response({"track": {}})
    assert parse_shazam_response({"track": {"title": "song", "subtitle": "artist"}})["title"] == "song"


def test_shazam_no_match_reaches_agent_status(monkeypatch):
    from segment.music_agent import recognition

    async def no_match(*args):
        return None

    monkeypatch.setattr(recognition, "shazam_orig", no_match)
    result = asyncio.run(
        recognition.recognize_audio(
            Path("audio.wav"),
            netease_endpoint="http://localhost:3000",
            use_netease=False,
        )
    )
    assert result["shazam"] == {"status": "no_match"}


def test_recognizers_run_concurrently(monkeypatch):
    from segment.music_agent import recognition

    started, finished = [], []
    lock = Lock()

    async def slow_shazam(*args, **kwargs):
        with lock:
            started.append(time.monotonic())
        await asyncio.sleep(0.4)
        with lock:
            finished.append(time.monotonic())
        return None

    async def slow_netease(*args, **kwargs):
        with lock:
            started.append(time.monotonic())
        time.sleep(0.4)
        with lock:
            finished.append(time.monotonic())
        return None

    monkeypatch.setattr(recognition, "shazam_orig", slow_shazam)
    monkeypatch.setattr(recognition, "netease_orig", slow_netease)
    begin = time.monotonic()
    result = asyncio.run(
        recognition.recognize_audio(
            Path("audio.wav"),
            netease_endpoint="http://localhost:3000",
            timeout=5,
        )
    )
    elapsed = time.monotonic() - begin
    # Sequential providers would need ~0.8s; concurrent execution finishes both in roughly one wait.
    assert elapsed < 0.7
    assert max(started) < min(finished)
    assert result["shazam"]["status"] == "no_match"
    assert result["netease"]["status"] == "no_match"


def test_recognizer_base_exception_is_reported_not_raised(monkeypatch):
    from segment.music_agent import recognition
    from segment.shazam import KoreanCharException

    async def korean(*args, **kwargs):
        raise KoreanCharException("韩文歌名")

    monkeypatch.setattr(recognition, "shazam_orig", korean)
    result = asyncio.run(
        recognition.recognize_audio(Path("audio.wav"), netease_endpoint="http://localhost:3000", use_netease=False)
    )
    assert result["shazam"]["status"] == "error"
    assert "KoreanCharException" in result["shazam"]["error"]


def test_conflict_and_romanized_names_need_audio():
    assert needs_audio_title({}, "conflict")
    assert needs_audio_title(
        {"shazam": {"status": "matched", "title": "Tori No Uta", "artist": "Lia"}}, "single_provider"
    )
    assert not needs_audio_title({"netease": {"status": "matched", "title": "偶阵雨", "artist": "梁静茹"}}, "matched")


def test_chinese_version_is_selected_using_lyrics():
    refs = {
        "shazam": {"status": "matched", "title": "JEWEL", "artist": "Ayumi Hamasaki"},
        "netease": {"status": "matched", "title": "鱼玄机", "artist": "Gabriel"},
    }
    data = {
        "choice": "netease",
        "confidence": 0.95,
        "language": "中文",
        "lyrics_evidence": "明确中文歌词",
        "display_title": "鱼玄机",
        "display_artist": "Gabriel",
        "name_evidence": "候选名称",
        "rationale": "中文填词版",
    }
    call = Mock(return_value={"data": data, "usage": None})
    context = TitleContext(Path("media.mp4"), None, None, "audio", "prefix", call)
    result = resolve_audio_title({"start_seconds": 1, "end_seconds": 60}, refs, context)
    assert result["title"] == "鱼玄机"
    assert result["status"] == "audio_verified"
    data["lyrics_evidence"] = ""
    assert resolve_audio_title({"start_seconds": 1, "end_seconds": 60}, refs, context)["status"] == "unresolved"


def test_chinese_display_requires_evidence():
    refs = {"shazam": {"status": "matched", "title": "Tori No Uta", "artist": "Lia"}}
    data = {
        "choice": "shazam",
        "confidence": 0.95,
        "language": "日文",
        "lyrics_evidence": "日文歌词",
        "display_title": "鸟之诗",
        "display_artist": "Lia",
        "name_evidence": "",
        "rationale": "同曲",
    }
    context = TitleContext(Path("media.mp4"), None, None, "audio", "prefix", Mock(return_value={"data": data}))
    with pytest.raises(ValueError, match="证据"):
        resolve_audio_title({"start_seconds": 1, "end_seconds": 60}, refs, context)
