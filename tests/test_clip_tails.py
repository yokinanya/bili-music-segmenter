import copy
import subprocess

import pytest

from segment.music_agent.clip_tails import extend_clip_tails
from segment.music_agent.export import export_video
from segment.music_agent.media import media_duration


def record(index, *ranges):
    return {
        "index": index,
        "singing_intervals": [
            {"start_seconds": start, "end_seconds": end, "title": f"歌曲{index}"} for start, end in ranges
        ],
    }


def test_tail_extends_two_seconds_and_keeps_original_evidence():
    source = [record(1, (10, 40))]
    before = copy.deepcopy(source)
    result = extend_clip_tails(source, 100)
    interval = result[0]["singing_intervals"][0]
    assert interval["start_seconds"] == 10
    assert interval["end_seconds"] == 42
    assert interval["duration_seconds"] == 32
    assert interval["title"] == "歌曲1"
    assert interval["tail_extension"] == {
        "original_end_seconds": 40,
        "requested_seconds": 2,
        "applied_seconds": 2,
    }
    assert source == before


@pytest.mark.parametrize("end,expected", [(98.75, 100), (100, 100)])
def test_tail_stops_at_media_end(end, expected):
    result = extend_clip_tails([record(1, (80, end))], 100)
    interval = result[0]["singing_intervals"][0]
    assert interval["end_seconds"] == expected
    assert interval["tail_extension"]["applied_seconds"] == expected - end


@pytest.mark.parametrize("next_start,expected", [(40, 40), (40.75, 40.75), (42, 42), (45, 42)])
def test_tail_stops_at_next_song_across_unsorted_candidates(next_start, expected):
    result = extend_clip_tails([record(2, (next_start, 70)), record(1, (10, 40))], 100)
    assert [item["index"] for item in result] == [2, 1]
    assert result[0]["singing_intervals"][0]["start_seconds"] == next_start
    assert result[1]["singing_intervals"][0]["end_seconds"] == expected


def test_multiple_intervals_in_one_candidate_and_empty_records():
    result = extend_clip_tails([record(1), record(2, (10, 20), (21, 30))], 100)
    assert result[0]["singing_intervals"] == []
    assert [item["end_seconds"] for item in result[1]["singing_intervals"]] == [21, 32]
    assert extend_clip_tails([], 100) == []


@pytest.mark.parametrize(
    "ranges",
    [((10, 30), (29, 40)), ((10, 101),), ((-1, 10),), ((10, 10),), ((10, float("nan")),)],
)
def test_invalid_or_overlapping_confirmed_ranges_are_explicit_errors(ranges):
    with pytest.raises(ValueError, match="边界无效或仍有重叠"):
        extend_clip_tails([record(1, *ranges)], 100)


@pytest.mark.parametrize("duration", [0, -1, float("inf"), float("nan")])
def test_invalid_media_duration_is_an_explicit_error(duration):
    with pytest.raises(ValueError, match="源视频时长"):
        extend_clip_tails([], duration)


def test_real_export_includes_extended_tail_and_media_endpoint(tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=size=64x64:rate=25:duration=5",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=5",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(source),
        ],
        check=True,
        capture_output=True,
        timeout=10,
    )
    extended = extend_clip_tails([record(1, (1, 2)), record(2, (4.5, 4.75))], 5)
    for entry in extended:
        interval = entry["singing_intervals"][0]
        destination = tmp_path / f"{entry['index']}.mp4"
        export_video(source, interval["start_seconds"], interval["end_seconds"], destination)
        assert media_duration(destination) == pytest.approx(interval["duration_seconds"], abs=0.05)
    assert extended[0]["singing_intervals"][0]["end_seconds"] == 4
    assert extended[1]["singing_intervals"][0]["end_seconds"] == 5
