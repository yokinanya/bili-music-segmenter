"""Node recognizer output is UTF-8 regardless of the Windows system locale."""

import subprocess
import sys

import pytest

from segment import netease


@pytest.mark.parametrize("operation", ["match", "fingerprint"])
def test_node_output_uses_explicit_utf8(monkeypatch, operation):
    run = subprocess.run
    output = '{"song": {"name": "中文歌曲", "artist": "演唱者"}}' if operation == "match" else "指纹结果"

    def node(command, **kwargs):
        assert kwargs.get("encoding") == "utf-8"
        program = f"import sys; sys.stdout.buffer.write({output.encode('utf-8')!r})"
        return run([sys.executable, "-c", program], **kwargs)

    monkeypatch.setattr(netease.subprocess, "run", node)
    if operation == "match":
        result = netease._post_audio_match("fingerprint", duration=3, cookie="", timeout=5)
        assert result == {"name": "中文歌曲", "artist": "演唱者"}
    else:
        assert netease._run_afp_generator("audio.f32le") == "指纹结果"


@pytest.mark.parametrize("operation", ["match", "fingerprint"])
def test_node_failure_surfaces_stderr(monkeypatch, operation):
    """Node 子进程失败时必须带上它自己的错误信息，否则界面只能看到命令行和退出码。"""

    def node(command, **kwargs):
        raise subprocess.CalledProcessError(1, command, output="", stderr="NetEase audio match HTTP 403\n")

    monkeypatch.setattr(netease.subprocess, "run", node)
    with pytest.raises(RuntimeError) as failure:
        if operation == "match":
            netease._post_audio_match("fingerprint", duration=3, cookie="", timeout=5)
        else:
            netease._run_afp_generator("audio.f32le")
    message = str(failure.value)
    assert "NetEase audio match HTTP 403" in message
    assert "CalledProcessError" not in message


def test_fractional_timeout_is_passed_as_integer(monkeypatch):
    """整体时限裁剪会产生小数秒；Node 的 AbortSignal.timeout 只接受整数。

    实测报错：The value of "delay" is out of range. It must be an integer. Received 59999.99904807191
    """
    captured = {}

    def node(command, **kwargs):
        captured["payload"] = __import__("json").loads(kwargs["input"])
        return subprocess.CompletedProcess(command, 0, stdout='{"data": {"result": []}}', stderr="")

    monkeypatch.setattr(netease.subprocess, "run", node)
    with pytest.raises(Exception):
        netease._post_audio_match("fingerprint", duration=3, cookie="", timeout=59.99904807191)
    assert isinstance(captured["payload"]["timeout"], int)
    assert captured["payload"]["timeout"] == 60


def test_tiny_fractional_timeout_never_becomes_zero(monkeypatch):
    """裁剪到接近 0 时也要给 JS 一个合法正整数，不能是 0 或负数。"""
    captured = {}

    def node(command, **kwargs):
        captured["payload"] = __import__("json").loads(kwargs["input"])
        return subprocess.CompletedProcess(command, 0, stdout='{"data": {"result": []}}', stderr="")

    monkeypatch.setattr(netease.subprocess, "run", node)
    with pytest.raises(Exception):
        netease._post_audio_match("fingerprint", duration=3, cookie="", timeout=0.02)
    assert captured["payload"]["timeout"] == 1
