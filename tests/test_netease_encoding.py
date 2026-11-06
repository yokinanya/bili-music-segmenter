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
