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
    s3_access_key: str
    s3_access_secret: str
    s3_endpoint: str
    s3_bucket: str
    s3_prefix: str
    s3_region: str
    s3_addressing_style: str = "path"
    s3_user_agent: str | None = None


def load_config() -> ApiConfig:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    names = (
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_BASE_URL",
        "S3_ACCESS_KEY_ID",
        "S3_ACCESS_KEY_SECRET",
        "S3_ENDPOINT",
        "S3_BUCKET",
        "S3_REGION",
    )
    values = {name: os.getenv(name, "").strip() for name in names}
    missing = [name for name in names if not values[name]]
    if missing:
        raise ValueError(f"请在 .env 配置必填项：{', '.join(missing)}")
    base_url = values["DASHSCOPE_BASE_URL"]
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("DASHSCOPE_BASE_URL 必须是与 API key 对应的 HTTPS 接入地址")
    endpoint = _s3_endpoint(values["S3_ENDPOINT"])
    addressing_style = os.getenv("S3_ADDRESSING_STYLE", "path").strip()
    if addressing_style not in {"path", "virtual", "auto"}:
        raise ValueError("S3_ADDRESSING_STYLE 必须是 path、virtual 或 auto")
    return ApiConfig(
        api_key=values["DASHSCOPE_API_KEY"],
        base_url=base_url.rstrip("/"),
        s3_access_key=values["S3_ACCESS_KEY_ID"],
        s3_access_secret=values["S3_ACCESS_KEY_SECRET"],
        s3_endpoint=endpoint.rstrip("/"),
        s3_bucket=values["S3_BUCKET"],
        s3_prefix=os.getenv("S3_PREFIX", "music-agent").strip("/"),
        s3_region=values["S3_REGION"],
        s3_addressing_style=addressing_style,
        s3_user_agent=os.getenv("S3_USER_AGENT", "").strip() or None,
    )


def _s3_endpoint(endpoint: str) -> str:
    if "://" not in endpoint:
        endpoint = f"https://{endpoint}"
    parsed = urlsplit(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("S3_ENDPOINT 必须是无凭据、查询参数和片段的 HTTP(S) 地址")
    return endpoint.rstrip("/")
