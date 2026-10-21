"""Serialize structured child-process events across worker threads and processes.

The WebUI passes an event pipe as an inheritable file descriptor. On the first use the events
module takes private ownership of it: non-inheritable for ffmpeg and other subprocesses, and
removed from the environment so Python child processes cannot keep it open by accident.
"""

import json
import os
from threading import Lock

EVENTS_ENV = "MUSIC_AGENT_EVENTS_FD"
_EVENT_LOCK = Lock()
_private_fds: set[int] = set()


def emit_event(prefix: str, event: dict) -> None:
    """Write one event line to the dedicated pipe, never to stdout or the log stream."""
    fd = _event_fd()
    if fd is None:
        return
    line = (prefix + json.dumps(event) + "\n").encode("utf-8")
    with _EVENT_LOCK:
        try:
            os.write(fd, line)
        except OSError:
            # The reader is gone (WebUI stopped); reporting must never fail the actual work.
            return


def _event_fd() -> int | None:
    value = os.environ.get(EVENTS_ENV, "")
    if not value:
        return None
    try:
        fd = int(value)
    except ValueError:
        return None
    with _EVENT_LOCK:
        if fd not in _private_fds:
            try:
                os.set_inheritable(fd, False)
            except OSError:
                return None
            _private_fds.add(fd)
    return fd
