"""Persistent task documents and structured event reduction."""

from __future__ import annotations

from uuid import uuid4

from segment.usage import UsageTotals
from segment.workspace_uploads import now

ACTIVE_STATES = frozenset({"queued", "running"})
UNFINISHED_STEPS = frozenset({"running", "waiting", "retrying"})


def usage_snapshot(events: list[dict]) -> dict:
    totals = UsageTotals()
    for event in events:
        totals.add(event)
    return totals.snapshot()


def new_job(uploads: list[dict], options: dict, request_id: str, root) -> dict:
    identity = uuid4().hex
    items = [new_item(upload, root / "jobs" / identity) for upload in uploads]
    return {
        "id": identity,
        "request_id": request_id,
        "upload_ids": [value["id"] for value in uploads],
        "options": options,
        "state": "queued",
        "started_at": now(),
        "finished_at": None,
        "attempt": 1,
        "attempts": [],
        "batch": items,
        "current_index": None,
        "clips": [],
        "usage_events": [],
        "usage": usage_snapshot([]),
        "error": None,
        "stop_requested": False,
        "cleanup_error": None,
        "legacy": False,
    }


def new_item(upload: dict, root) -> dict:
    identity = uuid4().hex
    folder = root / identity
    folder.mkdir(parents=True)
    return {
        "id": identity,
        "upload_id": upload["id"],
        "media": upload["name"],
        "sha256": upload["sha256"],
        "source_path": upload["source_path"],
        "outdir": str(folder),
        "log_path": str(folder / "execution.log"),
        "state": "queued",
        "steps": [],
        "last_sequence": 0,
        "returncode": None,
        "error": None,
        "started_at": None,
        "finished_at": None,
        **({"download_config": upload["download_config"]} if upload.get("download_config") else {}),
    }


def reduce_event(job: dict, index: int, *, kind: str, event: dict, attempt: int) -> dict:
    if job["attempt"] != attempt:
        return job
    if kind == "usage":
        events = [
            *job["usage_events"],
            {**event, "attempt": attempt, "media_id": job["batch"][index]["id"], "at": now()},
        ]
        return {**job, "usage_events": events, "usage": usage_snapshot(events)}
    item = job["batch"][index]
    if kind == "download":
        from segment.workspace_downloads import update_download

        return update_download(job, index, event)
    if kind == "upload":
        uploads = {value["key"]: value for value in item.get("upload", {}).get("uploads", [])}
        uploads[event["key"]] = event
        return replace_item(job, index, {**item, "upload": {"uploads": list(uploads.values())}})
    if event["attempt"] != attempt or event["sequence"] <= item["last_sequence"]:
        return job
    steps = {step["id"]: step for step in item["steps"]}
    steps[event["id"]] = event
    return replace_item(job, index, {**item, "steps": list(steps.values()), "last_sequence": event["sequence"]})


def replace_item(job: dict, index: int, item: dict) -> dict:
    return {**job, "batch": [item if position == index else value for position, value in enumerate(job["batch"])]}


def end_steps(item: dict, state: str) -> dict:
    steps = [
        {**step, "state": state, "finished_at": now()} if step["state"] in UNFINISHED_STEPS else step
        for step in item["steps"]
    ]
    return {**item, "steps": steps}


def attempt_record(job: dict) -> dict:
    return {
        "number": job["attempt"],
        "state": job["state"],
        "finished_at": job["finished_at"],
        "started_at": job["attempt_started_at"],
        "usage": usage_snapshot([event for event in job["usage_events"] if event["attempt"] == job["attempt"]]),
    }
