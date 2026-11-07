from pathlib import Path
from unittest.mock import Mock

import pytest

from segment.music_agent import detection
from segment.music_agent.boundary_response import InvalidBoundary
from segment.music_agent.runtime import Runtime
from segment.workspace_options import default_options


@pytest.fixture
def scan(monkeypatch):
    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", "2")
    monkeypatch.setattr(detection, "media_duration", lambda _: 130)

    def invoke(request):
        monkeypatch.setattr(detection, "call_with_storage", request)
        return detection.scan_candidates(
            Path("input.mp4"),
            None,
            None,
            chunk_seconds=60,
            chunk_context=10,
            s3_prefix="test",
            model="test",
            scan_concurrency=1,
        )

    return invoke


def response(start=10, end=40):
    return {
        "data": {
            "segments": [
                {
                    "start_seconds": start,
                    "end_seconds": end,
                    "classification": "host_singing",
                    "confidence": 0.95,
                    "host_singing_present": True,
                    "title_hint": "",
                    "rationale": "演唱",
                }
            ]
        },
        "usage": {"prompt_tokens": 1},
    }


def empty_response():
    return {"data": {"segments": []}, "usage": None}


def test_scan_corrects_out_of_range_then_finishes_remaining_chunks(scan, caplog):
    request = Mock(side_effect=[response(end=90), response(end=45), empty_response(), empty_response()])
    candidates, metadata = scan(request)
    assert [(item.start, item.end) for item in candidates] == [(10, 45)]
    assert [item["chunk"] for item in metadata] == [1, 2, 3]
    assert request.call_count == 4
    first, corrected = request.call_args_list[:2]
    assert first.args[1:3] == corrected.args[1:3] == (0, 70)
    assert "0 <= start_seconds < end_seconds <= 70.000000" in first.kwargs["prompt"]
    assert "90" in corrected.kwargs["prompt"]
    assert "时间校验纠正要求" in corrected.kwargs["prompt"]
    assert "end_seconds=90" in caplog.text
    assert metadata[0]["boundary_corrections"][0]["response"]["data"]["segments"][0]["end_seconds"] == 90


def test_context_and_final_short_chunk_use_relative_times(scan):
    request = Mock(side_effect=[empty_response(), response(5, 15), response(10, 20)])
    candidates, metadata = scan(request)
    assert [(item.start, item.end) for item in candidates] == [(55, 65), (120, 130)]
    assert "核心区间为输入音频的 10.000000 到 70.000000 秒" in request.call_args_list[1].kwargs["prompt"]
    assert "总时长为 20.000000 秒" in request.call_args.kwargs["prompt"]
    assert all(not item["boundary_corrections"] for item in metadata)


@pytest.mark.parametrize(
    "start,end", [(-1, 30), (40, 20), (0, float("nan")), (0, float("inf")), (None, 30), ("1:20", 30), (80, 90)]
)
def test_invalid_times_are_explicitly_reasked_and_exhaustion_surfaces(scan, start, end):
    request = Mock(return_value=response(start, end))
    with pytest.raises(InvalidBoundary, match="连续 3 次校验失败"):
        scan(request)
    assert request.call_count == 3


def test_invalid_candidates_outside_core_are_validated_before_filtering(scan):
    request = Mock(side_effect=[response(65, 80), empty_response(), empty_response(), empty_response()])
    candidates, metadata = scan(request)
    assert candidates == []
    assert len(metadata[0]["boundary_corrections"]) == 1
    assert request.call_count == 4


def test_scan_correction_can_be_disabled(scan, monkeypatch):
    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", "0")
    request = Mock(return_value=response(end=90))
    with pytest.raises(InvalidBoundary, match="输入时长=70.000000秒"):
        scan(request)
    assert request.call_count == 1


def test_network_failure_surfaces_without_timestamp_correction(scan):
    request = Mock(side_effect=RuntimeError("connection failed"))
    with pytest.raises(RuntimeError, match="connection failed"):
        scan(request)
    assert request.call_count == 1


@pytest.mark.parametrize("offset", [float("nan"), float("inf"), 1e20])
def test_absolute_time_conversion_preserves_finite_ordered_times(offset):
    with pytest.raises(InvalidBoundary, match="无效候选时间"):
        detection.parse_candidates(response()["data"], offset)


def test_correction_reports_progress_and_completed_chunks_are_reused(scan, tmp_path):
    events = []
    config = {
        "checkpoint_dir": str(tmp_path),
        "source_digest": "test",
        "attempt": 1,
        "options": default_options(),
        "duration": 130,
        "scan_total": 3,
    }
    request = Mock(side_effect=[response(end=90), response(end=45), empty_response(), empty_response()])

    def execute(attempt):
        runtime = Runtime({**config, "attempt": attempt}, report=lambda prefix, event: events.append(event))
        with runtime.activate("scan"):
            return scan(request)

    first = execute(1)
    assert any(event["id"] == "scan/1" and event["state"] == "retrying" for event in events)
    assert events[-1]["state"] == "succeeded"
    assert events[-1]["completed"] == 3
    assert execute(2) == first
    assert request.call_count == 4
    assert len([event for event in events if event["state"] == "reused"]) == 3
