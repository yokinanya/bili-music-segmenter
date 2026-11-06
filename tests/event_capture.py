"""Test helpers for the child-process event pipe."""

import json
import os

from segment.events import EVENTS_ENV, emit_event


class EventCapture:
    def __init__(self, path):
        self.path = path

    def lines(self, capsys=None):
        if self.path.exists():
            return self.path.read_text(encoding="utf-8").splitlines()
        return []

    def stdout(self, capsys):
        return capsys.readouterr().out


def capture_events(monkeypatch, tmp_path) -> EventCapture:
    """Point emit_event at a file descriptor so tests never depend on stdout capture."""
    path = tmp_path / "events.log"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    monkeypatch.setenv(EVENTS_ENV, str(fd))
    return EventCapture(path)


def send_raw(line: str) -> None:
    """Write one already-serialized event line through the production writer."""
    emit_event("", json.loads(line))


def child_sends(line: str) -> str:
    """Child program that sends one raw event line; requires PYTHONPATH to include tests/."""
    return f"from event_capture import send_raw; send_raw({line!r})"
