"""识曲只做自动匹配与人工决策，不再调用任何模型做二次判断。"""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from segment.music_agent import pipeline_candidates
from segment.music_agent.pipeline_services import PipelineServices
from segment.music_agent.recognition import deterministic_title_choice


class Runtime:
    async def async_run(self, spec, work):
        return await work()

    def run(self, spec, work):
        return work()


def make_context(providers):
    services = PipelineServices(
        {"recognize": AsyncMock(return_value=providers), "choose_title": deterministic_title_choice},
        asyncio.Semaphore(1),
    )
    return SimpleNamespace(
        services=services,
        runtime=Runtime(),
        media=Path("source.mp4"),
        client=None,
        options={
            "netease_cookie": "",
            "recognizer_timeout": 60,
            "use_shazam": True,
            "use_netease": True,
        },
        spec=lambda identity, label, payload: {"id": identity, "input": payload},
    )


def identify(monkeypatch, providers):
    monkeypatch.setattr(pipeline_candidates, "_recognition_audio", lambda *args: Path("audio.mp3"))
    return asyncio.run(
        pipeline_candidates.recognize_interval({"start_seconds": 0, "end_seconds": 30}, make_context(providers))
    )


def test_matching_providers_produce_a_title_without_model_review(monkeypatch):
    result = identify(
        monkeypatch,
        {
            "shazam": {"status": "matched", "title": "青花", "artist": "周传雄"},
            "netease": {"status": "matched", "title": "青花", "artist": "周传雄"},
        },
    )
    assert (result["title"], result["artist"]) == ("青花", "周传雄")
    assert result["title_resolution"] == {"status": "matched"}


def test_single_provider_match_is_used_directly(monkeypatch):
    result = identify(monkeypatch, {"shazam": {"status": "matched", "title": "唯一", "artist": "邓紫棋"}})
    assert (result["title"], result["title_resolution"]["status"]) == ("唯一", "single_provider")


def test_conflicting_providers_leave_the_title_for_manual_input(monkeypatch):
    result = identify(
        monkeypatch,
        {
            "shazam": {"status": "matched", "title": "青花", "artist": "周传雄"},
            "netease": {"status": "matched", "title": "别的歌", "artist": "别人"},
        },
    )
    assert (result["title"], result["artist"]) == ("", "")
    assert result["title_resolution"] == {"status": "conflict"}


def test_provider_errors_still_fail_the_interval(monkeypatch):
    with pytest.raises(RuntimeError, match="识曲服务请求失败"):
        identify(monkeypatch, {"shazam": {"status": "error", "error": "timeout"}})


@pytest.mark.parametrize(
    "recognize_result,title",
    [
        (
            {
                "shazam": {"status": "matched", "title": "痴心絕對", "artist": "Sam Lee"},
                "netease": {"status": "matched", "title": "痴心绝对", "artist": "李圣杰"},
            },
            "痴心绝对",
        ),
        (
            {"netease": {"status": "matched", "title": "晴天", "artist": "周杰伦"}},
            "晴天",
        ),
    ],
)
def test_same_song_from_different_providers_or_artists_is_accepted(monkeypatch, recognize_result, title):
    result = identify(monkeypatch, recognize_result)
    assert result["title"] == title


def test_netease_vote_tie_counts_as_conflict_even_when_shazam_matches(monkeypatch):
    result = identify(
        monkeypatch,
        {
            "shazam": {"status": "matched", "title": "唯一", "artist": "邓紫棋"},
            "netease": {"status": "conflict", "error": "offset=6: 甲/乙", "samples": [[6, "甲", "乙"]]},
        },
    )
    assert result["title"] == ""
    assert result["title_resolution"]["status"] == "conflict"


def test_version_suffixes_are_stripped_but_real_title_differences_are_kept():
    from segment.music_agent.recognition import normalize_title

    # 版本附注不算不同作品。
    assert normalize_title("空空（cover陈粒）") == normalize_title("空空")
    assert normalize_title("天黑黑 (伴奏)") == normalize_title("天黑黑")
    assert normalize_title("稻香（Live版）") == normalize_title("稻香")
    # 歌名本身不同就必须区分，不能把所有括号都剥掉。
    assert normalize_title("空空（温柔版）") != normalize_title("空空")
    assert normalize_title("空空") != normalize_title("定格的瞬间")
