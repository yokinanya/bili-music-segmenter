import asyncio

import httpx
import pytest

from segment.music_agent.qqmusic_client import parse_search, search_lyrics, search_payload


def response(songs=None, filtered=0):
    return {
        "code": 0,
        "req_0": {
            "code": 0,
            "data": {
                "code": 0,
                "meta": {"is_filter": filtered},
                "body": {"item_song": songs or []},
            },
        },
    }


def test_payload_is_anonymous_lyric_search():
    payload = search_payload("清晰实听歌词")
    assert payload["req_0"]["param"]["search_type"] == 7
    assert payload["req_0"]["param"]["query"] == "清晰实听歌词"
    assert payload["comm"]["QIMEI36"]
    assert "authst" not in payload["comm"]


def test_parses_lyrics_and_metadata():
    songs = [{"id": 1, "mid": "mid", "title": "歌曲", "content": "歌词", "singer": [{"name": "歌手"}]}]
    assert parse_search(response(songs)) == [
        {"id": 1, "mid": "mid", "title": "歌曲", "lyrics": "歌词", "artist": "歌手"}
    ]
    assert parse_search(response()) == []


@pytest.mark.parametrize("data", [{"code": 1}, {"code": 0, "req_0": {"code": 1}}, response(filtered=-9)])
def test_business_errors_and_filtering_are_exposed(data):
    with pytest.raises(ValueError):
        parse_search(data)


def test_http_adapter_uses_real_protocol_and_reports_http_errors(monkeypatch):
    original = httpx.AsyncClient

    def handle(request):
        assert request.url.host == "u.y.qq.com"
        return httpx.Response(503, request=request)

    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: original(**kwargs, transport=httpx.MockTransport(handle))
    )
    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(search_lyrics("实听歌词"))
