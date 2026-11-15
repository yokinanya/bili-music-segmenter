import asyncio
from types import SimpleNamespace

import pytest

from segment.music_agent.runtime import Runtime
from segment.workspace_store import DocumentStore


def runtime(tmp_path, name, **config):
    value = Runtime(
        {
            "checkpoint_dir": str(tmp_path / name),
            "source_digest": "same-source",
            "attempt": 1,
            **config,
        },
        report=lambda *args: None,
    )
    value.result_store = DocumentStore(tmp_path / "workspace.sqlite3")
    return value


SPEC = {"id": "audio-scan", "label": "扫描", "input": ["model-a", "prompt-a", "audio-hash"], "shared": True}


def test_model_result_is_reused_across_jobs(tmp_path):
    first = runtime(tmp_path, "first")
    second = runtime(tmp_path, "second")
    assert first.run(SPEC, lambda: {"segments": [10, 30]}) == {"segments": [10, 30]}

    def unexpected():
        pytest.fail("a matching result must not call the model again")

    assert second.run(SPEC, unexpected) == {"segments": [10, 30]}
    assert second._steps["audio-scan"]["state"] == "reused"


def test_recognizer_result_is_reused_across_jobs(tmp_path):
    first, second = runtime(tmp_path, "first"), runtime(tmp_path, "second")
    result = {"title": "稻香", "artist": "周杰伦"}

    async def identify():
        return result

    async def unexpected():
        pytest.fail("a matching result must not run recognition again")

    asyncio.run(first.async_run(SPEC, identify))
    assert asyncio.run(second.async_run(SPEC, unexpected)) == result


@pytest.mark.parametrize(
    "change",
    [
        {"source_digest": "new-source"},
        {"refresh_recognition": True},
    ],
)
def test_changed_source_or_explicit_refresh_does_not_reuse(tmp_path, change):
    runtime(tmp_path, "first").run(SPEC, lambda: "old")
    assert runtime(tmp_path, "second", **change).run(SPEC, lambda: "fresh") == "fresh"


def test_changed_model_or_prompt_does_not_reuse(tmp_path):
    runtime(tmp_path, "first").run(SPEC, lambda: "old")
    changed = {**SPEC, "input": ["model-b", "prompt-b", "audio-hash"]}
    assert runtime(tmp_path, "second").run(changed, lambda: "fresh") == "fresh"


def test_failed_call_is_not_cached(tmp_path):
    def fail():
        raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        runtime(tmp_path, "first").run(SPEC, fail)
    assert runtime(tmp_path, "second").run(SPEC, lambda: "fresh") == "fresh"


def test_explicit_refresh_also_skips_local_checkpoint(tmp_path):
    runtime(tmp_path, "same-job").run(SPEC, lambda: "old")
    assert runtime(tmp_path, "same-job", refresh_recognition=True).run(SPEC, lambda: "fresh") == "fresh"


def test_model_audio_content_cache_does_not_repeat_usage(tmp_path, monkeypatch):
    from segment.music_agent import gemini

    requests, usage_events = [], []

    def create(**kwargs):
        requests.append(kwargs)
        usage = SimpleNamespace(total_input_tokens=10, total_output_tokens=2, total_cached_tokens=0)
        return SimpleNamespace(output_text='{"segments": []}', usage=usage)

    monkeypatch.setattr(gemini, "report_usage", lambda *args: usage_events.append(args))
    client = object.__new__(gemini.GeminiClient)
    client._client = SimpleNamespace(interactions=SimpleNamespace(create=create))
    client.model = "model-a"
    results = []
    for name in ("temporary-a", "temporary-b"):
        audio = tmp_path / f"{name}.wav"
        audio.write_bytes(b"same audio bytes")
        worker = runtime(tmp_path, name)
        results.append(
            worker.run(
                {"id": "uncached-parent", "label": "扫描入口", "cache": False},
                lambda: client.json_call(audio, "same prompt", {"type": "object"}),
            )
        )
    assert results[0] == results[1]
    assert len(requests) == 1
    assert len(usage_events) == 1
