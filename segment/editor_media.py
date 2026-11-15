"""Disk-cached waveform peaks extracted incrementally from source audio."""

import array
import json
import subprocess
import tempfile
from pathlib import Path

from segment.music_agent.manifest import atomic_write_json

SAMPLE_RATE = 8000
SAMPLES_PER_PEAK = 800
PCM_MAX = 32768
WAVEFORM_VERSION = 1


def waveform(source: Path, cache: Path, digest: str) -> dict:
    destination = cache / f"waveform-{digest}-v{WAVEFORM_VERSION}.json"
    if destination.is_file():
        return json.loads(destination.read_text(encoding="utf-8"))
    cache.mkdir(parents=True, exist_ok=True)
    peaks = _extract_peaks(source)
    if not peaks:
        raise RuntimeError("waveform: source contains no audio samples")
    result = {"seconds_per_peak": SAMPLES_PER_PEAK / SAMPLE_RATE, "peaks": peaks}
    atomic_write_json(destination, result)
    return result


def _extract_peaks(source: Path) -> list[float]:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "s16le",
        "pipe:1",
    ]
    peaks = []
    with tempfile.TemporaryFile() as errors:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors) as process:
            while block := process.stdout.read(SAMPLES_PER_PEAK * 2):
                samples = array.array("h", block)
                peaks.append(round(max(abs(value) for value in samples) / PCM_MAX, 5))
            process.stdout.close()
            if process.wait() != 0:
                errors.seek(0)
                raise RuntimeError("waveform: " + errors.read().decode("utf-8", errors="replace"))
    return peaks
