"""Small anonymous QQ lyric search adapter, based on L-1124/QQMusicApi.

Uses the mobile CGI's lyric-search response, which includes matching lyric text.
No account, device registration, audio upload or SDK dependency is required.
"""

from __future__ import annotations

from uuid import uuid4

import httpx

SEARCH_URL = "https://u.y.qq.com/cgi-bin/musicu.fcg"
CLIENT_VERSION = "20090008"
LYRIC_SEARCH_TYPE = 7
SEARCH_RESULTS = 5
REQUEST_TIMEOUT_SECONDS = 60


def search_payload(query: str) -> dict:
    # The anonymous client identifier must be nonempty, or QQ filters lyric results.
    device_id = str(uuid4())
    return {
        "comm": {
            "ct": "11",
            "cv": CLIENT_VERSION,
            "v": CLIENT_VERSION,
            "tmeAppID": "qqmusic",
            "chid": "10003505",
            "QIMEI36": device_id,
        },
        "req_0": {
            "module": "music.search.SearchCgiService",
            "method": "DoSearchForQQMusicMobile",
            "param": {
                "searchid": str(uuid4().int),
                "query": query,
                "search_type": LYRIC_SEARCH_TYPE,
                "num_per_page": SEARCH_RESULTS,
                "page_num": 1,
                "highlight": 0,
                "grp": 1,
                "selectors": {},
                "vec_selectors": [],
            },
        },
    }


def parse_search(response: dict) -> list[dict]:
    if not isinstance(response, dict) or response.get("code") != 0:
        raise ValueError("QQ 音乐请求失败或返回无效响应")
    result = response.get("req_0", {})
    if result.get("code") != 0:
        raise ValueError(f"QQ 音乐搜索失败：code={result.get('code')}")
    data = result["data"]
    if data.get("code") != 0 or data["meta"]["is_filter"] < 0:
        raise ValueError("QQ 音乐搜索被过滤或返回业务错误")
    songs = data["body"]["item_song"]
    if not isinstance(songs, list):
        raise ValueError("QQ 音乐搜索歌曲列表无效")
    return [_song(song) for song in songs]


def _song(song: dict) -> dict:
    for field in ("mid", "title", "content"):
        if not isinstance(song.get(field), str):
            raise ValueError(f"QQ 音乐歌曲 {field} 无效")
    singers = song["singer"]
    if not isinstance(singers, list) or any(not isinstance(s.get("name"), str) for s in singers):
        raise ValueError("QQ 音乐歌手列表无效")
    return {
        "id": song["id"],
        "mid": song["mid"],
        "title": song["title"],
        "artist": " / ".join(singer["name"] for singer in singers),
        "lyrics": song["content"],
    }


async def search_lyrics(query: str) -> list[dict]:
    headers = {"User-Agent": f"QQMusic {CLIENT_VERSION}(android 12)"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        response = await client.post(SEARCH_URL, json=search_payload(query))
        response.raise_for_status()
        return parse_search(response.json())
