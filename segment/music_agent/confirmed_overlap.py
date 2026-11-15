"""Merge overlapping performances only when reference identification agrees."""

from segment.music_agent.recognition import normalize_title


def merge_confirmed_overlaps(records: list[dict]) -> list[dict]:
    entries = sorted(
        (interval["start_seconds"], row, column, interval)
        for row, record in enumerate(records)
        for column, interval in enumerate(record.get("singing_intervals", []))
    )
    merged = []
    for _, row, column, interval in entries:
        if merged and _same_performance(merged[-1][2], interval):
            previous_row, previous_column, previous = merged[-1]
            end = max(previous["end_seconds"], interval["end_seconds"])
            evidence = previous.get("merged_intervals", [previous])
            merged[-1] = (
                previous_row,
                previous_column,
                {
                    **previous,
                    "end_seconds": end,
                    "duration_seconds": round(end - previous["start_seconds"], 3),
                    "merged_intervals": [*evidence, interval],
                },
            )
        else:
            merged.append((row, column, interval))
    retained = {(row, column): interval for row, column, interval in merged}
    return [
        {
            **record,
            "singing_intervals": [
                retained[row, column]
                for column, _ in enumerate(record.get("singing_intervals", []))
                if (row, column) in retained
            ],
        }
        for row, record in enumerate(records)
    ]


def _confirmed_title(interval: dict) -> str:
    if interval.get("title_resolution", {}).get("status") not in {"matched", "single_provider"}:
        return ""
    title = normalize_title(interval.get("title", ""))
    references = interval.get("recognition", {})
    matches = [
        normalize_title(value.get("title", ""))
        for value in references.values()
        if isinstance(value, dict) and value.get("status") == "matched"
    ]
    return title if title and title in matches else ""


def _same_performance(first: dict, second: dict) -> bool:
    title = _confirmed_title(first)
    return bool(title and title == _confirmed_title(second) and second["start_seconds"] < first["end_seconds"])
