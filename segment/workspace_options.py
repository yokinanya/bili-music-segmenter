"""One typed set of task defaults and validation for CLI and browser requests."""

from __future__ import annotations

import math
import os
from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class RunOptions:
    candidate_concurrency: int = 3
    model_concurrency: int = 3
    recognizer_concurrency: int = 3
    media_concurrency: int = min(2, os.cpu_count() or 1)
    chunk_seconds: int = 600
    chunk_context_seconds: int = 30
    minimum_candidate_seconds: float = 30
    minimum_singing_seconds: float = 30
    minimum_confidence: float = 0.85
    use_shazam: bool = True
    use_netease: bool = True
    recognizer_timeout: int = 60


ENV_NAMES = {
    "chunk_context_seconds": "CHUNK_CONTEXT",
    "use_shazam": "SKIP_SHAZAM",
    "use_netease": "SKIP_NETEASE",
}
NONNEGATIVE = {"chunk_context_seconds"}
BOOLEAN_FIELDS = {"use_shazam", "use_netease"}
FLOAT_FIELDS = {"minimum_candidate_seconds", "minimum_singing_seconds", "minimum_confidence"}
RETIRED_OPTIONS = frozenset(
    {"scan_concurrency", "upload_concurrency", "use_title_model", "boundary_context_seconds"}
)


def default_options() -> dict:
    values = asdict(RunOptions())
    for name, current in values.items():
        raw = os.getenv("MUSIC_AGENT_" + ENV_NAMES.get(name, name.upper()))
        if raw is None:
            continue
        if name in BOOLEAN_FIELDS:
            if raw.lower() not in {"true", "false"}:
                raise ValueError(f"{name} 必须是 true 或 false")
            values[name] = raw.lower() == "false"
        else:
            values[name] = type(current)(raw)
    return validate_options(values)


def validate_options(values: dict, defaults: dict | None = None) -> dict:
    if not isinstance(values, dict):
        raise ValueError("options 必须是对象")
    names = {field.name for field in fields(RunOptions)}
    if values.keys() - names:
        raise ValueError("包含未知任务参数")
    merged = {**(defaults if defaults is not None else asdict(RunOptions())), **values}
    for name, value in merged.items():
        _validate_value(name, value)
    return merged


def _validate_value(name: str, value: object) -> None:
    if name in BOOLEAN_FIELDS:
        if type(value) is not bool:
            raise ValueError(f"{name} 必须是布尔值")
        return
    expected = (int, float) if name in FLOAT_FIELDS else (int,)
    if type(value) not in expected or not math.isfinite(value):
        raise ValueError(f"{name} 必须是有限数值")
    if name in NONNEGATIVE:
        if value < 0:
            raise ValueError(f"{name} 不能为负")
        return
    if value <= 0 or (name == "minimum_confidence" and value > 1):
        raise ValueError(f"{name} 超出有效范围")
