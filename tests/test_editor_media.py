import subprocess

import pytest

from segment.editor_media import waveform


def test_waveform_uses_real_audio_peaks_and_caches_by_digest(tmp_path):
    source = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(source)], check=True
    )
    result = waveform(source, tmp_path / "cache", "digest")
    assert result["seconds_per_peak"] > 0
    assert len(result["peaks"]) > 0
    assert max(result["peaks"]) > 0
    assert all(0 <= value <= 1 for value in result["peaks"])
    source.unlink()
    assert waveform(source, tmp_path / "cache", "digest") == result


def test_waveform_exposes_invalid_media(tmp_path):
    source = tmp_path / "bad.mp4"
    source.write_bytes(b"not a video")
    with pytest.raises(RuntimeError, match="waveform"):
        waveform(source, tmp_path / "cache", "digest")
