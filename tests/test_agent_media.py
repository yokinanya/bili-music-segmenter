import subprocess

from segment.music_agent.export import export_video, safe_component
from segment.music_agent.media import extract_wav, media_duration


def test_ffmpeg_export_and_audio_extraction(tmp_path):
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:s=160x90:r=10:d=3",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:duration=3",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            "-shortest",
            str(source),
        ],
        check=True,
        capture_output=True,
    )
    clip = tmp_path / "clip.mp4"
    export_video(source, 0.5, 2.0, clip)
    assert abs(media_duration(clip) - 1.5) < 0.2
    wav = tmp_path / "clip.wav"
    extract_wav(source, 0.5, 2.0, wav)
    assert abs(media_duration(wav) - 1.5) < 0.05


def test_filename_component_sanitizes_reserved_characters():
    assert safe_component("直播/回放:?", "media") == "直播 回放"
    assert safe_component("/", "fallback") == "fallback"
