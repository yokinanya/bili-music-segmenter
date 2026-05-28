import os
import pprint
import subprocess
import tempfile
from collections.abc import Iterable

import requests

from segment.shazam import legalize_filename, recognize_files

DEFAULT_TIMEOUT = 60
AFP_DURATION = 3
AFP_OFFSETS = (6, 12, 20, 30)
AFP_SAMPLE_RATE = 8000
DEFAULT_REJECTS = (("劫", "黄霄雲"),)
AFP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vendor", "ncm-afp")
AFP_GENERATOR = os.path.join(AFP_DIR, "generate_fp.js")


def netease_title(match):
    title = _first_text(match, ("title", "name", "songName"))
    artist = _first_text(match, ("artist", "artistName", "singer", "author"))
    return [legalize_filename(title), legalize_filename(artist)]


async def netease_orig(
    file,
    *,
    endpoint,
    cookie="",
    offsets=AFP_OFFSETS,
    rejects=DEFAULT_REJECTS,
    timeout=DEFAULT_TIMEOUT,
):
    match = _recognize_with_offsets(file, endpoint, cookie, offsets, timeout)
    title = netease_title(match)
    _raise_if_rejected(title, rejects)
    return title, match


async def neteasing(
    outdir,
    media,
    *,
    endpoint,
    cookie="",
    offsets=AFP_OFFSETS,
    rejects=DEFAULT_REJECTS,
    coverart_path="",
    timeout=DEFAULT_TIMEOUT,
    ignore_fails=False,
):
    async def recognizer(file):
        return await netease_orig(
            file,
            endpoint=endpoint,
            cookie=cookie,
            offsets=offsets,
            rejects=rejects,
            timeout=timeout,
        )

    await recognize_files(
        outdir,
        media,
        recognizer_func=recognizer,
        provider_name="netease",
        coverart_path=coverart_path,
        coverart_func=netease_coverart,
        ignore_fails=ignore_fails,
    )


def netease_coverart(match, fn, outdir):
    cover_url = _first_optional_text(
        match, ("cover_url", "coverUrl", "picUrl", "albumPic")
    )
    if cover_url is None:
        return
    response = requests.get(cover_url, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    ext = os.path.splitext(cover_url.split("?", 1)[0])[1] or ".jpg"
    with open(os.path.join(outdir, os.path.basename(fn) + ext), "wb") as file:
        file.write(response.content)


def generate_audio_fp(file, offset):
    with tempfile.NamedTemporaryFile(suffix=".f32le") as pcm_file:
        _extract_pcm(file, pcm_file.name, offset)
        return _run_afp_generator(pcm_file.name)


def parse_offsets(value):
    if isinstance(value, str):
        return tuple(int(item.strip()) for item in value.split(",") if item.strip())
    if isinstance(value, Iterable):
        return tuple(int(item) for item in value)
    return (int(value),)


def parse_rejects(value):
    if value is None:
        return ()
    if isinstance(value, str):
        return tuple(_parse_reject_item(item) for item in value.split(",") if item)
    return tuple(tuple(item) for item in value)


def _parse_reject_item(value):
    parts = [part.strip() for part in value.split("|")]
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError("NetEase reject item must be formatted as title|artist")
    return tuple(parts)


def _raise_if_rejected(title, rejects):
    title_text, artist_text = title
    for rejected_title, rejected_artist in parse_rejects(rejects):
        if title_text == rejected_title and artist_text == rejected_artist:
            raise NetEaseRejectedMatch(
                f"NetEase rejected known bad match: {title_text} by {artist_text}"
            )


def _recognize_with_offsets(file, endpoint, cookie, offsets, timeout):
    failures = []
    for offset in parse_offsets(offsets):
        try:
            audio_fp = generate_audio_fp(file, offset)
            return _post_audio_match(endpoint, audio_fp, AFP_DURATION, cookie, timeout)
        except NetEaseNoMatch as error:
            failures.append(f"offset={offset}: {error}")
    raise NetEaseNoMatch("; ".join(failures))


def _post_audio_match(endpoint, audio_fp, duration, cookie, timeout):
    data = {"duration": duration, "audioFP": audio_fp}
    if cookie:
        data["cookie"] = cookie
    response = requests.post(
        endpoint,
        params=data,
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    return _extract_match(payload)


def _extract_pcm(file, pcm_path, offset):
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            str(offset),
            "-i",
            file,
            "-t",
            str(AFP_DURATION),
            "-ac",
            "1",
            "-ar",
            str(AFP_SAMPLE_RATE),
            "-f",
            "f32le",
            pcm_path,
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _run_afp_generator(pcm_path):
    result = subprocess.run(
        ["node", AFP_GENERATOR, pcm_path],
        check=True,
        text=True,
        capture_output=True,
    )
    output = result.stdout.strip().splitlines()
    if not output:
        raise ValueError("NetEase AFP generator returned empty audioFP")
    return output[-1]


def _extract_match(payload):
    if not isinstance(payload, dict):
        raise ValueError("NetEase recognizer response must be a JSON object")
    match = _find_song_object(payload)
    if match is None:
        reason = _no_match_reason(payload)
        if reason is not None:
            raise NetEaseNoMatch(reason)
        if payload == {"code": 200}:
            raise ValueError(
                'NetEase recognizer returned only {"code": 200}. '
                "The NeteaseCloudMusicApi route accepted the request but did "
                "not return a matched song."
            )
        summary = pprint.pformat(payload, width=100, compact=True)
        raise ValueError(f"NetEase recognizer response has no song data: {summary}")
    return match


def _no_match_reason(payload):
    data = payload.get("data")
    if not isinstance(data, dict):
        return None
    if data.get("result") is not None:
        return None
    reason = data.get("noMatchReason")
    query_id = data.get("queryId")
    return f"noMatchReason={reason}, queryId={query_id}"


def _find_song_object(value):
    if isinstance(value, dict):
        if _looks_like_song(value):
            return value
        for key in ("song", "match", "simpleSong", "audio", "track"):
            match = _find_song_object(value.get(key))
            if match is not None:
                return match
        for key in ("songs", "matches", "result", "data"):
            match = _find_song_object(value.get(key))
            if match is not None:
                return match
    if isinstance(value, list):
        for item in value:
            match = _find_song_object(item)
            if match is not None:
                return match
    return None


class NetEaseNoMatch(ValueError):
    pass


class NetEaseRejectedMatch(ValueError):
    pass


def _looks_like_song(value):
    title = _first_optional_text(value, ("title", "name", "songName"))
    artist = _first_optional_text(value, ("artist", "artistName", "singer", "author"))
    return title is not None and artist is not None


def _first_text(payload, keys):
    value = _first_optional_text(payload, keys)
    if value is None:
        raise KeyError(f"missing required field: one of {', '.join(keys)}")
    return value


def _first_optional_text(payload, keys):
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if "artist" not in " ".join(keys).lower():
        return None
    artists = payload.get("artists") or payload.get("ar")
    if isinstance(artists, list) and artists:
        first = artists[0]
        if isinstance(first, dict):
            return _first_optional_text(first, ("name", "artistName"))
    return None
