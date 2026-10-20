import subprocess

from segment.music_agent.export import export_video, make_clip_path
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


def test_chinese_filename_keeps_title_and_stays_below_filesystem_limit(tmp_path):
    path = make_clip_path(tmp_path, "很长的直播名字" * 30, 1, 10, 60, "歌曲标题" * 20, "歌手")
    assert len(path.name.encode("utf-8")) <= 255
    assert "歌曲标题" in path.name
