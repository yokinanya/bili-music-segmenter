"""Environment configuration shared by audio and text model calls."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


@dataclass(frozen=True)
class ApiConfig:
    api_key: str
    base_url: str
    oss_access_key: str
    oss_access_secret: str
    oss_endpoint: str
    oss_bucket: str
    oss_prefix: str


def load_config() -> ApiConfig:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    names = (
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_BASE_URL",
        "OSS_ACCESS_KEY_ID",
        "OSS_ACCESS_KEY_SECRET",
        "OSS_ENDPOINT",
        "OSS_BUCKET",
    )
    values = {name: os.getenv(name, "").strip() for name in names}
    missing = [name for name in names if not values[name]]
    if missing:
        raise ValueError(f"请在 .env 配置必填项：{', '.join(missing)}")
    base_url = values["DASHSCOPE_BASE_URL"]
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("DASHSCOPE_BASE_URL 必须是与 API key 对应的 HTTPS 接入地址")
    return ApiConfig(
        api_key=values["DASHSCOPE_API_KEY"],
        base_url=base_url.rstrip("/"),
        oss_access_key=values["OSS_ACCESS_KEY_ID"],
        oss_access_secret=values["OSS_ACCESS_KEY_SECRET"],
        oss_endpoint=values["OSS_ENDPOINT"],
        oss_bucket=values["OSS_BUCKET"],
        oss_prefix=os.getenv("OSS_PREFIX", "music-agent").strip("/") or "music-agent",
    )
