"""Non-destructive, revisioned song-cut projects independent of exports."""

from __future__ import annotations

import math
import re
from uuid import uuid4

from segment.workspace_uploads import now

INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_FILENAME = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.I)
CLIP_FIELDS = frozenset(
    {"id", "start_seconds", "end_seconds", "title", "artist", "name", "recognition", "title_resolution"}
)


def validate_clips(clips: object, duration: float) -> list[dict]:
    if not isinstance(clips, list):
        raise ValueError("clips must be a list")
    identities = set()
    for clip in clips:
        if not isinstance(clip, dict) or clip.keys() - CLIP_FIELDS:
            raise ValueError("Invalid clip fields")
        identity = clip.get("id")
        if not isinstance(identity, str) or not identity or identity in identities:
            raise ValueError("Clip IDs must be unique nonempty strings")
        identities.add(identity)
        start, end = clip.get("start_seconds"), clip.get("end_seconds")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (start, end)):
            raise ValueError("Clip bounds must be finite numbers")
        if not 0 <= start < end <= duration:
            raise ValueError("Clip bounds must satisfy 0 <= start < end <= source duration")
        for field in ("title", "artist", "name"):
            if not isinstance(clip.get(field), str) or "\x00" in clip[field]:
                raise ValueError(f"Invalid {field}")
        name = clip["name"]
        if (
            not name.lower().endswith(".mp4")
            or INVALID_FILENAME.search(name)
            or RESERVED_FILENAME.match(name)
            or name.endswith((".", " "))
        ):
            raise ValueError("Filename must be a valid .mp4 basename")
    return clips


class Projects:
    def __init__(self, store):
        self.store = store

    def create(self, source: dict) -> dict:
        duration = source["duration"]
        if type(duration) not in (int, float) or not math.isfinite(duration) or duration <= 0:
            raise ValueError("Source duration must be finite and positive")
        project = {
            "id": uuid4().hex,
            "version": 1,
            "revision": 0,
            "clips": [],
            "upload_id": source["upload_id"],
            "name": source["name"],
            "duration": duration,
            "updated_at": now(),
        }
        self.store.put("projects", project)
        return project

    def get(self, identity: str) -> dict:
        return self.store.get("projects", identity)

    def save(self, identity: str, payload: dict) -> dict:
        if payload.keys() != {"revision", "clips"} or type(payload["revision"]) is not int:
            raise ValueError("Expected revision and clips")

        def change(project):
            if payload["revision"] != project["revision"]:
                raise ValueError("Project revision conflict: reload before saving")
            clips = validate_clips(payload["clips"], project["duration"])
            return {**project, "clips": clips, "revision": project["revision"] + 1, "updated_at": now()}

        return self.store.update("projects", identity, change)
