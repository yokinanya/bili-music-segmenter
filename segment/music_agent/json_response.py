"""Strict JSON parsing for model responses; no fabricated results on malformed output."""

from __future__ import annotations

import json
from typing import Any


def parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) < 3 or lines[-1].strip() != "```":
            raise ValueError("模型响应 JSON 代码块不完整")
        text = "\n".join(lines[1:-1]).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("模型响应 JSON 顶层必须是对象")
    return value
