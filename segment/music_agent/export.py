"""Safe video export and collision-resistant filenames."""

from __future__ import annotations

import re
from pathlib import Path

from segment.music_agent.media import run_command


def safe_component(value: str, fallback: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    return value or fallback


def format_hms(seconds: float) -> str:
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}-{minutes:02d}-{seconds:02d}"


def export_video(media: Path, start: float, end: float, destination: Path) -> None:
    if end <= start:
        raise ValueError(f"invalid clip range {start}-{end}")
    run_command(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(media),
            "-t",
            f"{end - start:.3f}",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "24",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(destination),
        ]
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"导出视频为空：{destination}")


def make_clip_path(
    output_dir: Path,
    media_stem: str,
    candidate_index: int,
    start: float,
    end: float,
    title: str,
    artist: str,
) -> Path:
    labels = []
    if title:
        labels.append(safe_component(title, ""))
    if artist:
        labels.append(f"by {safe_component(artist, '')}")
    name_suffix = f"_{' '.join(labels)}" if labels else ""
    prefix = safe_component(media_stem, "media").encode("utf-8")[:60].decode("utf-8", errors="ignore")
    label = name_suffix.encode("utf-8")[:110].decode("utf-8", errors="ignore")
    stem = f"{prefix}_{candidate_index:02d}_{format_hms(start)}_{format_hms(end)}{label}"
    path = output_dir / f"{stem}.mp4"
    suffix = 2
    while path.exists():
        path = output_dir / f"{stem}_{suffix}.mp4"
        suffix += 1
    return path
