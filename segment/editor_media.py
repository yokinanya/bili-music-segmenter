"""Disk-cached waveform peaks extracted incrementally from source audio."""

import array
import json
import re
import subprocess
import tempfile
from pathlib import Path
from threading import Lock

from segment.music_agent.manifest import atomic_write_json

SAMPLE_RATE = 8000
SAMPLES_PER_PEAK = 800
PCM_MAX = 32768
WAVEFORM_VERSION = 1
_CACHE_NAME = re.compile(r"waveform-[0-9a-f]{64}-v[0-9]+\.json")
_cache_lock = Lock()


def _waveform_files(cache: Path) -> list[Path]:
    return [path for path in cache.glob("waveform-*.json") if _CACHE_NAME.fullmatch(path.name) and path.is_file()]


def waveform_cache_bytes(cache: Path) -> int:
    with _cache_lock:
        return sum(path.stat().st_size for path in _waveform_files(cache))


def clear_waveforms(cache: Path) -> int:
    with _cache_lock:
        files = _waveform_files(cache)
        for path in files:
            path.unlink()
        return len(files)


def waveform(source: Path, cache: Path, digest: str) -> dict:
    with _cache_lock:
        return _waveform(source, cache, digest)


def _waveform(source: Path, cache: Path, digest: str) -> dict:
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
