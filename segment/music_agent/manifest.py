"""Incremental run manifest persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def write_manifest(
    path: Path,
    *,
    media: Path,
    duration: float,
    models: dict[str, str | None],
    policy: dict[str, Any],
    chunks: list[dict[str, Any]],
    candidate_count: int,
    candidates: list[dict[str, Any]],
    exported_count: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "media": str(media),
        "duration_seconds": duration,
        "models": models,
        "policy": policy,
        "chunks": chunks,
        "candidate_count": candidate_count,
        "candidates_completed": len(candidates),
        "exported_count": exported_count,
        "candidates": candidates,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
