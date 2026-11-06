"""Track new-flow exports without deleting legacy batch files."""

from __future__ import annotations

import json
from pathlib import Path

from segment.music_agent.manifest import atomic_write_json

INVENTORY_NAME = ".export-inventory.json"


def initialize_inventory(output: Path) -> None:
    path = output / INVENTORY_NAME
    if path.exists():
        return
    legacy = [str(item.resolve()) for item in (output / "clips").rglob("*.mp4")]
    atomic_write_json(path, {"legacy_files": legacy})


def remove_superseded_exports(output: Path, records: list[dict]) -> None:
    inventory = json.loads((output / INVENTORY_NAME).read_text(encoding="utf-8"))
    retained = set(inventory["legacy_files"])
    retained.update(
        str(Path(interval["file"]).resolve())
        for record in records
        for interval in record.get("singing_intervals", [])
        if "file" in interval
    )
    for path in (output / "clips").rglob("*.mp4"):
        if str(path.resolve()) not in retained:
            path.unlink()
