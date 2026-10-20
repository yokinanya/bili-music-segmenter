import json
import sys
from types import SimpleNamespace

import pytest
from test_webui import wait_for_job

from segment.music_agent.cli import build_parser
from segment.music_agent.models import text_model_call
from segment.usage import EVENT_PREFIX, UsageTotals
from segment.webui_jobs import Jobs


def event(model="qwen3.8-flash", usage=None):
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
    assert result["estimated_cny"] == pytest.approx(3.15)
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


def test_usage_recorded_even_if_model_json_invalid(monkeypatch, capsys):
    monkeypatch.setenv("MUSIC_AGENT_JSON_RETRIES", "0")
    monkeypatch.setenv("MUSIC_AGENT_USAGE_EVENTS", "1")
    usage = {"prompt_tokens": 12, "completion_tokens": 3}
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="bad json"))],
        usage=SimpleNamespace(model_dump=lambda: usage),
    )
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: response)))
    with pytest.raises(ValueError):
        text_model_call(client, "qwen3.8-flash", "test")
    line = capsys.readouterr().out.strip()
    assert json.loads(line.removeprefix(EVENT_PREFIX))["usage"] == usage


def test_subprocess_usage_only_in_memory(tmp_path):
    data = event(usage={"prompt_tokens": 100, "completion_tokens": 20})
    code = f"print({(EVENT_PREFIX + json.dumps(data))!r}); print('normal log')"
    jobs = Jobs(lambda _: [sys.executable, "-c", code])
    try:
        job_id = jobs.start({"outdir": str(tmp_path)})
        result = wait_for_job(jobs, job_id)
        assert result["usage"]["input_tokens"] == 100
        assert jobs.usage.snapshot()["calls"] == 1
        assert EVENT_PREFIX not in result["log"]
        assert "normal log" in result["log"]
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
