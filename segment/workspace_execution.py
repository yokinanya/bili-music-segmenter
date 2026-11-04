"""Sequential durable jobs; each child owns its internal parallel pipeline."""

from __future__ import annotations

from queue import Queue
from threading import Event, Lock, Thread

from segment.workspace_process import stop_process
from segment.workspace_records import attempt_record, end_steps, reduce_event, replace_item
from segment.workspace_results import read_clips
from segment.workspace_uploads import now


class Execution:
    def __init__(self, store, runner, root, *, usage):
        self.store, self.runner, self.root = store, runner, root
        self.usage = usage
        self._lock = Lock()
        self._processes = {}
        self._queue = Queue()
        self._closing = Event()
        self._worker = Thread(target=self._work, daemon=True)
        self._worker.start()

    def schedule(self, identity: str) -> None:
        self._queue.put(identity)

    def _work(self) -> None:
        while (identity := self._queue.get()) is not None:
            try:
                self._run(identity)
            except Exception as error:
                message = str(error)
                self.store.update(
                    "jobs",
                    identity,
                    lambda job: {
                        **job,
                        "state": "failed",
                        "error": message,
                        "finished_at": now(),
                    },
                )

    def stop(self, identity: str) -> None:
        self.store.update("jobs", identity, lambda job: {**job, "stop_requested": True})
        with self._lock:
            process = self._processes.get(identity)
            if process:
                stop_process(process)

    def close(self) -> None:
        self._closing.set()
        with self._lock:
            for process in self._processes.values():
                stop_process(process)
        self._queue.put(None)
        self._worker.join()

    def _started(self, identity: str, process) -> None:
        with self._lock:
            self._processes[identity] = process
            if self._closing.is_set() or self.store.get("jobs", identity)["stop_requested"]:
                stop_process(process)

    def _run(self, identity: str) -> None:
        if self._closing.is_set():
            return
        self.store.update("jobs", identity, lambda job: {**job, "state": "running", "attempt_started_at": now()})
        self._run_items(identity)
        self.store.update("jobs", identity, self._finish)

    def _run_items(self, identity: str) -> None:
        initial = self.store.get("jobs", identity)
        for index, item in enumerate(initial["batch"]):
            if item["state"] == "succeeded":
                continue
            job = self.store.get("jobs", identity)
            if self._closing.is_set() or job["stop_requested"]:
                self._update_item(
                    identity, index, state="interrupted" if self._closing.is_set() else "cancelled", finished_at=now()
                )
                continue
            self._execute(identity, index)

    def _execute(self, identity: str, index: int) -> None:
        self._update_item(identity, index, state="running", started_at=now(), error=None)
        job = self.store.get("jobs", identity)
        self.store.update("jobs", identity, lambda value: {**value, "current_index": index})
        attempt = job["attempt"]

        def report(kind, event):
            if kind == "usage":
                self.usage.add(event)
            self.store.update(
                "jobs",
                identity,
                lambda value: reduce_event(
                    value,
                    index,
                    kind=kind,
                    event=event,
                    attempt=attempt,
                ),
            )

        try:
            code = self.runner.run(
                job,
                job["batch"][index],
                state_dir=self.root,
                report=report,
                started=lambda process: self._started(identity, process),
            )
            state = "succeeded" if code == 0 else "failed"
            if self._closing.is_set():
                state = "interrupted"
            if self.store.get("jobs", identity)["stop_requested"]:
                state = "cancelled"
            self._update_item(
                identity,
                index,
                state=state,
                returncode=code,
                finished_at=now(),
                error=None if state == "succeeded" else f"执行进程退出：{code}",
            )
        except Exception as error:
            self._update_item(identity, index, state="failed", error=str(error), finished_at=now())
        finally:
            with self._lock:
                self._processes.pop(identity, None)

    def _update_item(self, identity: str, index: int, **changes) -> None:
        def update(job):
            item = {**job["batch"][index], **changes}
            if changes.get("state") in {"failed", "cancelled", "interrupted"}:
                item = end_steps(item, changes["state"])
            return replace_item(job, index, item)

        self.store.update("jobs", identity, update)

    @staticmethod
    def _finish(job: dict) -> dict:
        states = {item["state"] for item in job["batch"]}
        state = "succeeded" if states == {"succeeded"} else "failed"
        if "interrupted" in states:
            state = "interrupted"
        if job["stop_requested"] or "cancelled" in states:
            state = "cancelled"
        result = {**job, "state": state, "finished_at": now(), "current_index": None}
        result["clips"] = [clip for item in job["batch"] for clip in read_clips(item)]
        return {**result, "attempts": [*job["attempts"], attempt_record(result)]}
