"""Google Gemini 官方接口客户端：结构化 JSON、音频内联与代理支持。"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from google import genai
from google.genai import types

from segment.usage import report_usage

DEFAULT_MODEL = "gemini-3.8-flash"
THINKING_LEVEL = "high"
# 内联 base64 上限 20MB（含 prompt）；留出余量避免恰好越界。更大的音频走 Files API。
INLINE_LIMIT_BYTES = 19_000_000
UPLOAD_ACTIVE_TIMEOUT_SECONDS = 300
UPLOAD_POLL_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 1800
LOGGER = logging.getLogger(__name__)


class GeminiConfig:
    """从环境读取 Gemini 凭据与代理；代理为空时直连。"""

    def __init__(
        self,
        api_key: str,
        proxy: str | None,
        base_url: str | None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        if not api_key:
            raise ValueError("请配置 GEMINI_API_KEY")
        if proxy and "://" not in proxy:
            raise ValueError("GEMINI_PROXY 必须带协议，例如 http://127.0.0.1:7890")
        self.api_key = api_key
        self.proxy = proxy
        self.base_url = base_url
        self.model = model


class GeminiClient:
    """一次音频输入 → 符合 JSON Schema 的结构化结果。"""

    def __init__(self, config: GeminiConfig, workdir: Path | None = None) -> None:
        self._audio_directory = tempfile.TemporaryDirectory(prefix="gemini-audio-", dir=workdir)
        self._workdir = Path(self._audio_directory.name)
        http_options = types.HttpOptions(timeout=REQUEST_TIMEOUT_SECONDS * 1000)
        if config.base_url:
            http_options.base_url = config.base_url
        # google-genai 不透出 proxy 参数，通过自建 httpx 客户端注入。
        http_options.httpx_client = _http_client(config.proxy)
        self._client = genai.Client(api_key=config.api_key, http_options=http_options)
        self.model = config.model

    def close(self) -> None:
        try:
            self._client.close()
        finally:
            self._audio_directory.cleanup()

    def audio_window(self, media: Path, start: float, end: float, extract) -> Path:
        destination = self._workdir / f"window-{start:.3f}-{end:.3f}.wav"
        if not destination.exists():
            extract(media, start, end, destination)
        return destination

    def json_call(
        self,
        audio: Path | None,
        prompt: str,
        schema: dict[str, Any],
        *,
        model: str | None = None,
        label: str = "Gemini 调用",
        cache: bool = True,
    ) -> dict[str, Any]:
        from segment.music_agent.json_response import parse_json
        from segment.music_agent.runtime import CURRENT, file_digest, fingerprint

        chosen = model or self.model
        scope = CURRENT.get()
        audio_key = file_digest(audio) if audio is not None and scope is not None else None
        request_key = [audio_key, chosen, THINKING_LEVEL, prompt, schema]
        identity = label + "/" + fingerprint(request_key)

        def perform() -> dict[str, Any]:
            inputs: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
            uploaded = None
            if audio is not None:
                if audio.stat().st_size > INLINE_LIMIT_BYTES:
                    uploaded = self._upload(audio)
                    inputs.insert(0, {"type": "audio", "uri": uploaded.uri, "mime_type": uploaded.mime_type})
                else:
                    inputs.insert(0, _audio_input(audio))
            try:
                interaction = self._client.interactions.create(
                    model=chosen,
                    input=inputs,
                    generation_config={"thinking_level": THINKING_LEVEL},
                    response_format={"type": "text", "mime_type": "application/json", "schema": schema},
                )
            finally:
                # 上传文件 48 小时自动过期，这里立即释放，避免堆积占用存储配额。
                if uploaded is not None:
                    self._client.files.delete(name=uploaded.name)
            return _read_response(interaction, chosen, parse_json)

        if scope is None:
            return perform()
        return scope.runtime.run(
            {"id": identity, "label": label, "input": request_key, "shared": True, "cache": cache}, perform
        )

    def _upload(self, audio: Path) -> Any:
        uploaded = self._client.files.upload(file=audio, config=types.UploadFileConfig(mime_type="audio/wav"))
        deadline = time.monotonic() + UPLOAD_ACTIVE_TIMEOUT_SECONDS
        while uploaded.state == types.FileState.PROCESSING:
            if time.monotonic() > deadline:
                self._client.files.delete(name=uploaded.name)
                raise TimeoutError(f"Gemini 文件 {audio.name} 长时间处于 PROCESSING")
            time.sleep(UPLOAD_POLL_SECONDS)
            uploaded = self._client.files.get(name=uploaded.name)
        if uploaded.state == types.FileState.FAILED:
            self._client.files.delete(name=uploaded.name)
            raise ValueError(f"Gemini 文件 {audio.name} 处理失败：{uploaded.error}")
        return uploaded


def _read_response(interaction: Any, model: str, parse) -> dict:
    usage = _usage(interaction.usage)
    report_usage(model, usage)
    text = (interaction.output_text or "").strip()
    status = getattr(interaction, "status", None)
    metadata = {
        "id": getattr(interaction, "id", None),
        "status": getattr(status, "value", status),
        "output_characters": len(text),
        "has_continuation": bool(getattr(interaction, "continuation_token", None)),
    }
    try:
        if not text:
            raise ValueError(f"Gemini 模型 {model} 返回空响应")
        if metadata["status"] not in (None, "completed"):
            raise ValueError(f"Gemini 响应未完成：{metadata['status']}")
        data = parse(text)
    except ValueError as error:
        LOGGER.error("Gemini 响应无效 model=%s metadata=%s usage=%s error=%s", model, metadata, usage, error)
        raise ValueError(f"{error}；响应诊断：{metadata}") from error
    return {"data": data, "usage": usage, "response_metadata": metadata}


def _http_client(proxy: str | None) -> httpx.Client:
    kwargs: dict[str, Any] = {"timeout": REQUEST_TIMEOUT_SECONDS}
    if proxy:
        kwargs["proxy"] = proxy
        # 显式代理优先，避免环境变量里的代理再次叠加。
        kwargs["trust_env"] = False
    return httpx.Client(**kwargs)


def _audio_input(audio: Path) -> dict[str, Any]:
    size = audio.stat().st_size
    if size > INLINE_LIMIT_BYTES:
        raise ValueError(f"音频 {audio.name} 为 {size} 字节，超过内联上限；需改用 Files API 或缩短窗口")
    return {
        "type": "audio",
        "data": base64.b64encode(audio.read_bytes()).decode("ascii"),
        "mime_type": "audio/wav",
    }


def _usage(usage: Any) -> dict[str, int] | None:
    if usage is None:
        return None
    return {
        "total_input_tokens": getattr(usage, "total_input_tokens", 0) or 0,
        "total_output_tokens": getattr(usage, "total_output_tokens", 0) or 0,
        "total_cached_tokens": getattr(usage, "total_cached_tokens", 0) or 0,
    }


def gemini_config_from_env(model: str = DEFAULT_MODEL) -> GeminiConfig:
    return GeminiConfig(
        api_key=os.getenv("GEMINI_API_KEY", "").strip(),
        proxy=os.getenv("GEMINI_PROXY", "").strip() or None,
        base_url=os.getenv("GEMINI_BASE_URL", "").strip() or None,
        model=model,
    )
