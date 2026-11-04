"""Shazam reference matching without global clients or post-request sleeps."""

import re

from shazamio import Shazam


async def shazam_orig(file, **kwargs):
    match = await shazam(file)
    return (shazam_title(match), match) if match is not None else None


async def shazam(file):
    response = await Shazam().recognize(file)
    return parse_shazam_response(response)


def parse_shazam_response(response):
    if not isinstance(response, dict):
        raise ValueError("Shazam 响应必须是对象")
    if "track" in response:
        track = response["track"]
        if not isinstance(track, dict) or not all(isinstance(track.get(key), str) for key in ("title", "subtitle")):
            raise ValueError("Shazam track 缺少有效歌名或歌手")
        return track
    if response.get("matches") == []:
        return None
    raise ValueError(f"Shazam 响应缺少 track，字段：{sorted(response)}")


def legalize_filename(value):
    return re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", value).strip()


def shazam_title(match):
    return [legalize_filename(match["title"]), legalize_filename(match["subtitle"])]
