from pathlib import Path
from unittest.mock import Mock

import pytest

from segment.music_agent.final_review import ReviewContext, audit_results


def context():
    return ReviewContext(Path("input.mp4"), None, None, "summary", "audio", "test", 20, 0.85, 30)


def record():
    return {
        "index": 1,
        "start": 100,
        "end": 200,
        "classification": "host_singing",
        "confidence": 0.9,
        "host_singing_present": True,
        "title_hint": "",
        "rationale": "singing",
        "singing_intervals": [{"start_seconds": 110, "end_seconds": 180}],
    }


def test_summary_cannot_change_times_without_audio_review():
    original = record()
    text = Mock(
        return_value={
            "data": {
                "summary": "check intro",
                "rechecks": [
                    {"candidate_index": 1, "context_seconds": 60, "reason": "intro missing"},
                ],
            },
            "usage": None,
        }
    )
    refine = Mock(return_value=([(90, 205)], {"data": {"rationale": "audio evidence"}, "usage": None}))
    results, summary = audit_results([original], context(), text_call=text, refine=refine)
    assert refine.call_args.kwargs["context_seconds"] == 60
    assert results[0]["singing_intervals"][0]["start_seconds"] == 90
    assert original["singing_intervals"][0]["start_seconds"] == 110
    assert "final_audio_review" in results[0]
    # The summary belongs to the run, not to every record.
    assert summary["data"]["summary"] == "check intro"
    assert "final_summary" not in results[0]


@pytest.mark.parametrize(
    "requests",
    [
        [{"candidate_index": 99, "context_seconds": 60, "reason": "unknown"}],
        [{"candidate_index": 1, "context_seconds": 0, "reason": "bad"}],
    ],
)
def test_invalid_summary_is_explicit_failure(requests):
    text = Mock(return_value={"data": {"summary": "test", "rechecks": requests}})
    refine = Mock()
    with pytest.raises(ValueError):
        audit_results([record()], context(), text_call=text, refine=refine)
    refine.assert_not_called()


def test_failed_recheck_keeps_prepared_boundaries():
    text = Mock(
        return_value={
            "data": {
                "summary": "recheck",
                "rechecks": [{"candidate_index": 1, "context_seconds": 60, "reason": "intro missing"}],
            },
            "usage": None,
        }
    )
    refine = Mock(side_effect=ValueError("边界复核在 8 次扩张后仍未找到歌曲边界"))
    results, _ = audit_results([record()], context(), text_call=text, refine=refine)
    assert results[0]["singing_intervals"] == [{"start_seconds": 110, "end_seconds": 180}]
    assert "仍未找到歌曲边界" in results[0]["final_audio_review"]["error"]


def test_audio_failure_is_not_swallowed():
    text = Mock(
        return_value={
            "data": {
                "summary": "test",
                "rechecks": [
                    {"candidate_index": 1, "context_seconds": 60, "reason": "intro"},
                ],
            }
        }
    )
    with pytest.raises(RuntimeError, match="audio failed"):
        audit_results([record()], context(), text_call=text, refine=Mock(side_effect=RuntimeError("audio failed")))
