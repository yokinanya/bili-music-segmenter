from unittest.mock import Mock

import pytest

from segment.music_agent.boundary_response import InvalidBoundary
from segment.music_agent.boundary_review import BoundaryOptions, review_boundaries

OPTIONS = BoundaryOptions(100, 200, 1000, 20, 0.85)


def response(start, end):
    return {
        "data": {
            "host_singing_present": True,
            "confidence": 0.95,
            "intervals": [{"start_seconds": start, "end_seconds": end}],
            "song_groups": [[0]],
        },
        "usage": {"prompt_tokens": 1},
    }


def test_invalid_boundary_is_reasked_without_clamping(monkeypatch, caplog):
    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", "2")
    request = Mock(side_effect=[response(20, 200), response(20, 120)])
    intervals, audit = review_boundaries(OPTIONS, request)
    assert intervals == [(100, 200)]
    assert request.call_count == 2
    assert request.call_args.args == (80, 220)
    assert "140.000000" in request.call_args.kwargs["correction"]
    assert "200" in request.call_args.kwargs["correction"]
    assert audit["boundary_corrections"][0]["response"]["data"]["intervals"][0]["end_seconds"] == 200
    assert "interval=" in caplog.text


@pytest.mark.parametrize("start,end", [(20, 200), (-1, 20), (40, 30), (0, float("nan")), ("1:20", 120), (None, 120)])
def test_exhausted_corrections_surface_error(monkeypatch, start, end):
    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", "2")
    request = Mock(return_value=response(start, end))
    with pytest.raises(InvalidBoundary, match="连续 3 次"):
        review_boundaries(OPTIONS, request)
    assert request.call_count == 3


def test_correction_can_be_disabled(monkeypatch):
    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", "0")
    request = Mock(return_value=response(20, 200))
    with pytest.raises(InvalidBoundary, match="输入时长=140"):
        review_boundaries(OPTIONS, request)
    assert request.call_count == 1


def test_request_failure_is_not_retried(monkeypatch):
    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", "2")
    request = Mock(side_effect=RuntimeError("connection failed"))
    with pytest.raises(RuntimeError, match="connection failed"):
        review_boundaries(OPTIONS, request)
    assert request.call_count == 1


def grouped_response(groups):
    base = response(20, 40)
    return {
        **base,
        "data": {
            **base["data"],
            "intervals": [
                {"start_seconds": 20, "end_seconds": 40},
                {"start_seconds": 50, "end_seconds": 70},
            ],
            "song_groups": groups,
        },
    }


@pytest.mark.parametrize(
    "groups",
    [
        [[0], [0, 1]],
        [[1], [0]],
        [[0]],
        [[0, 2]],
        [[1, 2]],
        [[False, 1]],
        [["0", 1]],
        [[0.0, 1]],
        [[0], []],
        "0,1",
        None,
        [],
    ],
)
def test_invalid_groups_are_reasked_with_exact_index_rules(monkeypatch, groups, caplog):
    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", "2")
    invalid = grouped_response(groups)
    request = Mock(side_effect=[invalid, grouped_response([[0, 1]])])
    intervals, audit = review_boundaries(OPTIONS, request)
    assert intervals == [(100, 150)]
    assert request.call_count == 2
    assert request.call_args.args == (80, 220)
    correction = request.call_args.kwargs["correction"]
    assert "song_groups" in correction and "[0, 1]" in correction
    assert "零起始编号" in correction and "每个区间恰好出现一次" in correction
    assert audit["boundary_corrections"][0]["response"] == invalid
    assert "song_groups" in caplog.text
    assert invalid["data"]["song_groups"] == groups


@pytest.mark.parametrize("retries", [0, 2])
def test_invalid_groups_still_surface_after_configured_corrections(monkeypatch, retries):
    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", str(retries))
    request = Mock(return_value=grouped_response([[0], [0, 1]]))
    with pytest.raises(InvalidBoundary, match=rf"song_groups.*连续 {retries + 1} 次校验失败"):
        review_boundaries(OPTIONS, request)
    assert request.call_count == retries + 1


def test_corrected_grouping_can_change_the_number_of_intervals(monkeypatch):
    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", "2")
    corrected = grouped_response([[0, 1], [2]])
    corrected["data"]["intervals"].append({"start_seconds": 80, "end_seconds": 100})
    request = Mock(side_effect=[grouped_response([[1, 2]]), corrected])
    intervals, _ = review_boundaries(OPTIONS, request)
    assert intervals == [(100, 150), (160, 180)]
    assert "按新数组重新编号" in request.call_args.kwargs["correction"]


def test_unsorted_intervals_are_reasked_without_reordering_them(monkeypatch):
    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", "2")
    invalid = grouped_response([[0], [1]])
    invalid["data"]["intervals"].reverse()
    request = Mock(side_effect=[invalid, grouped_response([[0], [1]])])
    intervals, audit = review_boundaries(OPTIONS, request)
    assert intervals == [(100, 120), (130, 150)]
    assert audit["boundary_corrections"][0]["response"]["data"]["intervals"][0]["start_seconds"] == 50


def test_refine_candidate_passes_group_correction_and_review_instruction(monkeypatch):
    from segment.music_agent import detection

    monkeypatch.setenv("MUSIC_AGENT_BOUNDARY_RETRIES", "2")
    monkeypatch.setattr(detection, "media_duration", lambda _: 1000)
    request = Mock(side_effect=[grouped_response([[1, 2]]), grouped_response([[0, 1]])])
    monkeypatch.setattr(detection, "call_with_storage", request)
    candidate = detection.Candidate(1, 100, 200, "host_singing", 0.95, True, "", "")
    intervals, audit = detection.refine_candidate(
        None,
        candidate,
        None,
        None,
        context_seconds=20,
        s3_prefix="test",
        model="audio-model",
        minimum_confidence=0.85,
        review_instruction="确认是否为同一首歌",
    )
    assert intervals == [(100, 150)] and request.call_count == 2
    initial, corrected = request.call_args_list
    assert initial.args[1:3] == corrected.args[1:3] == (80, 220)
    assert "从左到右展开" in initial.kwargs["prompt"]
    assert "边界与分组纠正要求" in corrected.kwargs["prompt"]
    assert "零起始编号 [0, 1]" in corrected.kwargs["prompt"]
    assert "确认是否为同一首歌" in corrected.kwargs["prompt"]
    assert audit["boundary_corrections"][0]["response"]["data"]["song_groups"] == [[1, 2]]
