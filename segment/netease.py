import json
import math
import os
import pprint
import re
import subprocess
import tempfile
import time
import unicodedata
from collections.abc import Iterable

from segment.shazam import legalize_filename

DEFAULT_TIMEOUT = 60
AFP_DURATION = 3
# 从切片开头取样。实测从开头取点比从中间取稳定：中段会采到间奏与临近音频，混入翻唱/伴奏版本。
AFP_OFFSETS = (6, 12, 20, 30)
AFP_SAMPLE_RATE = 8000
DEFAULT_REJECTS = (("劫", "黄霄雲"),)
AFP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "vendor", "ncm-afp")
AFP_GENERATOR = os.path.join(AFP_DIR, "generate_fp.js")
MATCH_SCRIPT = os.path.join(AFP_DIR, "audio_match.js")


def netease_title(match):
    title = _first_text(match, ("title", "name", "songName"))
    artist = _first_text(match, ("artist", "artistName", "singer", "author"))
    return [legalize_filename(title), legalize_filename(artist)]


def probe_duration(file):
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file),
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    return float(result.stdout.strip())


def sample_offsets(duration, offsets=AFP_OFFSETS):
    """丢弃超出切片或与上一采样窗口重叠的起点，保证每个采样听到的是不同音频。"""
    if duration < AFP_DURATION:
        return ()
    points = []
    for offset in parse_offsets(offsets):
        if 0 <= offset <= duration - AFP_DURATION:
            points.append(offset)
    ordered = sorted(set(points))
    # 相邻采样窗口重叠会让多个点实际上听的是同一段音频，投票就失去意义。
    spaced = []
    for item in ordered:
        if not spaced or item - spaced[-1] >= AFP_DURATION:
            spaced.append(item)
    return tuple(spaced)


# 只有明确的版本附注才算同一作品；单字「版」「款」太宽泛，会误删「温柔版」这类真实歌名。
VARIANT_WORDS = (
    "cover",
    "翻自",
    "翻唱",
    "伴奏",
    "纯享",
    "纯音乐",
    "instrumental",
    "inst",
    "remix",
    "live",
    "原版",
    "伴奏版",
    "现场版",
    "重制版",
    "完整版",
    "纯享版",
    "版本",
)
_BRACKETS = re.compile(r"[（(\[【]([^（()）\[\]【】]*)[）)\]】]")
_DASH_SUFFIX = re.compile(r"\s+-\s+.*$")


def netease_match_key(match):
    """同一作品常有 cover/伴奏/纯享版等版本，投票只按归一化歌名归并，艺人差异不拆分票。"""
    title, _ = netease_title(match)
    return normalize_song_text(variant_free(title))


def variant_free(title):
    """去掉版本附注，只保留歌名主体；歌名自身的括号内容保留。"""
    text = title.strip().strip("《》\"“”'’ ")
    # 只去掉含有版本词的括号，歌名自身括号内的内容保留。
    text = _BRACKETS.sub(
        lambda m: " " if any(word in m.group(1).casefold() for word in VARIANT_WORDS) else m.group(0), text
    )
    return _DASH_SUFFIX.sub("", text)


def normalize_song_text(value):
    return "".join(char for char in unicodedata.normalize("NFKC", value).casefold() if char.isalnum())


def vote_match(matches):
    """得票最多者胜出；平票无法判断时返回 None，交给人工在界面选择。"""
    tally = {}
    for match in matches:
        key = netease_match_key(match)
        if key:
            tally.setdefault(key, []).append(match)
    if not tally:
        return None
    groups = sorted(tally.values(), key=len, reverse=True)
    # 两个不同作品票数相同说明采样点各自听到了不同歌曲，不能替模型挑一个。
    if len(groups) > 1 and len(groups[0]) == len(groups[1]):
        return None
    return groups[0][0]


def netease_orig(
    file,
    *,
    duration=None,
    cookie="",
    offsets=AFP_OFFSETS,
    rejects=DEFAULT_REJECTS,
    timeout=DEFAULT_TIMEOUT,
    deadline=None,
):
    if duration is None:
        duration = probe_duration(file)
    match = _recognize_with_offsets(
        file, duration=duration, cookie=cookie, offsets=offsets, timeout=timeout, deadline=deadline
    )
    title = netease_title(match)
    _raise_if_rejected(title, rejects)
    return title, match


def generate_audio_fp(file, offset):
    with tempfile.TemporaryDirectory(prefix="netease-afp-") as directory:
        pcm_path = os.path.join(directory, "audio.f32le")
        _extract_pcm(file, pcm_path, offset)
        return _run_afp_generator(pcm_path)


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
            raise NetEaseRejectedMatch(f"NetEase rejected known bad match: {title_text} by {artist_text}")


class NetEaseDisagreement(ValueError):
    """多个采样点给出不同作品；不能假装其中一个是正确答案。"""

    def __init__(self, groups):
        self.groups = groups
        super().__init__("；".join(f"offset={offset}: {title}/{artist}" for offset, title, artist in groups))


def _recognize_with_offsets(file, *, duration, cookie, offsets, timeout, deadline=None):
    points = sample_offsets(duration, offsets)
    if not points:
        raise ValueError(f"识曲音频 {duration:.1f} 秒短于一个 {AFP_DURATION} 秒采样窗口")
    matches, collected, reasons = [], [], []
    errors: list[Exception] = []
    started = time.monotonic()
    for index, point in enumerate(points):
        # 单点超时不是总时限：按剩余时间裁剪，用尽后跳过剩余采样点，沿用已有多数结果。
        remaining = None if deadline is None else deadline - (time.monotonic() - started)
        if remaining is not None and remaining <= 0:
            reasons.append(f"skipped {len(points) - index} samples: deadline={deadline:.0f}s")
            break
        limit = timeout if remaining is None else min(timeout, remaining)
        try:
            audio_fp = generate_audio_fp(file, point)
            match = _post_audio_match(audio_fp, duration=AFP_DURATION, cookie=cookie, timeout=limit)
        except NetEaseNoMatch as error:
            reasons.append(f"offset={point}: {error}")
            continue
        except Exception as error:
            # 单点网络抖动或子进程失败不能毁掉整首歌，其余采样点仍可投票。
            errors.append(error)
            reasons.append(f"offset={point}: {type(error).__name__}: {error}")
            continue
        matches.append(match)
        collected.append((point, *netease_title(match)))
    # 不同起点可能听到不同录音，按多数决取一致的候选；平票标记冲突，交给人工选择。
    winner = vote_match(matches)
    if winner is None:
        if matches:
            raise NetEaseDisagreement(collected)
        if errors:
            raise RuntimeError("；".join(reasons)) from errors[0]
        raise NetEaseNoMatch("; ".join(reasons))
    return winner


def _post_audio_match(audio_fp, *, duration, cookie, timeout):
    # 整体时限裁剪会产生小数秒，而 Node 的 AbortSignal.timeout 只接受整数毫秒。
    seconds = max(1, math.ceil(timeout))
    result = _run_node(
        [MATCH_SCRIPT],
        input=json.dumps({"audioFP": audio_fp, "duration": duration, "cookie": cookie, "timeout": seconds}),
        what="网易云音频匹配",
        timeout=seconds,
    )
    return _extract_match(json.loads(result.stdout))


def _run_node(args, *, input=None, what, timeout=None):
    """Node 子进程失败时带上它自己的 stderr；单独的命令行和退出码对用户没有意义。"""
    try:
        return subprocess.run(
            ["node", *args],
            input=input,
            check=True,
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or "").strip().splitlines()
        raise RuntimeError(f"{what}失败：{detail[-1] if detail else f'退出码 {error.returncode}'}") from error
    except subprocess.TimeoutExpired as error:
        raise RuntimeError(f"{what}超时：{timeout} 秒内未返回") from error


def _extract_pcm(file, pcm_path, offset):
    from segment.music_agent.media_process import execute_media

    execute_media(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
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
        AFP_DURATION,
    )


def _run_afp_generator(pcm_path):
    result = _run_node([AFP_GENERATOR, pcm_path], what="网易云指纹生成")
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
