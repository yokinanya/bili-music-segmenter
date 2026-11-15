"""Search public song metadata in supported music catalogs."""

from __future__ import annotations

import httpx

ITUNES_URL = "https://itunes.apple.com/search"
NETEASE_URL = "https://music.163.com/api/cloudsearch/pc"
SEARCH_TIMEOUT_SECONDS = 20
SEARCH_RESULT_LIMIT = 20


def search_songs(query: str, *, get) -> dict:
    query = query.strip()
    if not query:
        raise ValueError("请输入歌曲名或歌手关键词")
    songs, errors = [], []
    for provider, parse in (("网易云", _netease_songs), ("iTunes", _itunes_songs)):
        try:
            songs.extend(_search(provider, parse, query, get))
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            errors.append({"provider": provider, "error": str(error)})
    return {"songs": songs, "errors": errors}


def _search(provider: str, parse, query: str, get) -> list[dict]:
    url, options = _request(provider, query)
    response = get(url, **options, timeout=SEARCH_TIMEOUT_SECONDS)
    response.raise_for_status()
    source = {"网易云": "netease", "iTunes": "itunes"}[provider]
    return [{**song, "id": f"{source}:{song['id']}", "provider": provider} for song in parse(response.json())]


def _request(provider: str, query: str) -> tuple[str, dict]:
    if provider == "网易云":
        return NETEASE_URL, {
            "params": {"s": query, "type": 1, "offset": 0, "limit": SEARCH_RESULT_LIMIT},
            "headers": {"Referer": "https://music.163.com/", "User-Agent": "Mozilla/5.0"},
        }
    return ITUNES_URL, {
        "params": {"term": query, "entity": "song", "media": "music", "country": "TW", "limit": SEARCH_RESULT_LIMIT}
    }


def _itunes_songs(payload: dict) -> list[dict]:
    results = payload.get("results")
    if not isinstance(results, list):
        raise ValueError("返回了无效的搜索结果")
    return [
        _song(
            str(item.get("trackId", "")),
            {
                "title": item.get("trackName", ""),
                "artist": item.get("artistName", ""),
                "album": item.get("collectionName", ""),
            },
        )
        for item in results
    ]


def _netease_songs(payload: dict) -> list[dict]:
    results = payload.get("result", {}).get("songs")
    if not isinstance(results, list):
        raise ValueError("返回了无效的搜索结果")
    songs = []
    for item in results:
        artists = item.get("ar", item.get("artists", []))
        album = item.get("al", item.get("album", {}))
        if not isinstance(artists, list) or not isinstance(album, dict):
            raise ValueError("返回了无效的歌曲信息")
        artist = "、".join(value["name"] for value in artists)
        songs.append(
            _song(
                str(item.get("id", "")),
                {"title": item.get("name", ""), "artist": artist, "album": album.get("name", "")},
            )
        )
    return songs


def _song(identity: str, fields: dict) -> dict:
    if not identity:
        raise ValueError("返回了无效的歌曲 ID")
    song = {"id": identity}
    for name, text in fields.items():
        if not isinstance(text, str):
            raise ValueError("返回了无效的歌曲信息")
        song[name] = text
    return song
