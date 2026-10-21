"""In-memory token accounting using the official price screenshots dated 2026-10-20."""

from __future__ import annotations

from decimal import Decimal
from threading import Lock

from segment.events import emit_event

EVENT_PREFIX = "__MUSIC_AGENT_USAGE__"
MILLION = Decimal(1_000_000)
PRICES = {
    "qwen3.8-flash": (Decimal("0.8"), Decimal("0.1"), Decimal("2.7")),
    "qwen3.8-omni-flash": (Decimal("0.8"), Decimal("0.1"), Decimal("2.7")),
}


def report_usage(model: str, usage: dict | None) -> None:
    emit_event(EVENT_PREFIX, {"model": model, "usage": usage})


def _tokens(usage: dict) -> tuple[int, int, int]:
    prompt = usage["prompt_tokens"]
    completion = usage["completion_tokens"]
    details = usage.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens", 0)
    if any(type(value) is not int or value < 0 for value in (prompt, completion, cached)) or cached > prompt:
        raise ValueError("模型 usage token 数值无效")
    return prompt, completion, cached


class UsageTotals:
    def __init__(self) -> None:
        self._lock = Lock()
        self._events: list[dict] = []

    def add(self, event: dict) -> None:
        # Validate inside the lock so a failing event never interleaves with a concurrent snapshot.
        with self._lock:
            usage = event["usage"]
            if usage is not None:
                _tokens(usage)
            self._events.append(event)

    def snapshot(self) -> dict:
        with self._lock:
            events = tuple(self._events)
        models: dict[str, dict] = {}
        for event in events:
            model = event["model"]
            row = models.setdefault(
                model,
                {
                    "model": model,
                    "calls": 0,
                    "missing_usage": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cached_tokens": 0,
                    "estimated_cny": 0.0,
                },
            )
            _accumulate(row, event["usage"])
        rows = list(models.values())
        complete = all(not row["missing_usage"] and row["estimated_cny"] is not None for row in rows)
        return {
            "models": rows,
            "calls": len(events),
            "input_tokens": sum(row["input_tokens"] for row in rows),
            "output_tokens": sum(row["output_tokens"] for row in rows),
            "cached_tokens": sum(row["cached_tokens"] for row in rows),
            "estimated_cny": sum(row["estimated_cny"] or 0 for row in rows),
            "complete": complete,
        }


def _accumulate(row: dict, usage: dict | None) -> None:
    row["calls"] += 1
    if usage is None:
        row["missing_usage"] += 1
        return
    prompt, completion, cached = _tokens(usage)
    row["input_tokens"] += prompt
    row["output_tokens"] += completion
    row["cached_tokens"] += cached
    price = PRICES.get(row["model"])
    if price is None:
        row["estimated_cny"] = None
        return
    input_price, cached_price, output_price = price
    cost = ((prompt - cached) * input_price + cached * cached_price + completion * output_price) / MILLION
    row["estimated_cny"] += float(cost)
