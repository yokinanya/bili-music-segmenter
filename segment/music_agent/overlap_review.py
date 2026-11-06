"""Resolve shared performances globally before any candidate is exported."""

from __future__ import annotations

import json

from segment.music_agent.detection import Candidate


def reconcile_overlaps(records: list[dict], context) -> list[dict]:
    entries = [
        {"candidate": record["index"], "interval": interval}
        for record in records
        for interval in record.get("singing_intervals", [])
    ]
    groups = overlap_groups(entries)
    replacements = []
    for group in groups:
        unique = {(item["interval"]["start_seconds"], item["interval"]["end_seconds"]) for item in group}
        if len(group) == 1:
            continue
        owner = min(item["candidate"] for item in group)
        if len(unique) == 1:
            intervals = [dict(min(group, key=lambda item: item["candidate"])["interval"])]
            audit = {"kind": "identical_time_range", "members": group}
        else:
            intervals, response = _joint_review(group, context)
            audit = {"kind": "joint_audio_review", "members": group, "response": response}
        replacements.append({"owner": owner, "intervals": intervals, "audit": audit, "members": group})
    return _apply(records, entries, replacements)


def overlap_groups(entries: list[dict]) -> list[list[dict]]:
    ordered = sorted(entries, key=lambda item: (item["interval"]["start_seconds"], item["candidate"]))
    groups = []
    end = float("-inf")
    for item in ordered:
        interval = item["interval"]
        if not groups or interval["start_seconds"] >= end:
            groups.append([item])
            end = interval["end_seconds"]
        else:
            groups[-1].append(item)
            end = max(end, interval["end_seconds"])
    return groups


def _joint_review(group: list[dict], context) -> tuple[list[dict], dict]:
    start = min(item["interval"]["start_seconds"] for item in group)
    end = max(item["interval"]["end_seconds"] for item in group)
    candidate = Candidate(
        min(item["candidate"] for item in group), start, end, "host_singing", 1.0, True, "", "跨候选重叠"
    )
    instruction = (
        "这些候选时间重叠，可能指向同一次演唱。请联合听取目标范围，按实际表演去重："
        "同一次完整演唱只返回一个区间，不因标题或伴奏版本不同重复返回。不同歌曲必须返回各自不重叠区间。"
        "不得只选择最长候选，必须用声学证据确定完整边界；无法确认时明确返回无可确认演唱。"
        "候选参考数据（原视频绝对秒数，仅供定位，回答仍使用输入音频相对秒数）：" + json.dumps(group, ensure_ascii=False)
    )
    review = context.services.review_context(context)
    intervals, response = context.services.calls["refine"](
        context.media,
        candidate,
        context.client,
        context.storage,
        context_seconds=review.context_seconds,
        s3_prefix=review.prefix,
        model=review.audio_model,
        minimum_confidence=review.minimum_confidence,
        review_instruction=instruction,
    )
    if not intervals:
        raise ValueError(f"重叠候选联合复核未确认演唱：{start}–{end}，不自动选择或丢弃片段")
    _validate_intervals(intervals, context.runtime.config["duration"])
    return [{"start_seconds": a, "end_seconds": b, "duration_seconds": round(b - a, 3)} for a, b in intervals], response


def _validate_intervals(intervals: list, duration: float) -> None:
    import math

    previous = 0.0
    for start, end in intervals:
        if not all(math.isfinite(value) for value in (start, end)) or not 0 <= start < end <= duration:
            raise ValueError("联合复核返回无效边界")
        if start < previous:
            raise ValueError("联合复核仍存在重叠区间")
        previous = end


def _apply(records: list[dict], entries: list[dict], replacements: list[dict]) -> list[dict]:
    removed = {id(member) for replacement in replacements for member in replacement["members"]}
    result = []
    for record in records:
        owned = [replacement for replacement in replacements if replacement["owner"] == record["index"]]
        related = [
            replacement
            for replacement in replacements
            if any(item["candidate"] == record["index"] for item in replacement["members"])
        ]
        intervals = [
            item["interval"] for item in entries if item["candidate"] == record["index"] and id(item) not in removed
        ]
        intervals += [interval for replacement in owned for interval in replacement["intervals"]]
        result.append(
            {
                **record,
                "singing_intervals": sorted(intervals, key=lambda item: item["start_seconds"]),
                **(
                    {
                        "overlap_review": [item["audit"] for item in related],
                        "superseded_singing_intervals": record.get("singing_intervals", []),
                        "decision": "deduplicated" if not intervals else "overlap_reviewed",
                    }
                    if related
                    else {}
                ),
            }
        )
    final = [
        {"candidate": record["index"], "interval": interval}
        for record in result
        for interval in record["singing_intervals"]
    ]
    if any(len(group) > 1 for group in overlap_groups(final)):
        raise ValueError("联合复核结果仍与其他演唱片段重叠，停止导出并保留复核记录")
    return result
