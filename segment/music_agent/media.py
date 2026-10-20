"""Media probing and exact-cut ffmpeg helpers."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run_command(command: list[str]) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout.strip()


def media_duration(media: Path) -> float:
    return float(
        run_command(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media),
            ]
        )
    )


def make_windows(duration: float, chunk_seconds: int, context_seconds: int) -> list[tuple[float, float, float, float]]:
    if duration < 0 or chunk_seconds <= 0 or context_seconds < 0:
        raise ValueError("duration must be nonnegative, chunk_seconds positive and context nonnegative")
    windows = []
    core_start = 0.0
    while core_start < duration:
        core_end = min(duration, core_start + chunk_seconds)
        windows.append(
            (
                core_start,
                core_end,
                max(0.0, core_start - context_seconds),
                min(duration, core_end + context_seconds),
            )
        )
        core_start = core_end
    return windows


def extract_wav(media: Path, start: float, end: float, destination: Path) -> None:
    if start < 0 or end <= start:
        raise ValueError(f"invalid audio window {start}-{end}")
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
            "0:a:0",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "24000",
            "-c:a",
            "pcm_s16le",
            "-f",
            "wav",
            str(destination),
        ]
    )


def export_video(media: Path, start: float, end: float, destination: Path) -> None:
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
