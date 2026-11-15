import json
from types import SimpleNamespace

import httpx
import pytest

from segment.webui import Handler


def test_song_search_route_returns_online_metadata(monkeypatch):
    handler = object.__new__(Handler)
    responses = []
    result = {
        "songs": [
            {"id": "netease:1", "provider": "网易云", "title": "稻香", "artist": "周杰伦", "album": "魔杰座"},
        ],
        "errors": [],
    }
    handler.jobs = SimpleNamespace(song_search=lambda query: result)
    monkeypatch.setattr(handler, "_query", lambda name: "稻香")
    monkeypatch.setattr(handler, "_json", lambda status, body: responses.append((status, body)))
    handler._root("GET", "/api/songs/search")
    assert responses == [(200, result)]


def test_online_catalog_search_encodes_query_and_normalizes_results():
    from segment.song_search import search_songs

    def respond(request):
        if request.url.host == "music.163.com":
            return httpx.Response(200, json={"result": {"songs": []}})
        assert request.url.params["term"] == "稻香 周杰伦"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "trackId": 123,
                        "trackName": "稻香",
                        "artistName": "周杰倫",
                        "collectionName": "魔杰座",
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = search_songs("  稻香 周杰伦  ", get=client.get)
    assert result == {
        "songs": [{"id": "itunes:123", "provider": "iTunes", "title": "稻香", "artist": "周杰倫", "album": "魔杰座"}],
        "errors": [],
    }


def test_search_combines_netease_and_itunes():
    from segment.song_search import search_songs

    def respond(request):
        if request.url.host == "music.163.com":
            assert request.url.path == "/api/cloudsearch/pc"
            return httpx.Response(
                200,
                json={
                    "result": {
                        "songs": [
                            {
                                "id": 3381542797,
                                "name": "稻香",
                                "ar": [{"name": "周杰伦"}, {"name": "合唱歌手"}],
                                "al": {"name": "魔杰座"},
                            }
                        ]
                    }
                },
            )
        assert request.url.host == "itunes.apple.com"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "trackId": 1624001324,
                        "trackName": "稻香",
                        "artistName": "周杰倫",
                        "collectionName": "魔杰座",
                    }
                ]
            },
        )

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        songs = search_songs("稻香 周杰伦", get=client.get)
    assert songs["songs"] == [
        {
            "id": "netease:3381542797",
            "provider": "网易云",
            "title": "稻香",
            "artist": "周杰伦、合唱歌手",
            "album": "魔杰座",
        },
        {"id": "itunes:1624001324", "provider": "iTunes", "title": "稻香", "artist": "周杰倫", "album": "魔杰座"},
    ]
    assert songs["errors"] == []


def test_empty_search_does_not_contact_provider():
    from segment.song_search import search_songs

    def unexpected(*args, **kwargs):
        pytest.fail("empty search must not contact provider")

    with pytest.raises(ValueError, match="关键词"):
        search_songs("   ", get=unexpected)


@pytest.mark.parametrize("status,payload", [(503, {}), (200, {"results": "invalid"})])
def test_provider_failures_are_explicit(status, payload):
    from segment.song_search import search_songs

    def respond(request):
        if request.url.host == "music.163.com" and status == 200:
            return httpx.Response(200, json={"result": {"songs": "invalid"}})
        return httpx.Response(status, content=json.dumps(payload))

    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        result = search_songs("稻香", get=client.get)
    assert result["songs"] == []
    assert {error["provider"] for error in result["errors"]} == {"网易云", "iTunes"}
