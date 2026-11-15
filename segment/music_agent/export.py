"""Safe video export and filename sanitizing."""

from __future__ import annotations

import re
from pathlib import Path

from segment.music_agent.media import reencode_cut_command
from segment.music_agent.media_process import execute_media


def safe_component(value: str, fallback: str) -> str:
    value = re.sub(r'[\\/:*?"<>|\x00-\x1f]', " ", value).strip(" .")
    value = re.sub(r"\s+", " ", value)
    return value or fallback


def export_video(media: Path, start: float, end: float, destination: Path) -> None:
    if end <= start:
        raise ValueError(f"invalid clip range {start}-{end}")
    execute_media(reencode_cut_command(media, start, end, destination), end - start)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise RuntimeError(f"导出视频为空：{destination}")
