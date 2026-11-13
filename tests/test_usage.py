import json
from types import SimpleNamespace

import pytest
from event_capture import capture_events, child_sends
from workspace_support import make_jobs, start, wait_for, wait_for_job

from segment.music_agent.cli import build_parser
from segment.music_agent.gemini import GeminiClient
from segment.music_agent.runtime import PROGRESS_PREFIX
from segment.usage import EVENT_PREFIX, UsageTotals
from segment.workspace_records import usage_snapshot


def event(model="gemini-4-hydrogen", usage=None):
    return {"model": model, "usage": usage}


def test_cost_with_cached_tokens():
    totals = UsageTotals()
    totals.add(
        event(
            usage={
                "prompt_tokens": 1_000_000,
                "completion_tokens": 1_000_000,
                "prompt_tokens_details": {"cached_tokens": 500_000},
            }
        )
    )
    result = totals.snapshot()
    # 1M 输入含 0.5M 缓存 + 1M 输出：0.5*1.5 + 0.5*0.075 + 1*7.5 = 8.2875 美元
    assert result["estimated_cny"] == pytest.approx(8.2875)
    assert result["complete"]
    assert result["cached_tokens"] == 500_000
    assert UsageTotals().snapshot()["calls"] == 0


def test_missing_usage_and_unknown_model():
    totals = UsageTotals()
    totals.add(event())
    totals.add(event("custom", {"prompt_tokens": 3, "completion_tokens": 4}))
    result = totals.snapshot()
    assert not result["complete"]
    assert result["models"][0]["missing_usage"] == 1
    assert result["models"][1]["estimated_cny"] is None


@pytest.mark.parametrize(
    "usage",
    [
        {"prompt_tokens": -1, "completion_tokens": 2},
        {"prompt_tokens": None, "completion_tokens": 2},
        {"prompt_tokens": "10", "completion_tokens": 2},
        {"prompt_tokens": True, "completion_tokens": 2},
        {"prompt_tokens": 10, "completion_tokens": -1},
        {"prompt_tokens": 10, "completion_tokens": 1.5},
        {"prompt_tokens": 10, "completion_tokens": 2, "prompt_tokens_details": {"cached_tokens": -1}},
        {"prompt_tokens": 10, "completion_tokens": 2, "prompt_tokens_details": {"cached_tokens": 11}},
    ],
)
def test_invalid_token_counts_are_missing_usage_and_do_not_modify_input(usage, caplog):
    totals = UsageTotals()
    invalid = event(usage=usage)
    validated = totals.add(invalid)
    assert invalid["usage"] is usage
    assert validated["usage"] is None
    totals.add(event(usage={"prompt_tokens": 10, "completion_tokens": 2}))
    result = totals.snapshot()
    assert result["calls"] == 2
    assert result["input_tokens"] == 10 and result["output_tokens"] == 2
    assert result["models"][0]["missing_usage"] == 1
    assert not result["complete"]
    # 10 输入 + 2 输出 @ $1.5/$7.5 每百万：0.000015 + 0.000015 = 0.00003 美元
    assert result["estimated_cny"] == pytest.approx(0.00003)
    assert "已忽略" in caplog.text


def test_historical_invalid_tokens_do_not_block_usage_snapshot():
    result = usage_snapshot([event(usage={"prompt_tokens": -1, "completion_tokens": 2})])
    assert result["calls"] == 1 and result["models"][0]["missing_usage"] == 1
    assert not result["complete"]


def test_non_token_schema_errors_still_surface():
    with pytest.raises(KeyError, match="completion_tokens"):
        UsageTotals().add(event(usage={"prompt_tokens": 10}))


def test_invalid_usage_does_not_stop_subsequent_process_events(tmp_path, caplog):
    invalid = EVENT_PREFIX + json.dumps(event(usage={"prompt_tokens": -1, "completion_tokens": 2}))
    valid = EVENT_PREFIX + json.dumps(event(usage={"prompt_tokens": 10, "completion_tokens": 2}))
    progress = PROGRESS_PREFIX + json.dumps(
        {
            "id": "scan",
            "attempt": 1,
            "sequence": 1,
            "state": "succeeded",
            "label": "分块扫描",
        }
    )
    code = "; ".join(child_sends(line) for line in (invalid, valid, progress))
    jobs = make_jobs(tmp_path, code)
    try:
        identity = start(jobs)
        result = wait_for_job(jobs, identity)
        assert result["state"] == "succeeded" and result["error"] is None
        assert result["batch"][0]["steps"][0]["id"] == "scan"
        assert result["usage"]["input_tokens"] == 10
        assert result["usage"]["models"][0]["missing_usage"] == 1
        assert not result["usage"]["complete"]
        assert jobs.usage.snapshot() == result["usage"]
        saved = jobs.store.get("jobs", identity)
        assert saved["usage_events"][0]["usage"] is None
        assert saved["usage_events"][1]["usage"]["prompt_tokens"] == 10
        assert saved["attempts"][0]["usage"] == result["usage"]
        assert caplog.text.count("已忽略") == 1
    finally:
        jobs.close()


def test_gemini_usage_recorded_even_if_model_json_invalid(monkeypatch, tmp_path):
    capture = capture_events(monkeypatch, tmp_path)
    usage = SimpleNamespace(total_input_tokens=12, total_output_tokens=3, total_cached_tokens=0)
    interaction = SimpleNamespace(output_text="bad json", usage=usage)
    client = object.__new__(GeminiClient)
    client._client = SimpleNamespace(interactions=SimpleNamespace(create=lambda **kw: interaction))
    client.model = "gemini-4-hydrogen"
    with pytest.raises(ValueError):
        client.json_call(None, "test", {"type": "object"})
    lines = capture.lines()
    assert len(lines) == 1
    recorded = json.loads(lines[0].strip().removeprefix(EVENT_PREFIX))
    assert recorded["model"] == "gemini-4-hydrogen"
    assert recorded["usage"] == {"total_input_tokens": 12, "total_output_tokens": 3, "total_cached_tokens": 0}


def test_subprocess_usage_persisted_and_separate_from_logs(tmp_path):
    data = event(usage={"prompt_tokens": 100, "completion_tokens": 20})
    line = EVENT_PREFIX + json.dumps(data) + "\n"
    jobs = make_jobs(tmp_path, child_sends(line) + "; print('normal log')")
    try:
        job_id = start(jobs)
        wait_for_job(jobs, job_id)
        wait_for(lambda: jobs.status(job_id)["usage"]["input_tokens"] == 100, "用量事件未被收集")
        assert jobs.usage.snapshot()["calls"] == 1
        text = jobs.log_chunk(job_id, 0, 0)["text"]
        assert EVENT_PREFIX not in text
        assert "normal log" in text
    finally:
        jobs.close()


def test_cli_environment_defaults(monkeypatch):
    monkeypatch.setenv("MUSIC_AGENT_MINIMUM_CONFIDENCE", "0.93")
    monkeypatch.setenv("MUSIC_AGENT_SKIP_NETEASE", "true")
    args = build_parser().parse_args(["--media", "input.mp4", "--outdir", "output"])
    assert args.minimum_confidence == 0.93
    assert args.skip_netease is True
    args = build_parser().parse_args(["--media", "input.mp4", "--outdir", "output", "--minimum-confidence", "0.8"])
    assert args.minimum_confidence == 0.8
