"""Serialize structured child-process events across worker threads."""

import json
import os
from threading import Lock

_EVENT_LOCK = Lock()


def emit_event(prefix: str, event: dict) -> None:
    if os.getenv("MUSIC_AGENT_USAGE_EVENTS") != "1":
        return
    line = prefix + json.dumps(event)
    with _EVENT_LOCK:
        print(line, flush=True)
