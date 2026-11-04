"""Immutable dependencies and task settings shared by concurrent pipeline work."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PipelineContext:
    media: Path
    output: Path
    options: dict
    services: Any
    runtime: Any
    client: Any
    storage: Any
    prefix: str

    def spec(self, identity: str, label: str, payload: Any) -> dict:
        return {"id": identity, "label": label, "input": [self.options, payload]}
