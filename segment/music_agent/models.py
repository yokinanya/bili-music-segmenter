"""Qwen-compatible audio API calls and private S3 staging."""

from __future__ import annotations

from contextlib import nullcontext
from functools import partial
from pathlib import Path
from typing import Any

from segment.music_agent.json_response import json_response
from segment.music_agent.json_response import parse_json as parse_json
from segment.music_agent.runtime import CURRENT, fingerprint
from segment.music_agent.staged_audio import with_audio
from segment.music_agent.storage import AudioStorage


def audio_model_call(client: Any, model: str, prompt: str, audio_url: str) -> dict[str, Any]:
    def request():
        url = audio_url() if callable(audio_url) else audio_url
        return client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "input_audio", "input_audio": {"data": url, "format": "wav"}},
                    ],
                }
            ],
        )

    return _request(request, model)


def text_model_call(client: Any, model: str, prompt: str) -> dict[str, Any]:
    request = partial(
        client.chat.completions.create,
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    return _model_step("文本模型", {"model": model, "prompt": prompt}, lambda: _request(request, model))


def _request(request, model: str) -> dict:
    scope = CURRENT.get()
    budget = scope.runtime.resource("model") if scope else nullcontext()
    with budget:
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
    payload = {"start": start, "end": end, "model": model, "prompt": prompt}
    return _model_step(
        "音频模型",
        payload,
        lambda: with_audio(
            media,
            start,
            end,
            {"prefix": s3_prefix, "storage": storage},
            lambda url: audio_model_call(client, model, prompt, url),
        ),
    )


def _model_step(label: str, payload: dict, work):
    scope = CURRENT.get()
    if scope is None:
        return work()
    return scope.runtime.run(
        {"id": label + "/" + fingerprint(payload), "label": label, "input": payload, "cache": False}, work
    )
