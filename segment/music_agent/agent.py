"""Composition root for the resumable concurrent music-cut pipeline."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

from segment.music_agent.config import load_config
from segment.music_agent.export import export_video
from segment.music_agent.gemini import GeminiClient
from segment.music_agent.media import extract_recognition_audio, media_duration
from segment.music_agent.media_cache import LocalMediaCache
from segment.music_agent.pipeline import execute_pipeline
from segment.music_agent.pipeline_context import PipelineContext
from segment.music_agent.pipeline_services import PipelineServices
from segment.music_agent.recognition import deterministic_title_choice, recognize_audio
from segment.music_agent.runtime import FIXED_BUDGETS, create_runtime
from segment.music_agent.scan_gemini import scan_candidates
from segment.workspace_options import default_options, validate_options
from segment.workspace_store import DocumentStore

# 出点位使用 Gemini 音频模型；标题与切分结果直接来自识曲，不再走模型裁决。
AUDIO_MODEL = "gemini-4-hydrogen"


async def run_agent(media: Path, output_dir: Path, **settings) -> Path:
    media = media.expanduser().resolve()
    if not media.is_file():
        raise FileNotFoundError(media)
    options = _options(settings)
    config = load_config()
    output_dir.mkdir(parents=True, exist_ok=True)
    runtime = create_runtime(media, output_dir, {key: options[key] for key in default_options()})
    runtime.config["media_threads"] = max(1, (os.cpu_count() or 1) // FIXED_BUDGETS["media"])
    store = DocumentStore(Path(runtime.config["state_dir"]) / "workspace.sqlite3")
    runtime.local_cache = LocalMediaCache(store, runtime.config)
    if options["use_shazam"]:
        from shazamio import Shazam

        runtime.shazam_client = Shazam()
    client = GeminiClient(config.gemini, workdir=Path(runtime.config["state_dir"]))
    context = PipelineContext(
        media=media,
        output=output_dir,
        options=options,
        services=_services(options),
        runtime=runtime,
        client=client,
    )
    try:
        with runtime.activate():
            result = await execute_pipeline(context)
    finally:
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
        "audio_model": AUDIO_MODEL,
        "netease_cookie": "",
    }
    unknown = settings.keys() - defaults.keys() - extras.keys() - {"manifest_path"}
    if unknown:
        raise TypeError(f"未知参数：{', '.join(sorted(unknown))}")
    extra_values = {key: settings.get(key, value) for key, value in extras.items()}
    return {**validate_options(overrides, defaults), **extra_values}


def _services(options: dict) -> PipelineServices:
    return PipelineServices(
        calls={
            "duration": media_duration,
            "scan": scan_candidates,
            "recognize": recognize_audio,
            "choose_title": deterministic_title_choice,
            "extract_reference": extract_recognition_audio,
            "export": export_video,
        },
        recognizer_budget=asyncio.Semaphore(FIXED_BUDGETS["recognizer"]),
        netease_budget=asyncio.Semaphore(FIXED_BUDGETS["netease"]),
    )
