"""Qwen-compatible audio API calls and private S3 staging."""

from __future__ import annotations

import tempfile
import uuid
from functools import partial
from pathlib import Path
from typing import Any

from segment.music_agent.json_response import json_response
from segment.music_agent.json_response import parse_json as parse_json
from segment.music_agent.media import extract_wav
from segment.music_agent.storage import AudioStorage


def audio_model_call(client: Any, model: str, prompt: str, audio_url: str) -> dict[str, Any]:
    request = partial(
        client.chat.completions.create,
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
    return json_response(request, model)


def text_model_call(client: Any, model: str, prompt: str) -> dict[str, Any]:
    request = partial(
        client.chat.completions.create,
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return json_response(request, model)


def call_with_storage(
    media: Path,
    start: float,
    end: float,
    client: Any,
    storage: AudioStorage,
    *,
    model: str,
    prompt: str,
    s3_prefix: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="music-agent-") as directory:
        wav = Path(directory) / "input.wav"
        extract_wav(media, start, end, wav)
        key = "/".join(filter(None, (s3_prefix, uuid.uuid4().hex, "input.wav")))
        storage.upload(key, wav)
        try:
            url = storage.signed_url(key)
            return audio_model_call(client, model, prompt, url)
        finally:
            storage.delete(key)
