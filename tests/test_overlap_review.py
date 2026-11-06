import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from segment.music_agent.overlap_review import reconcile_overlaps
from segment.music_agent.pipeline import _finalize


def record(index, start, end, title="同一首歌"):
    return {
        "index": index,
        "decision": "prepared",
        "singing_intervals": [{"start_seconds": start, "end_seconds": end, "title": title, "recognition": {}}],
    }


def context(tmp_path, result):
    refine = Mock(return_value=(result, {"data": {"rationale": "联合回听确认"}}))
    exports = []

    def export(media, start, end, destination):
        exports.append((start, end))
        destination.write_bytes(b"video")

    class Runtime:
        config = {"duration": 3000}

        def run(self, spec, work):
            return work()

        def advance(self, *args):
            pass

    review = SimpleNamespace(context_seconds=20, prefix="test", audio_model="test", minimum_confidence=0.85)
    services = SimpleNamespace(calls={"refine": refine, "export": export}, review_context=lambda _: review)
    current = SimpleNamespace(
        media=Path("source.mp4"),
        output=tmp_path,
        client=None,
        storage=None,
        services=services,
        runtime=Runtime(),
        options={"candidate_concurrency": 2},
    )
    current.spec = lambda identity, label, payload: {"id": identity, "input": payload}
    return current, refine, exports


def test_exact_duplicate_exports_one_physical_file(tmp_path):
    current, refine, exports = context(tmp_path, [])
    records = [record(1, 507, 727), record(2, 507, 727)]

    async def execute():
        return [value async for value in _finalize(records, [], current)][-1]

    result = asyncio.run(execute())
    assert len(list(tmp_path.rglob("*.mp4"))) == 1
    assert exports == [(507, 727)]
    assert sum(len(item["singing_intervals"]) for item in result) == 1
    refine.assert_not_called()


def test_contained_candidates_joint_review_before_export(tmp_path, monkeypatch):
    current, refine, exports = context(tmp_path, [(2211, 2416)])
    records = [record(7, 2211, 2416), record(8, 2225, 2414.5, "伴奏版本")]
    from segment.music_agent import pipeline

    async def identify(interval, context):
        return {"recognition": {}, "title": "确认歌曲"}

    monkeypatch.setattr(pipeline, "recognize_interval", identify)

    async def execute():
        return [value async for value in _finalize(records, [], current)][-1]

    result = asyncio.run(execute())
    assert refine.call_count == 1
    assert exports == [(2211, 2416)]
    assert len(list(tmp_path.rglob("*.mp4"))) == 1
    assert result[1]["decision"] == "deduplicated"


def test_same_title_separate_performances_not_deduplicated(tmp_path):
    current, refine, _ = context(tmp_path, [])
    records = [record(1, 10, 100), record(2, 110, 200)]
    assert reconcile_overlaps(records, current) == records
    refine.assert_not_called()


def test_unresolved_overlap_produces_no_files(tmp_path):
    current, _, exports = context(tmp_path, [])
    with pytest.raises(ValueError, match="未确认演唱"):
        reconcile_overlaps([record(1, 10, 100), record(2, 20, 90)], current)
    assert exports == []
    assert not list(tmp_path.rglob("*.mp4"))
