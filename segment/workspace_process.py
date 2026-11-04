"""Isolated video processes with independent log and structured event streams."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from threading import Thread

from segment.events import EVENTS_ENV
from segment.music_agent.runtime import PROGRESS_PREFIX
from segment.upload_progress import UPLOAD_PREFIX
from segment.usage import EVENT_PREFIX
from segment.workspace_downloads import DOWNLOAD_PREFIX

READ_BYTES = 65536
STOP_TIMEOUT_SECONDS = 15
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_OPTION_NAMES = {
    "chunk_context_seconds": "CHUNK_CONTEXT",
    "boundary_context_seconds": "BOUNDARY_CONTEXT",
    "use_shazam": "SKIP_SHAZAM",
    "use_netease": "SKIP_NETEASE",
    "use_title_model": "NO_TITLE_MODEL",
}


def command_for(item: dict) -> list[str]:
    if item.get("download_config"):
        return [
            sys.executable,
            "-u",
            "-m",
            "segment.workspace_download",
            "--source-config",
            item["download_config"],
            "--outdir",
            item["outdir"],
        ]
    return [
        sys.executable,
        "-u",
        "-m",
        "segment.music_agent.cli",
        "--media",
        item["source_path"],
        "--outdir",
        item["outdir"],
    ]


def child_environment(job: dict, item: dict, *, event_fd: int, state_dir: Path) -> dict:
    options = {}
    for name, value in job["options"].items():
        if name.startswith("use_"):
            value = not value
        options["MUSIC_AGENT_" + ENV_OPTION_NAMES.get(name, name.upper())] = str(value).lower()
    return {
        **os.environ,
        **options,
        EVENTS_ENV: str(event_fd),
        "PYTHONIOENCODING": "utf-8",
        "MUSIC_AGENT_STATE_DIR": str(state_dir),
        "MUSIC_AGENT_JOB_ID": job["id"],
        "MUSIC_AGENT_SOURCE_DIGEST": item["sha256"],
        "MUSIC_AGENT_ATTEMPT": str(job["attempt"]),
    }


class ProcessRunner:
    def __init__(self, command=command_for):
        self.command = command

    def run(self, job: dict, item: dict, *, state_dir: Path, report, started) -> int:
        read_fd, write_fd = os.pipe()
        try:
            process = subprocess.Popen(
                self.command(item),
                cwd=PROJECT_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                env=child_environment(job, item, event_fd=write_fd, state_dir=state_dir),
                pass_fds=(write_fd,),
            )
        except Exception:
            os.close(read_fd)
            raise
        finally:
            os.close(write_fd)
        started(process)
        event_errors = []
        reader = Thread(target=_collect_events, args=(read_fd, report, event_errors))
        reader.start()
        try:
            with Path(item["log_path"]).open("ab") as log:
                source = getattr(process.stdout, "raw", process.stdout)
                while chunk := source.read(READ_BYTES):
                    log.write(chunk)
                    log.flush()
            returncode = process.wait()
            reader.join()
            if event_errors:
                raise RuntimeError("；".join(event_errors))
            return returncode
        finally:
            process.stdout.close()
            if process.poll() is None:
                stop_process(process)
            reader.join()


def _collect_events(fd: int, report, errors: list) -> None:
    prefixes = {
        PROGRESS_PREFIX: "progress",
        UPLOAD_PREFIX: "upload",
        EVENT_PREFIX: "usage",
        DOWNLOAD_PREFIX: "download",
    }
    try:
        with os.fdopen(fd, encoding="utf-8") as pipe:
            for line in pipe:
                for prefix, kind in prefixes.items():
                    if line.startswith(prefix):
                        report(kind, json.loads(line.removeprefix(prefix)))
                        break
    except Exception as error:
        errors.append(f"任务事件读取失败：{error}")


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=STOP_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
