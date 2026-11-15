"""Gemini 扫描的相对时间解析、跨块去重与按需边界复核。"""

from types import SimpleNamespace

import pytest

from segment.music_agent import scan_gemini
from segment.music_agent.boundaries import InvalidBoundary


def segment(start, end, **extra):
    return {"start_seconds": start, "end_seconds": end, **extra}


def test_parse_candidates_rejects_invalid_model_values():
    window = scan_gemini.Window(0, 100, 0, 100)
    with pytest.raises(InvalidBoundary, match="超出输入范围"):
        scan_gemini.parse_candidates({"segments": [segment(10, 200)]}, window)
    with pytest.raises(ValueError, match="无效歌曲分类"):
        scan_gemini.parse_candidates({"segments": [segment(10, 20, classification="karaoke")]}, window)
    with pytest.raises(ValueError, match="无效候选置信度"):
        scan_gemini.parse_candidates(
            {"segments": [segment(10, 20, classification="host_singing", confidence=1.5)]}, window
        )


def test_parse_candidates_offsets_times_by_window_start():
    window = scan_gemini.Window(100, 160, 100, 160)
    data = {"segments": [segment(10, 60, classification="host_singing", title_hint="稻香")]}
    candidate = scan_gemini.parse_candidates(data, window)[0]
    assert (candidate.start, candidate.end, candidate.title_hint) == (110, 160, "稻香")


def test_merge_candidates_only_joins_same_song_border_duplicates():
    same = [
        scan_gemini.Candidate(0, 10, 100, "host_singing", 0.9, True, "歌A", ""),
        scan_gemini.Candidate(0, 90, 200, "host_singing", 0.8, True, "歌A", ""),
    ]
    assert [(item.start, item.end) for item in scan_gemini.merge_candidates(same)] == [(10, 200)]

    different = [
        scan_gemini.Candidate(0, 10, 100, "host_singing", 0.9, True, "歌A", ""),
        scan_gemini.Candidate(0, 95, 200, "host_singing", 0.9, True, "歌B", ""),
    ]
    assert len(scan_gemini.merge_candidates(different)) == 2


def test_scan_prompt_declares_whole_or_chunk_mode():
    whole = scan_gemini.scan_prompt(scan_gemini.Window(0, 500, 0, 500))
    assert "整场音频" in whole and "核心区间为输入音频" not in whole
    chunk = scan_gemini.scan_prompt(scan_gemini.Window(600, 1200, 570, 1230))
    assert "核心区间为输入音频的 30.000 到 630.000 秒" in chunk


def fake_client(payload, calls):
    def json_call(audio, prompt, schema, *, model=None, label=""):
        calls.append({"audio": audio, "label": label})
        return {"data": payload, "usage": None}

    def audio_window(media, start, end, extract):
        return f"{media}#{start}-{end}"

    return SimpleNamespace(json_call=json_call, audio_window=audio_window)


def test_scan_candidates_reindexes_candidates_and_records_usage(monkeypatch):
    monkeypatch.setattr(scan_gemini, "media_duration", lambda _: 500)
    payload = {"segments": [segment(100, 300, classification="host_singing", title_hint="长歌")]}
    calls = []
    candidates, chunks = scan_gemini.scan_candidates(
        "in.mp4", fake_client(payload, calls), chunk_seconds=600, chunk_context=30, minimum_seconds=30
    )
    assert [(item.index, item.title_hint) for item in candidates] == [(1, "长歌")]
    assert len(chunks) == 1 and calls[0]["label"] == "扫描分块 1"


def test_chunked_scan_keeps_each_candidate_only_in_its_core(monkeypatch):
    monkeypatch.setattr(scan_gemini, "media_duration", lambda _: 1900)
    payload = {
        "segments": [
            segment(0, 20, classification="host_singing", title_hint="首块"),
            segment(60, 120, classification="host_singing", title_hint="本块"),
        ]
    }
    candidates, chunks = scan_gemini.scan_candidates(
        "in.mp4", fake_client(payload, []), chunk_seconds=600, chunk_context=30, minimum_seconds=1
    )
    assert len(chunks) == 4
    assert {item.title_hint for item in candidates} == {"首块", "本块"}


def test_chunked_scan_runs_windows_concurrently_and_keeps_order(monkeypatch):
    """分块之间是独立请求，串行会把总耗时放大成窗口数倍。"""
    import threading
    import time

    monkeypatch.setattr(scan_gemini, "media_duration", lambda _: 1900)
    lock = threading.Lock()
    state = {"active": 0, "peak": 0}
    seen: list[str] = []

    def json_call(audio, prompt, schema, *, model=None, label=""):
        with lock:
            seen.append(label)
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
        time.sleep(0.1)
        with lock:
            state["active"] -= 1
        return {"data": {"segments": [segment(10, 20, classification="host_singing")]}, "usage": None}

    client = SimpleNamespace(
        json_call=json_call, audio_window=lambda media, start, end, extract: f"{media}#{start}-{end}"
    )
    _, chunks = scan_gemini.scan_candidates("in.mp4", client, chunk_seconds=600, chunk_context=30, minimum_seconds=1)
    assert state["peak"] > 1, "window scans ran one at a time"
    assert len(seen) == len(chunks) == 4
    # 结果仍按窗口顺序回填，chunk 编号不能随完成顺序变化。
    assert [chunk["chunk"] for chunk in chunks] == [1, 2, 3, 4]
    assert [chunk["audio_start"] for chunk in chunks] == sorted(chunk["audio_start"] for chunk in chunks)


def test_border_tolerance_only_applies_to_chunk_boundaries():
    """整场扫描时不存在跨块重复，间隔几秒的不同演唱不能被合并。"""
    gap = [
        scan_gemini.Candidate(1, 100, 200, "host_singing", 0.9, True, "", ""),
        scan_gemini.Candidate(2, 204, 300, "host_singing", 0.9, True, "", ""),
    ]
    assert len(scan_gemini.merge_candidates(gap)) == 2


def test_chunked_scan_still_joins_a_song_split_across_the_border():
    first = scan_gemini.Candidate(1, 100, 590, "host_singing", 0.9, True, "", "")
    second = scan_gemini.Candidate(2, 592, 700, "host_singing", 0.9, True, "", "")
    merged = scan_gemini.merge_candidates([first, second], max_gap=5.0)
    assert [(item.start, item.end) for item in merged] == [(100, 700)]


@pytest.mark.parametrize("bad", ["reversed", "outside", "json"])
def test_invalid_chunk_is_requested_again_with_correction(monkeypatch, bad):
    import json

    monkeypatch.setattr(scan_gemini, "media_duration", lambda _: 600)
    prompts = []

    def call(audio, prompt, schema, **kwargs):
        prompts.append(prompt)
        if len(prompts) == 1:
            if bad == "json":
                raise json.JSONDecodeError("Unterminated string", '{"segments": "', 13)
            start, end = (558, 173) if bad == "reversed" else (651, 953)
        else:
            start, end = 100, 200
        return {"data": {"segments": [segment(start, end, classification="host_singing")]}, "usage": None}

    client = fake_client({}, [])
    client.json_call = call
    candidates, chunks = scan_gemini.scan_candidates(
        "in.mp4", client, chunk_seconds=600, chunk_context=30, minimum_seconds=1
    )
    assert [(item.start, item.end) for item in candidates] == [(100, 200)]
    assert len(prompts) == 2 and prompts[0] != prompts[1]
    assert chunks[0]["attempt_errors"]


def test_failed_chunk_preserves_other_chunks_and_runtime_context(monkeypatch, tmp_path):
    from segment.music_agent.runtime import CURRENT, Runtime

    monkeypatch.setattr(scan_gemini, "media_duration", lambda _: 1200)
    runtime = Runtime({"checkpoint_dir": str(tmp_path), "source_digest": "src", "attempt": 1}, report=lambda *a: None)
    contexts = []

    def call(audio, prompt, schema, **kwargs):
        contexts.append(CURRENT.get())
        if "#600.0-1200" in audio:
            raise ValueError("invalid JSON response")
        return {"data": {"segments": [segment(100, 200, classification="host_singing")]}, "usage": None}

    client = fake_client({}, [])
    client.json_call = call
    with runtime.activate():
        candidates, chunks = scan_gemini.scan_candidates(
            "in.mp4", client, chunk_seconds=600, chunk_context=0, minimum_seconds=1
        )
    assert len(candidates) == 1
    assert chunks[1]["state"] == "failed" and chunks[1]["error"]
    assert all(context.runtime is runtime for context in contexts)
    contexts.clear()
    with runtime.activate():
        _, retried = scan_gemini.scan_candidates(
            "in.mp4", client, chunk_seconds=600, chunk_context=0, minimum_seconds=1
        )
    assert len(contexts) == 2  # Only the failed window's two attempts run again.
    assert retried[0]["state"] == "succeeded"


def test_all_failed_chunks_are_not_reported_as_empty_success(monkeypatch):
    monkeypatch.setattr(scan_gemini, "media_duration", lambda _: 600)
    client = fake_client({"segments": [segment(800, 900, classification="host_singing")]}, [])
    candidates, chunks = scan_gemini.scan_candidates(
        "in.mp4", client, chunk_seconds=600, chunk_context=0, minimum_seconds=1
    )
    assert candidates == []
    assert chunks[0]["state"] == "failed"
    assert "800" in chunks[0]["error"]


def test_request_schema_bounds_times_to_each_audio_window(monkeypatch):
    monkeypatch.setattr(scan_gemini, "media_duration", lambda _: 700)
    captured = {}

    def call(audio, prompt, schema, **kwargs):
        captured[audio] = schema["properties"]["segments"]["items"]["properties"]
        return {"data": {"segments": []}, "usage": None}

    client = fake_client({}, [])
    client.json_call = call
    scan_gemini.scan_candidates("in.mp4", client, chunk_seconds=600, chunk_context=0, minimum_seconds=1)
    for audio, duration in [("in.mp4#0.0-600.0", 600), ("in.mp4#600.0-700", 100)]:
        for field in ("start_seconds", "end_seconds"):
            assert captured[audio][field]["minimum"] == 0
            assert captured[audio][field]["maximum"] == duration
