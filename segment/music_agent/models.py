"""Qwen-compatible audio API calls and private OSS staging."""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from segment.music_agent.media import extract_wav


def parse_json(content: str) -> dict[str, Any]:
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("模型响应 JSON 顶层必须是对象")
    return value


def audio_model_call(client: Any, model: str, prompt: str, audio_url: str) -> dict[str, Any]:
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "input_audio", "input_audio": {"data": audio_url, "format": "wav"}},
                ],
            }
        ],
    )
    return {
        "data": parse_json(response.choices[0].message.content or ""),
        "usage": response.usage.model_dump() if response.usage else None,
    }


def text_model_call(client: Any, model: str, prompt: str) -> dict[str, Any]:
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return {
        "data": parse_json(response.choices[0].message.content or ""),
        "usage": response.usage.model_dump() if response.usage else None,
    }


def call_with_oss(
    media: Path,
    start: float,
    end: float,
    client: Any,
    bucket: Any,
    *,
    model: str,
    prompt: str,
    oss_prefix: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="music-agent-") as directory:
        wav = Path(directory) / "input.wav"
        extract_wav(media, start, end, wav)
        key = f"{oss_prefix}/{uuid.uuid4().hex}/input.wav"
        try:
            bucket.put_object_from_file(key, str(wav))
            url = bucket.sign_url("GET", key, 3600, slash_safe=True)
            return audio_model_call(client, model, prompt, url)
        finally:
            bucket.delete_object(key)
