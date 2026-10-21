import time
from pathlib import Path
from threading import Barrier, Lock
from unittest.mock import Mock

import pytest

from segment.music_agent import detection
from segment.upload_progress import UploadProgress

WORKERS = 3
WINDOW_COUNT = 6
DELAY_SECONDS = 0.005


def test_scan_concurrency_limit_and_order(monkeypatch):
    barrier = Barrier(WORKERS, timeout=5)
    lock = Lock()
    active = 0
    peak = 0
    storage = Mock()
    monkeypatch.setattr(detection, "media_duration", lambda _: WINDOW_COUNT)
    monkeypatch.setattr(detection, "extract_wav", lambda *args: None)

    def call(*args):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        barrier.wait()
        time.sleep(DELAY_SECONDS)
        with lock:
            active -= 1
        return {"data": {"segments": []}, "usage": None}

    monkeypatch.setattr(detection, "audio_model_call", call)
    candidates, metadata = detection.scan_candidates(
        Path("input.mp4"),
        None,
        storage,
        chunk_seconds=1,
        chunk_context=0,
        s3_prefix="test",
        model="test",
        scan_concurrency=WORKERS,
    )
    assert peak == WORKERS
    assert candidates == []
    assert [row["chunk"] for row in metadata] == list(range(1, WINDOW_COUNT + 1))
    assert storage.delete.call_count == WINDOW_COUNT


@pytest.mark.parametrize("workers", [1, WORKERS])
def test_scan_failures_propagate_and_cleanup(monkeypatch, workers):
    storage = Mock()
    monkeypatch.setattr(detection, "media_duration", lambda _: WINDOW_COUNT)
    monkeypatch.setattr(detection, "extract_wav", lambda *args: None)
    monkeypatch.setattr(detection, "audio_model_call", Mock(side_effect=RuntimeError("API failure")))
    with pytest.raises(RuntimeError, match="API failure"):
        detection.scan_candidates(
            Path("input.mp4"),
            None,
            storage,
            chunk_seconds=1,
            chunk_context=0,
            s3_prefix="test",
            model="test",
            scan_concurrency=workers,
        )
    assert storage.upload.call_count == storage.delete.call_count


def test_first_failure_stops_sending_further_chunks(monkeypatch):
    storage = Mock()
    monkeypatch.setattr(detection, "media_duration", lambda _: 40)
    monkeypatch.setattr(detection, "extract_wav", lambda *args: None)
    calls = []
    lock = Lock()

    def call(*args):
        with lock:
            calls.append(args)
        if len(calls) == 1:
            raise RuntimeError("API failure")
        return {"data": {"segments": []}, "usage": None}

    monkeypatch.setattr(detection, "audio_model_call", call)
    with pytest.raises(RuntimeError, match="API failure"):
        detection.scan_candidates(
            Path("input.mp4"),
            None,
            storage,
            chunk_seconds=10,
            chunk_context=0,
            s3_prefix="test",
            model="test",
            scan_concurrency=1,
        )
    # Serial execution must give up right after the failing chunk instead of scanning the rest.
    assert len(calls) == 1
    assert storage.upload.call_count == storage.delete.call_count


def test_border_candidates_are_merged_not_reviewed_twice():
    # Two adjacent chunks report the same song with a slightly different start.
    first = detection.Candidate(1, 100, 400, "host_singing", 0.9, True, "", "")
    second = detection.Candidate(2, 397, 460, "host_singing", 0.9, True, "", "")
    merged = detection.merge_candidates([first, second], max_gap=detection.BORDER_DUPLICATE_SECONDS)
    assert len(merged) == 1
    assert (merged[0].start, merged[0].end) == (100, 460)


def test_merge_keeps_genuinely_different_songs():
    first = detection.Candidate(1, 100, 200, "host_singing", 0.9, True, "", "")
    second = detection.Candidate(2, 260, 360, "host_singing", 0.9, True, "", "")
    merged = detection.merge_candidates([first, second], max_gap=detection.BORDER_DUPLICATE_SECONDS)
    assert [(item.start, item.end) for item in merged] == [(100, 200), (260, 360)]


def test_uploads_do_not_overwrite_each_other():
    progress = UploadProgress()
    first = {"key": "first", "total_bytes": 100, "transferred_bytes": 10, "state": "uploading"}
    second = {**first, "key": "second"}
    progress.update(first)
    progress.update(second)
    progress.update({**first, "transferred_bytes": 100, "state": "completed"})
    result = progress.snapshot()["uploads"]
    assert len(result) == 2
    assert result[0]["state"] == "completed"
    assert result[1]["transferred_bytes"] == 10
