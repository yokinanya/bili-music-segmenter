from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from event_capture import capture_events

from segment.music_agent import models
from segment.music_agent.json_response import parse_json
from segment.usage import EVENT_PREFIX


@pytest.fixture(autouse=True)
def retry_settings(monkeypatch):
    monkeypatch.setenv("MUSIC_AGENT_JSON_RETRIES", "3")


@pytest.fixture
def capture(monkeypatch, tmp_path):
    return capture_events(monkeypatch, tmp_path)


def response(content):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason="stop")],
        usage=SimpleNamespace(model_dump=lambda: {"prompt_tokens": 10, "completion_tokens": 5}),
    )


def client_for(create):
    return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))


@pytest.mark.parametrize("mode", ["audio", "text"])
def test_retry_only_current_request_and_count_all_usage(mode, capture, caplog):
    create = Mock(side_effect=[response('{"bad": 1 "missing": 2}'), response('{"ok": true}')])
    client = client_for(create)
    if mode == "audio":
        result = models.audio_model_call(client, "test", "prompt", "https://example.com/audio.wav")
    else:
        result = models.text_model_call(client, "test", "prompt")
    assert result["data"] == {"ok": True}
    assert create.call_count == 2
    assert create.call_args_list[0] == create.call_args_list[1]
    assert sum(line.startswith(EVENT_PREFIX) for line in capture.lines()) == 2
    assert "finish_reason=stop" in caplog.text
    assert "missing" in caplog.text


def test_retries_exhausted_preserve_cause(capture):
    create = Mock(return_value=response("not json"))
    with pytest.raises(ValueError, match="4") as error:
        models.text_model_call(client_for(create), "test", "prompt")
    assert isinstance(error.value.__cause__, ValueError)
    assert create.call_count == 4
    assert sum(line.startswith(EVENT_PREFIX) for line in capture.lines()) == 4


def test_disable_retry(monkeypatch):
    monkeypatch.setenv("MUSIC_AGENT_JSON_RETRIES", "0")
    create = Mock(return_value=response("not json"))
    with pytest.raises(ValueError):
        models.text_model_call(client_for(create), "test", "prompt")
    assert create.call_count == 1


def test_transport_error_not_retried_here():
    create = Mock(side_effect=RuntimeError("network"))
    with pytest.raises(RuntimeError, match="network"):
        models.text_model_call(client_for(create), "test", "prompt")
    assert create.call_count == 1


@pytest.mark.parametrize("content", ["```json", "```json\n{}", "[]", ""])
def test_invalid_json_has_explicit_error(content):
    with pytest.raises(ValueError):
        parse_json(content)
