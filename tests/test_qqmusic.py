import asyncio
from unittest.mock import AsyncMock

import pytest

from segment.music_agent.qqmusic import apply_verification, verify_lyrics

LYRIC = "紧紧握着青花信物信守着承诺"
SONG = {"id": 102204539, "mid": "002MFDAV3rPFlo", "title": "青花", "artist": "周传雄", "lyrics": LYRIC}


def review(lyrics=LYRIC, confidence=0.9):
    return {"data": {"lyrics_evidence": lyrics, "confidence": confidence}}


def test_lyric_verification_checks_actual_lyrics_not_search_rank():
    search = AsyncMock(return_value=[{**SONG, "title": "其他作品", "lyrics": "无关歌词"}, SONG])
    result = asyncio.run(verify_lyrics(review(), search))
    assert result["status"] == "matched"
    assert result["mid"] == SONG["mid"]
    assert "lyrics" not in result
    search.assert_awaited_once_with(LYRIC)


@pytest.mark.parametrize("evidence", [None, review(""), review(confidence=0.5)])
def test_insufficient_lyrics_do_not_query_or_guess(evidence):
    search = AsyncMock()
    assert asyncio.run(verify_lyrics(evidence, search))["status"] == "insufficient_evidence"
    search.assert_not_called()


def test_different_titles_with_same_lyrics_remain_ambiguous():
    search = AsyncMock(return_value=[SONG, {**SONG, "title": "另一个作品"}])
    result = asyncio.run(verify_lyrics(review(), search))
    assert result["status"] == "ambiguous"
    assert apply_verification(("", "", "unmatched"), result) == ("", "", "unmatched")


def test_no_matching_lyrics_and_network_failure_are_distinct():
    assert asyncio.run(verify_lyrics(review(), AsyncMock(return_value=[])))["status"] == "no_match"
    with pytest.raises(RuntimeError, match="QQ network"):
        asyncio.run(verify_lyrics(review(), AsyncMock(side_effect=RuntimeError("QQ network"))))


def test_qq_result_can_resolve_unknown_but_exposes_disagreement():
    evidence = {**SONG, "status": "matched"}
    assert apply_verification(("", "", "unmatched"), evidence) == ("青花", "周传雄", "qqmusic_verified")
    assert apply_verification(("其他歌", "其他人", "matched"), evidence) == ("", "", "qqmusic_conflict")


def test_formatting_and_traditional_characters_are_normalized():
    search = AsyncMock(return_value=[{**SONG, "lyrics": "[00:01.00]緊緊握著青花信物，信守著承諾"}])
    assert asyncio.run(verify_lyrics(review(), search))["status"] == "matched"


def test_escaped_lyric_newlines_are_not_treated_as_letters():
    lyrics = "紧紧握着\\n青花信物\\n信守着承诺"
    result = asyncio.run(verify_lyrics(review(), AsyncMock(return_value=[{**SONG, "lyrics": lyrics}])))
    assert result["status"] == "matched"
