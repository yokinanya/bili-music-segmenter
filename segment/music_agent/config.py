"""Environment configuration for model calls."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from segment.music_agent.gemini import DEFAULT_MODEL, GeminiConfig


@dataclass(frozen=True)
class ApiConfig:
    gemini: GeminiConfig


def load_config() -> ApiConfig:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("请在 .env 配置必填项：GEMINI_API_KEY")
    return ApiConfig(
        gemini=GeminiConfig(
            api_key=api_key,
            proxy=os.getenv("GEMINI_PROXY", "").strip() or None,
            base_url=os.getenv("GEMINI_BASE_URL", "").strip() or None,
            model=os.getenv("GEMINI_AUDIO_MODEL", "").strip() or DEFAULT_MODEL,
        )
    )
