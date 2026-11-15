import httpx
import pytest

from segment.song_lyrics import song_lyrics


def test_netease_lyrics_are_loaded_by_catalog_id():
    def respond(request):
        assert request.url.params["id"] == "123"
        return httpx.Response(200, json={"code": 200, "lrc": {"lyric": "[00:01]歌词"}, "tlyric": {"lyric": "译文"}})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = song_lyrics({"id": "netease:123", "title": "歌", "artist": "人"}, get=client.get)
    assert result == {"lyrics": "[00:01]歌词", "translation": "译文", "source": "网易云"}


def test_itunes_result_uses_explicit_metadata_match_in_lrclib():
    def respond(request):
        assert request.url.params["track_name"] == "稻香"
        assert request.url.params["artist_name"] == "周杰倫"
        return httpx.Response(200, json={"plainLyrics": "歌词正文", "syncedLyrics": None})

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = song_lyrics({"id": "itunes:123", "title": "稻香", "artist": "周杰倫"}, get=client.get)
    assert result == {"lyrics": "歌词正文", "translation": "", "source": "LRCLIB（按歌名与歌手匹配）"}


def test_unavailable_lyrics_are_explicit_not_a_request_failure():
    with httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as client:
        result = song_lyrics({"id": "itunes:123", "title": "歌", "artist": "人"}, get=client.get)
    assert result["lyrics"] == ""


def test_unsupported_provider_is_rejected_without_request():
    with pytest.raises(ValueError, match="来源"):
        song_lyrics({"id": "unknown:1", "title": "歌", "artist": "人"}, get=lambda *args, **kwargs: pytest.fail())
