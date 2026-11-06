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
