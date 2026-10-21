"""Single place that decides where run logs live.

All logs go to one dedicated directory at the project root (or ``/logs`` when the container
provides it) instead of being scattered next to the output clips. Filenames carry the date so
each day starts a new file instead of growing one forever.
"""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTAINER_LOG_DIR = Path("/logs")
LOG_DIRECTORY_NAME = "logs"
LOG_FORMAT = "%(asctime)s %(levelname)s %(message)s"
# Resolved on every call so callers (including tests) can redirect logs without restarting.
log_root = PROJECT_ROOT


def log_dir() -> Path:
    """Return the log directory, preferring the container mount when it is present."""
    if CONTAINER_LOG_DIR.is_dir():
        return CONTAINER_LOG_DIR
    return log_root / LOG_DIRECTORY_NAME


def job_log_path(job_id: str, *, today: date | None = None) -> Path:
    """Per-job WebUI log; the date separates runs and the job id separates concurrent jobs."""
    return _ensure(log_dir()) / f"webui-{_date(today)}-{job_id}.log"


def agent_log_path(media: Path, *, started: datetime | None = None) -> Path:
    """Per-run processing log for direct CLI usage, dated and named after the media."""
    moment = started or datetime.now()
    return _ensure(log_dir()) / f"music-agent-{_date(moment.date())}-{_safe(media.stem)}.log"


def server_log_path(*, today: date | None = None) -> Path:
    """WebUI service log, one file per day."""
    return _ensure(log_dir()) / f"webui-server-{_date(today)}.log"


def inaseg_log_path(*, today: date | None = None) -> Path:
    """Local detection log, one file per day."""
    return _ensure(log_dir()) / f"inaseg-{_date(today)}.log"


def configure_logging(level: int, *, log_file: Path | None = None) -> None:
    """Log to the console and, when a file is given, also write the same records to it."""
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        _ensure(log_file.parent)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(level=level, format=LOG_FORMAT, handlers=handlers, force=True)


def _date(value: date | None) -> str:
    return (value or date.today()).strftime("%Y%m%d")


def _ensure(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _safe(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return cleaned.strip("_") or "media"
