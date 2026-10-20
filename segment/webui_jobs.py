"""Validate WebUI requests and execute the existing CLI in child processes."""

from __future__ import annotations

import codecs
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from segment.upload_progress import UPLOAD_PREFIX, UploadProgress
from segment.usage import EVENT_PREFIX, UsageTotals

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_command(payload: dict) -> list[str]:
    allowed = {"media", "outdir"}
    if payload.keys() - allowed:
        raise ValueError("包含未知参数")
    media = _required_path(payload, "media")
    outdir = _required_path(payload, "outdir")
    if not media.is_file():
        raise ValueError(f"输入文件不存在：{media}")
    if outdir.exists() and not outdir.is_dir():
        raise ValueError("输出路径必须是目录")
    command = [sys.executable, "-u", "-m", "segment.music_agent.cli", "--media", str(media), "--outdir", str(outdir)]
    return command


def _required_path(payload: dict, name: str) -> Path:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不能为空")
    path = Path(value.strip()).expanduser()
    return (PROJECT_ROOT / path).resolve()


@dataclass(frozen=True)
class Job:
    process: subprocess.Popen
    log_path: Path
    outdir: Path
    usage: UsageTotals
    reader: Thread
    errors: list[str]
    upload: UploadProgress


class Jobs:
    def __init__(self, command_builder: Callable[[dict], list[str]]) -> None:
        self._command_builder = command_builder
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self.usage = UsageTotals()

    def start(self, payload: dict) -> str:
        command = self._command_builder(payload)
        outdir = _required_path(payload, "outdir")
        outdir.mkdir(parents=True, exist_ok=True)
        job_id = uuid4().hex
        log_path = outdir / f"webui-{job_id}.log"
        log_path.touch()
        process = subprocess.Popen(
            command,
            cwd=PROJECT_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=_child_environment(),
        )
        usage = UsageTotals()
        errors: list[str] = []
        upload = UploadProgress()
        reader = Thread(target=self._collect, args=(process, (log_path, usage, errors, upload)), daemon=True)
        with self._lock:
            self._jobs[job_id] = Job(process, log_path, outdir, usage, reader, errors, upload)
        reader.start()
        return job_id

    def status(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs[job_id]
        returncode = job.process.poll()
        if returncode is not None:
            job.reader.join()
        state = "running" if returncode is None else "succeeded" if returncode == 0 else "failed"
        return {
            "state": state,
            "usage": job.usage.snapshot(),
            "upload": job.upload.snapshot(),
            "accounting_errors": list(job.errors),
            "returncode": returncode,
            "log": codecs.getincrementaldecoder("utf-8")().decode(
                job.log_path.read_bytes(), final=returncode is not None
            ),
            "log_path": str(job.log_path),
            "outdir": str(job.outdir),
        }

    def close(self) -> None:
        with self._lock:
            jobs = tuple(self._jobs.values())
        for job in jobs:
            if job.process.poll() is None:
                job.process.terminate()
            job.process.wait()
            job.reader.join()

    def _collect(self, process, collection: tuple) -> None:
        log_path, usage, errors, upload = collection
        try:
            with log_path.open("wb") as log:
                while line := process.stdout.readline():
                    if line.startswith(UPLOAD_PREFIX.encode()):
                        upload.update(json.loads(line[len(UPLOAD_PREFIX) :]))
                        continue
                    if not line.startswith(EVENT_PREFIX.encode()):
                        log.write(line)
                        log.flush()
                        continue
                    try:
                        event = json.loads(line[len(EVENT_PREFIX) :])
                        usage.add(event)
                        self.usage.add(event)
                    except (ValueError, KeyError, TypeError) as exc:
                        errors.append(f"用量收集失败：{exc}")
        except OSError as exc:
            errors.append(f"日志读取失败：{exc}")
        finally:
            process.stdout.close()


def _child_environment() -> dict[str, str]:
    return {**os.environ, "PYTHONIOENCODING": "utf-8", "MUSIC_AGENT_USAGE_EVENTS": "1"}
