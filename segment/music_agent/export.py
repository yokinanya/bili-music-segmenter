"""Safe video export and filename sanitizing."""

from __future__ import annotations

import re
from pathlib import Path

from segment.music_agent.media_process import execute_media


def safe_component(value: str, fallback: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    return value or fallback


def export_video(media: Path, start: float, end: float, destination: Path) -> None:
    if end <= start:
        raise ValueError(f"invalid clip range {start}-{end}")
    execute_media(
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
        ],
        end - start,
    )
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"导出视频为空：{destination}")
