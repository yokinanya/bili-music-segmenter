"""Streaming FFmpeg execution with measured progress and one shared CPU budget."""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar

from segment.music_agent.runtime import CURRENT, PROGRESS_INTERVAL_SECONDS, fingerprint

MICROSECONDS_PER_SECOND = 1_000_000
AUTOMATIC_THREADS = 0
MEDIA_PROGRESS: ContextVar[Callable | None] = ContextVar("media_progress", default=None)


@contextmanager
def reporting_media(progress: Callable):
    token = MEDIA_PROGRESS.set(progress)
    try:
        yield
    finally:
        MEDIA_PROGRESS.reset(token)


def execute_media(command: list[str], duration: float) -> None:
    scope = CURRENT.get()
    budget = scope.runtime.resource("media") if scope else nullcontext()
    threads = scope.runtime.config["media_threads"] if scope else AUTOMATIC_THREADS
    invocation = [command[0], "-progress", "pipe:1", "-nostats", "-threads", str(threads), *command[1:]]
    # FFmpeg's output codec also needs an explicit thread budget.
    invocation[-1:-1] = ["-threads", str(threads)]
    with budget:
        with subprocess.Popen(invocation, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            _read_progress(process, duration, command)


def _read_progress(process, duration: float, command: list[str]) -> None:
    from threading import Thread

    errors: list[str] = []
    reader = Thread(target=lambda: errors.extend(process.stderr.readlines()))
    reader.start()
    last = 0.0
    started = time.monotonic()
    scope = CURRENT.get()
    progress = MEDIA_PROGRESS.get()
    identity = "media/" + fingerprint(command)
    label = "导出片段" if "libx264" in command else "提取音频"
    for line in process.stdout:
        key, _, value = line.strip().partition("=")
        if key != "out_time_us" or value == "N/A":
            continue
        elapsed = time.monotonic()
        if elapsed - last >= PROGRESS_INTERVAL_SECONDS:
            completed = min(duration, max(0, int(value) / MICROSECONDS_PER_SECOND))
            if progress:
                progress(
                    {
                        "stage": "encoding",
                        "completed_seconds": completed,
                        "total_seconds": duration,
                        "elapsed_seconds": elapsed - started,
                    }
                )
            if scope:
                scope.runtime.event(identity, label, completed=completed, total=duration, unit="秒")
            last = elapsed
    returncode = process.wait()
    reader.join()
    if returncode:
        if scope:
            scope.runtime.event(identity, label, state="failed", error="".join(errors))
        raise subprocess.CalledProcessError(returncode, command, stderr="".join(errors))
    if scope:
        scope.runtime.event(identity, label, state="succeeded", completed=duration, total=duration, unit="秒")
