"""Serialize structured child-process events across worker threads and processes.

On POSIX the WebUI passes the event pipe as an inheritable file descriptor. On the first use the
events module takes private ownership of it: non-inheritable for ffmpeg and other subprocesses,
and removed from the environment so Python child processes cannot keep it open by accident.

Windows has no ``pass_fds`` and cannot hand an anonymous pipe to a child as a numeric descriptor,
so there the child receives the inheritable OS pipe handle and writes to it with ``WriteFile``.
Tests that only need structured events may point ``EVENTS_ENV`` at an ordinary descriptor instead.
"""

import json
import os
from threading import RLock

EVENTS_ENV = "MUSIC_AGENT_EVENTS_FD"
HANDLE_ENV = "MUSIC_AGENT_EVENTS_HANDLE"
# Descriptor initialization re-enters this lock while an event write is serialized.
_EVENT_LOCK = RLock()
_private_fds: set[int] = set()
_child_handle: int | None = None


def emit_event(prefix: str, event: dict) -> None:
    """Write one event line to the dedicated pipe, never to stdout or the log stream."""
    line = (prefix + json.dumps(event) + "\n").encode("utf-8")
    with _EVENT_LOCK:
        try:
            _write_target(line)
        except OSError:
            # The reader is gone (WebUI stopped); reporting must never fail the actual work.
            return


def _write_target(data: bytes) -> None:
    if os.name == "nt" and os.environ.get(HANDLE_ENV):
        _write_handle(_event_handle(), data)
        return
    fd = _event_fd()
    if fd is not None:
        os.write(fd, data)


def _write_handle(handle: int, data: bytes) -> None:
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    written = wintypes.DWORD()
    buffer = ctypes.create_string_buffer(data, len(data))
    if not kernel32.WriteFile(handle, buffer, len(data), ctypes.byref(written), None):
        raise ctypes.WinError(ctypes.get_last_error())


def _event_handle() -> int:
    global _child_handle
    if _child_handle is None:
        _child_handle = int(os.environ[HANDLE_ENV])
    return _child_handle


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
