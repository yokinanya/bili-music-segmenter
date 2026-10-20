from unittest.mock import Mock

import pytest

from segment.music_agent.boundary_review import BoundaryOptions, review_boundaries


def response(intervals, **extra):
    return {
        "data": {
            "host_singing_present": True,
            "confidence": 0.95,
            "intervals": [{"start_seconds": a, "end_seconds": b} for a, b in intervals],
            **extra,
        },
        "usage": None,
    }


def test_same_song_group_includes_interlude_and_short_tail():
    request = Mock(return_value=response([(20, 90), (111, 160), (171, 190)], song_groups=[[0, 1, 2]]))
    intervals, audit = review_boundaries(BoundaryOptions(100, 280, 1000, 20, 0.85), request)
    assert intervals == [(100, 270)]
    assert len(audit["boundary_attempts"]) == 1


def test_touching_left_edge_expands_until_actual_start():
    request = Mock(side_effect=[response([(0, 100)]), response([(10, 120)])])
    intervals, audit = review_boundaries(BoundaryOptions(100, 200, 1000, 20, 0.85), request)
    assert request.call_args_list[0].args == (80, 220)
    assert request.call_args_list[1].args == (60, 240)
    assert intervals == [(70, 180)]
    assert len(audit["boundary_attempts"]) == 2


def test_media_edge_terminates_expansion():
    request = Mock(return_value=response([(0, 100)]))
    intervals, audit = review_boundaries(BoundaryOptions(10, 100, 1000, 20, 0.85), request)
    assert intervals == [(0, 100)]
    assert audit["media_start_reached"]
    assert request.call_count == 1


def test_different_songs_are_not_merged():
    request = Mock(return_value=response([(20, 90), (111, 160)], song_groups=[[0], [1]]))
    intervals, _ = review_boundaries(BoundaryOptions(100, 280, 1000, 20, 0.85), request)
    assert len(intervals) == 2


def test_missing_group_is_not_silent_split():
    with pytest.raises(ValueError, match="song_groups"):
        review_boundaries(
            BoundaryOptions(100, 280, 1000, 20, 0.85), Mock(return_value=response([(20, 90), (111, 160)]))
        )
