import logging

import pytest

from segment.webui import Handler


@pytest.mark.parametrize("error_type", [BrokenPipeError, ConnectionResetError, ConnectionAbortedError])
def test_disconnected_media_request_does_not_write_an_error_response(monkeypatch, caplog, error_type):
    handler = object.__new__(Handler)
    handler.path = "/preview.mp4"
    responses = []

    def disconnected(*args):
        raise error_type("browser closed media connection")

    monkeypatch.setattr(handler, "_authorized", lambda: True)
    monkeypatch.setattr(handler, "_static", disconnected)
    monkeypatch.setattr(handler, "_json", lambda status, body: responses.append((status, body)))
    with caplog.at_level(logging.INFO, logger="segment.webui"):
        handler._dispatch("GET")

    assert responses == []
    assert not any("浏览器已断开连接" in record.message for record in caplog.records)
    assert not any(record.levelno >= logging.ERROR for record in caplog.records)


def test_media_io_failure_still_returns_a_server_error(monkeypatch, caplog):
    handler = object.__new__(Handler)
    handler.path = "/preview.mp4"
    responses = []

    def failed(*args):
        raise OSError("media read failed")

    monkeypatch.setattr(handler, "_authorized", lambda: True)
    monkeypatch.setattr(handler, "_static", failed)
    monkeypatch.setattr(handler, "_json", lambda status, body: responses.append((status, body)))
    handler._dispatch("GET")

    assert responses == [(500, {"error": "media read failed"})]
    assert "请求执行失败" in caplog.text
