from pathlib import Path

from segment import netease


def test_pcm_path_is_not_open_and_directory_is_cleaned(monkeypatch):
    paths = []

    def extract(file, pcm_path, offset):
        path = Path(pcm_path)
        assert not path.exists()
        path.write_bytes(b"pcm")
        paths.append(path)

    monkeypatch.setattr(netease, "_extract_pcm", extract)
    monkeypatch.setattr(netease, "_run_afp_generator", lambda path: Path(path).read_bytes().hex())
    assert netease.generate_audio_fp("audio.wav", 6) == b"pcm".hex()
    assert not paths[0].parent.exists()
