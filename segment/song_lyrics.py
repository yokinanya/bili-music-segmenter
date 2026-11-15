"""On-demand lyrics for manual song verification, without audio analysis."""

LYRICS_TIMEOUT_SECONDS = 20


def song_lyrics(song: dict, *, get) -> dict:
    if set(song) != {"id", "title", "artist"} or any(not isinstance(value, str) for value in song.values()):
        raise ValueError("无效的歌曲信息")
    provider, _, identity = song["id"].partition(":")
    if provider == "netease" and identity.isdecimal():
        response = get(
            "https://music.163.com/api/song/lyric",
            params={"id": identity, "lv": -1, "tv": -1},
            timeout=LYRICS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise ValueError(f"歌词接口返回错误码 {payload.get('code')}")
        return _result(
            payload.get("lrc", {}).get("lyric", ""),
            translation=payload.get("tlyric", {}).get("lyric", ""),
            source="网易云",
        )
    if provider != "itunes" or not identity.isdecimal():
        raise ValueError("不支持的歌曲来源")
    response = get(
        "https://lrclib.net/api/get",
        params={"track_name": song["title"], "artist_name": song["artist"]},
        timeout=LYRICS_TIMEOUT_SECONDS,
    )
    if response.status_code == 404:
        return _result("", source="LRCLIB（按歌名与歌手匹配）")
    response.raise_for_status()
    payload = response.json()
    return _result(payload.get("syncedLyrics") or payload.get("plainLyrics") or "", source="LRCLIB（按歌名与歌手匹配）")


def _result(lyrics: str, *, translation: str = "", source: str) -> dict:
    if not isinstance(lyrics, str) or not isinstance(translation, str):
        raise ValueError("歌词接口返回了无效内容")
    return {"lyrics": lyrics, "translation": translation, "source": source}
