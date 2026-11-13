"""Dependency adapters composed once by the CLI entry point."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class PipelineServices:
    calls: dict[str, Callable]
    recognizer_budget: asyncio.Semaphore

    async def recognize(self, audio, context):
        return await self.calls["recognize"](
            audio,
            netease_cookie=context.options["netease_cookie"],
            timeout=context.options["recognizer_timeout"],
            use_shazam=context.options["use_shazam"],
            use_netease=context.options["use_netease"],
            budget=self.recognizer_budget,
        )

    def choose_title(self, recognition):
        return self.calls["choose_title"](recognition)

    def extract_reference(self, *args):
        return self.calls["extract_reference"](*args)
