"""Explicit retries for malformed model JSON, without fabricated results."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from typing import Any

from segment.usage import report_usage

LOGGER = logging.getLogger(__name__)
DEFAULT_JSON_RETRIES = 3


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


def json_response(request: Callable[[], Any], model: str) -> dict[str, Any]:
    retries = int(os.getenv("MUSIC_AGENT_JSON_RETRIES", str(DEFAULT_JSON_RETRIES)))
    if retries < 0:
        raise ValueError("MUSIC_AGENT_JSON_RETRIES 不能为负")
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        response = request()
        usage = response.usage.model_dump() if response.usage else None
        report_usage(model, usage)
        choice = response.choices[0]
        content = choice.message.content or ""
        try:
            data = parse_json(content)
        except ValueError as exc:
            LOGGER.warning(
                "Invalid model JSON: model=%s attempt=%d/%d finish_reason=%s error=%s response=%r",
                model,
                attempt,
                attempts,
                getattr(choice, "finish_reason", None),
                exc,
                content,
            )
            if attempt == attempts:
                raise ValueError(f"模型 {model} 连续 {attempts} 次返回无效 JSON；原始响应见日志") from exc
            continue
        return {"data": data, "usage": usage}
    raise AssertionError("JSON 调用未执行")
