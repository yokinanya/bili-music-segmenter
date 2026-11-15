"""In-memory token accounting using the official Gemini API prices dated 2026-11-13 (USD per 1M tokens)."""

from __future__ import annotations

import logging
from decimal import Decimal
from threading import Lock

from segment.events import emit_event

EVENT_PREFIX = "__MUSIC_AGENT_USAGE__"
LOGGER = logging.getLogger(__name__)
MILLION = Decimal(1_000_000)
# (输入, 缓存输入, 输出)，单位美元/百万 token；缓存价为官方隐式缓存价。
PRICES = {
    "gemini-4-hydrogen": (Decimal("1.50"), Decimal("0.075"), Decimal("7.50")),
    "gemini-4-argon": (Decimal("2.00"), Decimal("0.10"), Decimal("10.00")),
    "gemini-4-carbon": (Decimal("2.00"), Decimal("0.10"), Decimal("10.00")),
    "gemini-3.8-flash": (Decimal("0.75"), Decimal("0.075"), Decimal("3.75")),
    "gemini-3.6-flash": (Decimal("0.75"), Decimal("0.075"), Decimal("3.75")),
    "gemini-3.5-flash-lite": (Decimal("0.75"), Decimal("0.075"), Decimal("3.75")),
}


def report_usage(model: str, usage: dict | None) -> None:
    emit_event(EVENT_PREFIX, {"model": model, "usage": usage})


def _tokens(usage: dict) -> tuple[int, int, int]:
    if "total_input_tokens" in usage:
        prompt = usage["total_input_tokens"]
        completion = usage["total_output_tokens"]
        cached = usage.get("total_cached_tokens", 0)
    else:
        prompt = usage["prompt_tokens"]
        completion = usage["completion_tokens"]
        details = usage.get("prompt_tokens_details") or {}
        cached = details.get("cached_tokens", 0)
    if any(type(value) is not int or value < 0 for value in (prompt, completion, cached)) or cached > prompt:
        raise ValueError("模型 usage token 数值无效")
    return prompt, completion, cached


def _validated_event(event: dict) -> dict:
    try:
        if event["usage"] is not None:
            _tokens(event["usage"])
    except ValueError:
        LOGGER.warning("已忽略模型 %s 的无效 usage token 统计", event["model"])
        return {**event, "usage": None}
    return event


class UsageTotals:
    def __init__(self, store=None) -> None:
        self._lock = Lock()
        self._store = store
        self._events: list[dict] = self._load()

    def _load(self) -> list[dict]:
        """Previous runs survive a restart because the events live in SQLite."""
        if self._store is None:
            return []
        return [event for record in self._store.list("usage") for event in record["events"]]

    def add(self, event: dict) -> dict:
        validated = _validated_event(event)
        with self._lock:
            self._events.append(validated)
            if self._store is not None:
                self._store.put("usage", {"id": "totals", "events": list(self._events)})
        return validated

    def replace(self, events: list[dict]) -> None:
        with self._lock:
            self._events = list(events)
            if self._store is not None:
                self._store.put("usage", {"id": "totals", "events": self._events})

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
                    "estimated_usd": 0.0,
                },
            )
            _accumulate(row, event["usage"])
        rows = list(models.values())
        complete = all(not row["missing_usage"] and row["estimated_usd"] is not None for row in rows)
        return {
            "models": rows,
            "calls": len(events),
            "input_tokens": sum(row["input_tokens"] for row in rows),
            "output_tokens": sum(row["output_tokens"] for row in rows),
            "cached_tokens": sum(row["cached_tokens"] for row in rows),
            "estimated_usd": sum(row["estimated_usd"] or 0 for row in rows),
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
        row["estimated_usd"] = None
        return
    input_price, cached_price, output_price = price
    cost = ((prompt - cached) * input_price + cached * cached_price + completion * output_price) / MILLION
    row["estimated_usd"] += float(cost)
