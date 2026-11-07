"""Composition root for the resumable concurrent music-cut pipeline."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from segment.music_agent.audio_cache import AudioCache
from segment.music_agent.config import load_config
from segment.music_agent.detection import refine_candidate, scan_candidates
from segment.music_agent.export import export_video, make_clip_path
from segment.music_agent.media import extract_recognition_audio, media_duration
from segment.music_agent.media_cache import LocalMediaCache
from segment.music_agent.models import call_with_storage, text_model_call
from segment.music_agent.pipeline import execute_pipeline
from segment.music_agent.pipeline_context import PipelineContext
from segment.music_agent.pipeline_services import PipelineServices
from segment.music_agent.qqmusic_client import search_lyrics
from segment.music_agent.recognition import deterministic_title_choice, recognize_audio, resolve_title_with_model
from segment.music_agent.runtime import create_runtime
from segment.music_agent.storage import create_storage
from segment.music_agent.title_resolution import needs_audio_title, resolve_audio_title
from segment.workspace_options import default_options, validate_options
from segment.workspace_store import DocumentStore

OMNI_MODEL = "qwen3.8-omni-flash"
TITLE_MODEL = "qwen3.8-flash"
MODEL_TIMEOUT_SECONDS = 900


async def run_agent(media: Path, output_dir: Path, **settings) -> Path:
    from openai import OpenAI

    media = media.expanduser().resolve()
    if not media.is_file():
        raise FileNotFoundError(media)
    options = _options(settings)
    config = load_config()
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = create_runtime(media, output_dir, {key: options[key] for key in default_options()})
    runtime.config["media_threads"] = max(1, (os.cpu_count() or 1) // options["media_concurrency"])
    storage = create_storage(config)
    store = DocumentStore(Path(runtime.config["state_dir"]) / "workspace.sqlite3")
    runtime.audio_cache = AudioCache(storage, runtime.config, store)
    runtime.local_cache = LocalMediaCache(store, runtime.config)
    if options["use_shazam"]:
        from shazamio import Shazam

        runtime.shazam_client = Shazam()
    client = OpenAI(api_key=config.api_key, base_url=config.base_url, timeout=MODEL_TIMEOUT_SECONDS, max_retries=0)
    context = PipelineContext(
        media=media,
        output=output_dir,
        options=options,
        services=_services(options),
        runtime=runtime,
        client=client,
        storage=storage,
        prefix=config.s3_prefix,
    )
    try:
        with runtime.activate():
            result = await execute_pipeline(context)
    finally:
        if client is not None:
            client.close()
    requested = settings.get("manifest_path")
    if requested and Path(requested) != result:
        Path(requested).write_bytes(result.read_bytes())
        return Path(requested)
    return result


def _options(settings: dict) -> dict:
    defaults = default_options()
    overrides = {key: value for key, value in settings.items() if key in defaults}
    extras = {
        "audio_model": OMNI_MODEL,
        "title_model": TITLE_MODEL,
        "summary_model": TITLE_MODEL,
        "netease_cookie": "",
        "recognizer_timeout": 60,
    }
    unknown = settings.keys() - defaults.keys() - extras.keys() - {"manifest_path"}
    if unknown:
        raise TypeError(f"未知参数：{', '.join(sorted(unknown))}")
    extra_values = {key: settings.get(key, value) for key, value in extras.items()}
    if extra_values["recognizer_timeout"] <= 0:
        raise ValueError("识曲超时必须为正")
    return {**validate_options(overrides, defaults), **extra_values}


def _services(options: dict) -> PipelineServices:
    return PipelineServices(
        calls={
            "duration": media_duration,
            "scan": scan_candidates,
            "refine": refine_candidate,
            "recognize": recognize_audio,
            "qqmusic": search_lyrics,
            "text": text_model_call,
            "audio": call_with_storage,
            "choose_title": deterministic_title_choice,
            "resolve_text": resolve_title_with_model,
            "needs_audio": needs_audio_title,
            "audio_title": resolve_audio_title,
            "extract_reference": extract_recognition_audio,
            "clip_path": make_clip_path,
            "export": export_video,
        },
        recognizer_budget=asyncio.Semaphore(options["recognizer_concurrency"]),
    )
