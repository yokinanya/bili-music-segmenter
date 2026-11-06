"""Parent side of the child-process event pipe for the sequential job runner."""

from __future__ import annotations

import os
from dataclasses import dataclass

from segment.events import EVENTS_ENV, HANDLE_ENV


@dataclass(frozen=True)
class EventPipe:
    """Read end for the parent and the value the child uses to report events."""

    read_end: int
    write_end: int
    child_value: int
    inheritable: bool


def open_event_pipe() -> EventPipe:
    if os.name != "nt":
        read_end, write_end = os.pipe()
        return EventPipe(read_end=read_end, write_end=write_end, child_value=write_end, inheritable=False)
    import msvcrt

    # Windows pipes are non-inheritable by default and pass_fds is unavailable; the child gets
    # the write handle itself, so only that handle may leak into it (close_fds=False).
    read_end, write_end = os.pipe()
    write_handle = msvcrt.get_osfhandle(write_end)
    os.set_handle_inheritable(write_handle, True)
    return EventPipe(read_end=read_end, write_end=write_end, child_value=write_handle, inheritable=True)


__all__ = ["EVENTS_ENV", "HANDLE_ENV", "EventPipe", "open_event_pipe"]
