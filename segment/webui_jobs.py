"""Validate WebUI requests and execute the existing CLI in child processes."""

from __future__ import annotations

import codecs
import json
import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4

from segment.events import EVENTS_ENV
from segment.logs import job_log_path
from segment.upload_progress import UPLOAD_PREFIX, UploadProgress
from segment.usage import EVENT_PREFIX, UsageTotals
from segment.webui_history import JobHistory

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INPUT_DIR_NAME = "input"
# Only these extensions are offered and accepted; anything else in input/ is ignored.
MEDIA_SUFFIXES = (
    ".mp4",
    ".mkv",
    ".flv",
    ".ts",
    ".mov",
    ".m4v",
    ".webm",
    ".mp3",
    ".m4a",
    ".aac",
    ".wav",
    ".flac",
    ".ogg",
)
DEFAULT_MAX_JOBS = 2
READER_JOIN_SECONDS = 15
EVENT_READ_SIZE = 65536
LOG_READ_SIZE = 65536
CONTAINER_INPUT_DIR = Path("/input")
# Resolved on every call so tests can point the input directory elsewhere.
input_root = PROJECT_ROOT


class JobLimitReached(RuntimeError):
    """Raised when too many jobs are still running or waiting to be collected."""


def input_dir() -> Path:
    """Fixed input directory; the WebUI only ever processes media placed here."""
    if CONTAINER_INPUT_DIR.is_dir():
        return CONTAINER_INPUT_DIR
    return input_root / INPUT_DIR_NAME


def list_inputs() -> list[dict]:
    """Media files currently available in the input directory, sorted for a stable UI."""
    directory = input_dir()
    if not directory.is_dir():
        return []
    files = sorted(
        (path for path in directory.iterdir() if path.is_file() and path.suffix.lower() in MEDIA_SUFFIXES),
        key=lambda path: path.name.casefold(),
    )
    return [{"name": path.name, "size_bytes": path.stat().st_size} for path in files]


def build_command(payload: dict) -> list[str]:
    """Accept ``media`` (one name) or ``media`` (list of names), restricted to the input directory."""
    if payload.keys() - {"media", "outdir"}:
        raise ValueError("包含未知参数")
    media = _input_path(payload, "media")
    outdir = _absolute_path(payload, "outdir")
    if outdir.exists() and not outdir.is_dir():
        raise ValueError("输出路径必须是目录")
    return [sys.executable, "-u", "-m", "segment.music_agent.cli", "--media", str(media), "--outdir", str(outdir)]


def build_batch(payload: dict) -> list[list[str]]:
    """Command per media file; the caller runs them one after another."""
    names = payload.get("media")
    items = names if isinstance(names, list) else [names]
    if not items:
        raise ValueError("请至少选择一个输入文件")
    commands = []
    for name in items:
        commands.append(build_command({"media": name, "outdir": payload.get("outdir")}))
    if len({command[command.index("--media") + 1] for command in commands}) != len(commands):
        raise ValueError("输入文件重复")
    return commands


def _input_path(payload: dict, name: str) -> Path:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不能为空")
    candidate = Path(value.strip())
    if candidate.name != value.strip() or candidate.is_absolute() or value.strip() in {".", ".."}:
        # Only a bare file name is accepted, so a crafted value cannot escape the input directory.
        raise ValueError("只能选择输入目录 input/ 中的文件名")
    directory = input_dir().resolve()
    media = (directory / candidate.name).resolve()
    if media.parent != directory:
        raise ValueError("只能选择输入目录 input/ 中的文件名")
    if not media.is_file():
        raise ValueError(f"输入目录中没有该文件：{candidate.name}")
    if media.suffix.lower() not in MEDIA_SUFFIXES:
        raise ValueError(f"不支持的媒体格式：{media.suffix}")
    return media


def _absolute_path(payload: dict, name: str) -> Path:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} 不能为空")
    path = Path(value.strip()).expanduser()
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


@dataclass
class Item:
    """One media file of a job; a single-file job simply has one item."""

    media: str
    log_path: Path
    state: str = "pending"
    returncode: int | None = None
    usage: UsageTotals = field(default_factory=UsageTotals)
    upload: UploadProgress = field(default_factory=UploadProgress)
    errors: list[str] = field(default_factory=list)
    log_errors: list[str] = field(default_factory=list)
    log_parts: list[str] = field(default_factory=list)
    process: subprocess.Popen | None = None
    reader: Thread | None = None


@dataclass
class Job:
    """A batch: its files run sequentially so one job never multiplies cloud concurrency."""

    outdir: Path
    items: list[Item]
    usage: UsageTotals = field(default_factory=UsageTotals)
    upload: UploadProgress = field(default_factory=UploadProgress)
    errors: list[str] = field(default_factory=list)
    stopped: bool = False
    runner: Thread | None = None
    started_at: str = ""
    finished_at: str = ""


class Jobs:
    def __init__(
        self,
        command_builder: Callable[[dict], list[str]],
        *,
        max_jobs: int = DEFAULT_MAX_JOBS,
        usage: UsageTotals | None = None,
        history: JobHistory | None = None,
    ) -> None:
        self._command_builder = command_builder
        self.max_jobs = max_jobs
        self.history = history or JobHistory()
        self._max_jobs = max_jobs
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        # All jobs of one WebUI process report into the same totals unless a caller injects its own.
        self.usage = usage if usage is not None else UsageTotals()

    def start(self, payload: dict) -> str:
        """Run every file named by ``payload["media"]``; the builder returns one command per file."""
        built = self._command_builder(payload)
        if not built:
            raise ValueError("命令构建器未返回任何命令")
        # A builder may return one command or a list of commands; both describe the same batch size.
        commands = built if isinstance(built[0], list) else [built]
        labels = _media_names(payload)
        if len(commands) != len(labels):
            raise ValueError("命令数量与输入文件数量不一致")
        outdir = _absolute_path(payload, "outdir")
        with self._lock:
            running = sum(job.runner is not None and job.runner.is_alive() for job in self._jobs.values())
            if running >= self._max_jobs:
                raise JobLimitReached(f"同时最多运行 {self._max_jobs} 个任务，请等待当前任务结束")
        outdir.mkdir(parents=True, exist_ok=True)
        job_id = uuid4().hex
        items = []
        for label in labels:
            log_path = job_log_path(f"{job_id}-{_safe_stem(Path(label).stem)}")
            log_path.touch()
            items.append(Item(label, log_path))
        job = Job(outdir, items, started_at=datetime.now().isoformat(timespec="seconds"))
        with self._lock:
            self._jobs[job_id] = job
        job.runner = Thread(target=self._run_batch, args=(job, commands), daemon=True)
        job.runner.start()
        return job_id

    def status(self, job_id: str) -> dict:
        with self._lock:
            job = self._jobs[job_id]
        running = job.runner is not None and job.runner.is_alive()
        # A file killed on purpose by the user is stopped, not failed.
        failed = [] if job.stopped else [item for item in job.items if item.state == "failed"]
        cancelled = job.stopped and any(item.state in {"failed", "cancelled"} for item in job.items)
        settled = all(item.state not in {"pending", "running"} for item in job.items)
        if running or not settled:
            state = "running"
        elif failed:
            state = "failed"
        elif cancelled:
            state = "cancelled"
        else:
            state = "succeeded"
        # The item list is only final once the runner thread has exited; report both.
        with self._lock:
            batch = [_batch_item(job, item) for item in job.items]
        if state != "running" and job.finished_at:
            self.history.record(_history_entry(job_id, job, state, batch))
        return {
            "state": state,
            "batch_complete": job.runner is not None and not job.runner.is_alive(),
            "usage": job.usage.snapshot(),
            "upload": job.upload.snapshot(),
            "accounting_errors": list(job.errors),
            "returncode": next((_item_returncode(item) for item in failed), 0),
            "log": "".join("".join(item.log_parts) for item in job.items),
            "log_complete": not running,
            "log_path": str(job.items[-1].log_path) if job.items else "",
            "outdir": str(job.outdir),
            "clips": _exported_clips(job.outdir),
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "media": job.items[0].media if len(job.items) == 1 else "",
            "batch": batch,
        }

    def log_chunk(self, job_id: str, item_index: int, offset: int) -> dict:
        """Return the log tail after ``offset`` for one batch item, plus the offset to send next."""
        with self._lock:
            job = self._jobs[job_id]
            if not 0 <= item_index < len(job.items):
                raise IndexError(item_index)
            item = job.items[item_index]
            text = "".join(item.log_parts)
            running = item.state == "running"
        return {"text": text[offset:], "offset": len(text), "running": running, "state": item.state}

    def clip_path(self, job_id: str, name: str) -> Path | None:
        """Resolve a clip of this job by file name, refusing anything outside its exported clips."""
        with self._lock:
            job = self._jobs[job_id]
        for clip in _exported_clips(job.outdir):
            if clip["name"] == name:
                path = Path(clip["path"])
                return path if path.is_file() else None
        return None

    def stop_current(self, job_id: str) -> None:
        """Stop the file being processed and skip the rest of the batch; finished files keep their clips."""
        with self._lock:
            job = self._jobs[job_id]
            job.stopped = True
            current = next((item for item in job.items if item.state == "running"), None)
        if current is not None and current.process is not None:
            _stop(current.process)

    def _run_batch(self, job: Job, commands: list[list[str]]) -> None:
        for item, command in zip(job.items, commands, strict=True):
            if job.stopped:
                item.state = "cancelled"
                continue
            self._run_item(job, item, command)
        job.finished_at = datetime.now().isoformat(timespec="seconds")

    def _run_item(self, job: Job, item: Item, command: list[str]) -> None:
        event_read, event_write = os.pipe()
        try:
            process = subprocess.Popen(
                command,
                cwd=PROJECT_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                env=_child_environment(event_write),
                pass_fds=(event_write,),
            )
        finally:
            os.close(event_write)
        item.process = process
        item.state = "running"
        item.returncode = None
        item.reader = Thread(target=self._collect, args=(job, item, event_read), daemon=True)
        item.reader.start()
        item.reader.join()
        # poll() blocks until the exit status is collected, so this is the authoritative code.
        returncode = process.poll()
        if returncode is None:
            returncode = process.wait()
        item.returncode = returncode
        if returncode == 0:
            item.state = "succeeded"
        elif job.stopped:
            # The user asked to stop: this file was terminated, not broken.
            item.state = "cancelled"
        else:
            item.state = "failed"

    def close(self) -> None:
        with self._lock:
            jobs = tuple(self._jobs.values())
        for job in jobs:
            job.stopped = True
            for item in job.items:
                if item.process is not None:
                    _stop(item.process)
            if job.runner is not None:
                job.runner.join(timeout=READER_JOIN_SECONDS)
            for item in job.items:
                if item.reader is not None:
                    item.reader.join(timeout=READER_JOIN_SECONDS)

    def _collect(self, job: Job, item: Item, event_fd: int) -> None:
        if item.process is None:
            raise RuntimeError("任务进程未启动")
        reporter = Thread(target=_read_events, args=(job, item, event_fd, self.usage), daemon=True)
        reporter.start()
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        try:
            with item.log_path.open("wb") as log:
                for chunk in _read_chunks(item.process.stdout):
                    log.write(chunk)
                    log.flush()
                    text = decoder.decode(chunk)
                    if text:
                        item.log_parts.append(text)
                text = decoder.decode(b"", final=True)
                if text:
                    item.log_parts.append(text)
        except OSError as exc:
            item.log_errors.append(f"日志写入失败：{exc}")
            job.errors.append(f"{item.media}：{exc}")
        finally:
            item.process.stdout.close()
            reporter.join()


def _media_names(payload: dict) -> list[str]:
    """Media names as declared by the request; a missing name still yields one item per command."""
    names = payload.get("media")
    values = names if isinstance(names, list) else [names]
    names_out = [Path(str(value)).name for value in values if value]
    return names_out or ["job"]


def _history_entry(job_id: str, job: Job, state: str, batch: list[dict]) -> dict:
    return {
        "id": job_id,
        "state": state,
        "started_at": job.started_at,
        "outdir": str(job.outdir),
        "medias": [item["media"] for item in batch],
        "clip_count": sum(item["clip_count"] for item in batch),
        "usage": job.usage.snapshot(),
    }


def _batch_item(job: Job, item: Item) -> dict:
    return {
        "media": item.media,
        "state": item.state,
        "returncode": _item_returncode(item),
        "log_path": str(item.log_path),
        "clip_count": _clip_count(job.outdir, Path(item.media).stem),
    }


def _item_returncode(item: Item) -> int | None:
    """Prefer the live process status; the worker thread stores the same value once it joins."""
    if item.process is not None and item.process.poll() is not None:
        return item.process.returncode
    return item.returncode


def _clip_count(outdir: Path, media_stem: str) -> int:
    """Clips of one media file, attributed by that file's own manifest rather than by name."""
    return len(_exported_clips(outdir, manifest_name=f"{media_stem}_music_agent.json"))


def _safe_stem(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return cleaned.strip("_") or "media"


def _exported_clips(outdir: Path, manifest_name: str | None = None) -> list[dict]:
    """Read already exported clips from the manifest the agent rewrites after every export."""
    clips: list[dict] = []
    pattern = manifest_name or "*_music_agent.json"
    for manifest in sorted(outdir.glob(pattern)):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for record in data.get("candidates") or []:
            for interval in record.get("singing_intervals") or []:
                clip = _clip(interval)
                if clip:
                    clips.append(clip)
    return clips


def _clip(interval: dict) -> dict | None:
    try:
        path = Path(interval["file"])
        duration = float(interval["end_seconds"]) - float(interval["start_seconds"])
    except (KeyError, TypeError, ValueError):
        return None
    return {
        "name": path.name,
        "path": str(path),
        "title": interval.get("title") or "",
        "artist": interval.get("artist") or "",
        "duration_seconds": round(duration, 1),
    }


def _read_chunks(stream, size: int = LOG_READ_SIZE) -> Iterator[bytes]:
    """Read from the raw pipe in bounded chunks; incremental decoding keeps split characters intact."""
    buffer = getattr(stream, "raw", stream)
    while chunk := buffer.read(size):
        yield chunk


def _read_events(job: Job, item: Item, fd: int, service_usage: UsageTotals) -> None:
    decoder = codecs.getincrementaldecoder("utf-8")()
    buffered = ""

    def consume(text: str) -> None:
        nonlocal buffered
        *lines, buffered = (buffered + text).split("\n")
        for line in lines:
            _handle_event(job, item, line, service_usage)

    try:
        with os.fdopen(fd, "rb", closefd=True) as pipe:
            while chunk := pipe.read(EVENT_READ_SIZE):
                consume(decoder.decode(chunk))
        consume(decoder.decode(b"", final=True))
        if buffered:
            _handle_event(job, item, buffered, service_usage)
    except OSError as exc:
        item.errors.append(f"事件读取失败：{exc}")


def _handle_event(job: Job, item: Item, line: str, service_usage: UsageTotals) -> None:
    if line.startswith(UPLOAD_PREFIX):
        try:
            event = json.loads(line.removeprefix(UPLOAD_PREFIX))
            item.upload.update(event)
            job.upload.update(event)
        except (ValueError, KeyError, TypeError) as exc:
            item.errors.append(f"上传进度解析失败：{exc}")
        return
    if not line.startswith(EVENT_PREFIX):
        return
    try:
        event = json.loads(line.removeprefix(EVENT_PREFIX))
        item.usage.add(event)
        job.usage.add(event)
        service_usage.add(event)
    except (ValueError, KeyError, TypeError) as exc:
        item.errors.append(f"用量收集失败：{exc}")


def _stop(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _child_environment(event_fd: int) -> dict[str, str]:
    return {**os.environ, "PYTHONIOENCODING": "utf-8", EVENTS_ENV: str(event_fd)}
