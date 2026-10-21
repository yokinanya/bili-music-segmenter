from segment.music_agent.detection import Candidate, merge_candidates, parse_candidates
from segment.music_agent.export import make_clip_path, safe_component
from segment.music_agent.recognition import deterministic_title_choice, normalize_title


def test_scan_candidates_parse_and_reject_invalid_time():
    data = {
        "segments": [
            {
                "start_seconds": 10,
                "end_seconds": 60,
                "classification": "host_singing",
                "confidence": 0.9,
                "host_singing_present": True,
                "title_hint": "稻香",
                "rationale": "可听到主播现场演唱",
            }
        ]
    }
    candidate = parse_candidates(data, absolute_offset=100)[0]
    assert (candidate.start, candidate.end, candidate.title_hint) == (110, 160, "稻香")


def test_adjacent_songs_and_background_are_not_merged():
    candidates = [
        Candidate(0, 10, 30, "host_singing", 0.95, True, "歌A", "演唱"),
        Candidate(0, 30, 50, "host_singing", 0.9, True, "歌B", "另一首歌"),
        Candidate(0, 35, 60, "background_music_chat", 0.9, False, "", "聊天"),
    ]
    assert len(merge_candidates(candidates, max_gap=10)) == 3


def test_title_normalization_handles_spaces_and_fullwidth_characters():
    assert normalize_title("Play with Fire (Live)") == normalize_title("PlayWithFire")
    assert normalize_title("稻香（现场版）") == normalize_title("稻香")


def test_recognizer_consensus_uses_one_title_and_detects_true_conflict():
    references = {
        "shazam": {"status": "matched", "title": "痴心絕對", "artist": "Sam Lee"},
        "netease": {"status": "matched", "title": "痴心绝对", "artist": "李圣杰"},
    }
    title, _, status = deterministic_title_choice(references)
    assert status == "matched"
    assert title == "痴心绝对"

    references["netease"]["title"] = "完全不同的歌"
    assert deterministic_title_choice(references)[2] == "conflict"


def test_clip_filename_sanitizes_names_and_avoids_existing_paths(tmp_path):
    first = make_clip_path(tmp_path, "直播/回放", 1, 12.0, 42.0, "歌:名", "艺人/组合")
    first.touch()
    second = make_clip_path(tmp_path, "直播/回放", 1, 12.0, 42.0, "歌:名", "艺人/组合")
    assert first.name != second.name
    assert "/" not in second.name
    assert ":" not in second.name
    unknown = make_clip_path(tmp_path, "stream", 1, 1, 31, "", "")
    assert "unrecognized" not in unknown.name
    assert safe_component("/", "fallback") == "fallback"
