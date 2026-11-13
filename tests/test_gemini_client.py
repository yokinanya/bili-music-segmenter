from types import SimpleNamespace

import pytest

from segment.music_agent import gemini


@pytest.mark.parametrize("fail", [False, True])
def test_client_removes_only_its_temporary_audio_on_close(tmp_path, fail):
    parent = tmp_path / "state"
    parent.mkdir()
    retained = parent / "workspace.sqlite3"
    retained.write_bytes(b"retained")
    client = gemini.GeminiClient(gemini.GeminiConfig("test", None, None), workdir=parent)

    def extract(media, start, end, destination):
        destination.write_bytes(b"partial" if fail else b"audio")
        if fail:
            raise RuntimeError("extract failed")

    try:
        if fail:
            with pytest.raises(RuntimeError, match="extract failed"):
                client.audio_window(tmp_path / "source.mp4", 0, 10, extract)
        else:
            audio = client.audio_window(tmp_path / "source.mp4", 0, 10, extract)
            assert audio.read_bytes() == b"audio"
    finally:
        client.close()

    assert list(parent.iterdir()) == [retained]


def test_json_call_sends_inline_audio_and_reads_usage(tmp_path, monkeypatch):
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"RIFF0000")
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        usage = SimpleNamespace(total_input_tokens=9600, total_output_tokens=42, total_cached_tokens=0)
        return SimpleNamespace(output_text='{"segments": []}', usage=usage)

    client = object.__new__(gemini.GeminiClient)
    client._client = SimpleNamespace(interactions=SimpleNamespace(create=create))
    client.model = "gemini-4-hydrogen"
    result = client.json_call(wav, "prompt", {"type": "object"})

    assert result["data"] == {"segments": []}
    assert result["usage"]["total_input_tokens"] == 9600
    assert captured["response_format"]["mime_type"] == "application/json"
    assert captured["input"][0]["type"] == "audio"
    assert captured["input"][0]["mime_type"] == "audio/wav"
    assert captured["input"][0]["data"] == "UklGRjAwMDA="


def test_json_call_rejects_empty_output(tmp_path):
    client = object.__new__(gemini.GeminiClient)
    client._client = SimpleNamespace(
        interactions=SimpleNamespace(create=lambda **_: SimpleNamespace(output_text="", usage=None))
    )
    client.model = "gemini-4-hydrogen"
    wav = tmp_path / "a.wav"
    wav.write_bytes(b"x")
    with pytest.raises(ValueError, match="空响应"):
        client.json_call(wav, "p", {"type": "object"})


def test_oversized_audio_uses_files_api_and_cleans_up(tmp_path):
    big = tmp_path / "big.wav"
    with big.open("wb") as handle:
        handle.truncate(gemini.INLINE_LIMIT_BYTES + 1)
    deleted = []
    captured = {}
    file = SimpleNamespace(
        name="files/abc", uri="https://files/abc", mime_type="audio/wav", state=gemini.types.FileState.ACTIVE
    )
    files = SimpleNamespace(
        upload=lambda **_: file,
        get=lambda **_: file,
        delete=lambda **kwargs: deleted.append(kwargs["name"]),
    )

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_text='{"segments": []}', usage=None)

    client = object.__new__(gemini.GeminiClient)
    client._client = SimpleNamespace(interactions=SimpleNamespace(create=create), files=files)
    client.model = "gemini-4-hydrogen"
    client.json_call(big, "p", {"type": "object"})

    assert captured["input"][0] == {"type": "audio", "uri": "https://files/abc", "mime_type": "audio/wav"}
    assert deleted == ["files/abc"]
