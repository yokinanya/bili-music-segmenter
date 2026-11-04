"""Injected progress, checkpoints and shared resource budgets for one video."""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from threading import BoundedSemaphore, RLock
from typing import Any

from segment.events import emit_event
from segment.music_agent.manifest import atomic_write_json
from segment.workspace_options import default_options
from segment.workspace_uploads import now

PROGRESS_PREFIX = "__MUSIC_AGENT_PROGRESS__"
PIPELINE_VERSION = "workspace-1"
PROGRESS_INTERVAL_SECONDS = 0.25
HASH_BYTES = 1024 * 1024


@dataclass(frozen=True)
class Scope:
    runtime: Runtime
    step_id: str


CURRENT: ContextVar[Scope | None] = ContextVar("pipeline_scope", default=None)


def fingerprint(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return hashlib.sha256(serialized.encode()).hexdigest()


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(HASH_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


class Runtime:
    def __init__(self, config: dict, report: Callable = emit_event):
        self.config = config
        self.report = report
        self.root = Path(config["checkpoint_dir"])
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._sequence = 0
        self._steps: dict[str, dict] = {}
        self._stamps: dict[str, str] = {}
        self._budgets = {
            name: BoundedSemaphore(config["options"][name + "_concurrency"])
            for name in ("model", "recognizer", "upload", "media")
        }

    def advance(self, identity: str, label: str, total: int) -> None:
        with self._lock:
            count = self._steps.get(identity, {}).get("completed", 0) + 1
            self.event(
                identity,
                label,
                completed=count,
                total=total,
                unit="项",
                state="succeeded" if count == total else "running",
            )

    def event(self, identity: str, label: str, **changes) -> None:
        with self._lock:
            self._sequence += 1
            scope = CURRENT.get()
            parent = scope.step_id if scope and scope.step_id != identity else None
            previous = self._steps.get(identity, {})
            step = {
                "id": identity,
                "label": label,
                "parent_id": parent,
                "state": "running",
                "completed": 0,
                "total": None,
                "unit": None,
                "attempt": self.config["attempt"],
                "started_at": now(),
                "finished_at": None,
                "error": None,
                **previous,
                **changes,
                "sequence": self._sequence,
            }
            self._steps[identity] = step
            self.report(PROGRESS_PREFIX, step)

    @contextmanager
    def activate(self, identity: str = ""):
        token = CURRENT.set(Scope(self, identity))
        try:
            yield
        finally:
            CURRENT.reset(token)

    @contextmanager
    def resource(self, name: str):
        scope = CURRENT.get()
        identity = scope.step_id if scope else name
        label = self._steps.get(identity, {}).get("label", name)
        self.event(identity, label, state="waiting")
        started = time.monotonic()
        with self._budgets[name]:
            waited = time.monotonic() - started
            self.event(identity, label, state="running", waiting_seconds=waited)
            yield

    def run(self, spec: dict, work: Callable[[], Any]) -> Any:
        identity, label = spec["id"], spec["label"]
        stamp = fingerprint([PIPELINE_VERSION, self.config["source_digest"], spec.get("input")])
        self._stamps[identity] = stamp
        path = self.root / f"{fingerprint(identity)}.json"
        cached = self._cached(path, stamp, spec) if spec.get("cache", True) else None
        if cached is not None:
            self.event(
                identity,
                label,
                state="reused",
                completed=spec.get("total", 1),
                total=spec.get("total", 1),
                finished_at=now(),
            )
            return cached["value"]
        self.event(identity, label)
        started = time.monotonic()
        try:
            with self.activate(identity):
                value = work()
            if spec.get("cache", True):
                atomic_write_json(path, {"stamp": stamp, "value": value})
        except Exception as error:
            self.event(identity, label, state="failed", error=str(error), finished_at=now())
            raise
        self.event(
            identity,
            label,
            state="succeeded",
            completed=spec.get("total", 1),
            total=spec.get("total", 1),
            finished_at=now(),
            elapsed_seconds=time.monotonic() - started,
        )
        return value

    async def async_run(self, spec: dict, work: Callable) -> Any:
        identity, label = spec["id"], spec["label"]
        stamp = fingerprint([PIPELINE_VERSION, self.config["source_digest"], spec.get("input")])
        self._stamps[identity] = stamp
        path = self.root / f"{fingerprint(identity)}.json"
        cached = self._cached(path, stamp, spec)
        if cached is not None:
            self.event(identity, label, state="reused", completed=1, total=1, finished_at=now())
            return cached["value"]
        self.event(identity, label)
        started = time.monotonic()
        try:
            with self.activate(identity):
                value = await work()
            atomic_write_json(path, {"stamp": stamp, "value": value})
        except Exception as error:
            self.event(identity, label, state="failed", error=str(error), finished_at=now())
            raise
        self.event(
            identity,
            label,
            state="succeeded",
            completed=spec.get("total", 1),
            total=spec.get("total", 1),
            elapsed_seconds=time.monotonic() - started,
            finished_at=now(),
        )
        return value

    @staticmethod
    def _cached(path: Path, stamp: str, spec: dict) -> dict | None:
        if not path.exists():
            return None
        cached = json.loads(path.read_text())
        if cached["stamp"] != stamp:
            return None
        validate = spec.get("validate")
        if validate and not validate(cached["value"]):
            return None
        return cached


def create_runtime(media: Path, output: Path, options: dict) -> Runtime:
    return Runtime(
        {
            "options": {**default_options(), **options},
            "checkpoint_dir": str(output / ".checkpoints"),
            "source_digest": os.getenv("MUSIC_AGENT_SOURCE_DIGEST") or file_digest(media),
            "attempt": int(os.getenv("MUSIC_AGENT_ATTEMPT", "1")),
            "owner": os.getenv("MUSIC_AGENT_JOB_ID", str(output.resolve())),
            "state_dir": os.getenv("MUSIC_AGENT_STATE_DIR", str(output / ".runtime")),
        }
    )


def checkpoint(kind: str, payload: dict, work: Callable) -> Any:
    scope = CURRENT.get()
    if scope is None:
        return work()
    payload = {**payload, "dependency": scope.runtime._stamps.get(scope.step_id)}
    identity = f"{kind}/{fingerprint(payload)}"
    return scope.runtime.run({"id": identity, "label": kind, "input": payload}, work)
