"""导出缓存只取决于源视频与时间范围，标题变化必须复用同一片段。"""

from segment.music_agent.pipeline import export_identity


def interval(**changes):
    return {
        "start_seconds": 100.0,
        "end_seconds": 200.0,
        "duration_seconds": 100.0,
        "title": "",
        "artist": "",
        "recognition": {"shazam": {"status": "no_match"}},
        "title_resolution": {"status": "unmatched"},
        **changes,
    }


def test_manual_title_does_not_change_the_export_identity():
    # 用户填好标题后重跑，必须命中同一片段，否则会生成新文件并丢掉手动编辑。
    assert export_identity(1, interval()) == export_identity(1, interval(title="青花", artist="周传雄"))


def test_manual_time_edit_changes_the_export_identity():
    assert export_identity(1, interval()) != export_identity(1, interval(end_seconds=210.0))
    assert export_identity(1, interval()) != export_identity(2, interval())


def test_renamed_interval_reuses_export_but_updates_the_file_name(tmp_path):
    """同一时间范围改了标题，应复用已导出的视频，但文件名要跟随新标题。"""
    from unittest.mock import Mock

    from segment.music_agent import pipeline

    exported = tmp_path / "clips" / pipeline.export_identity(1, interval()) / "未识别歌名.mp4"
    exported.parent.mkdir(parents=True)
    exported.write_bytes(b"video")
    from segment.music_agent.pipeline_context import PipelineContext

    context = PipelineContext(
        media=tmp_path / "in.mp4",
        output=tmp_path,
        options={},
        services=Mock(calls={"export": Mock(side_effect=AssertionError("不应重新导出"))}),
        runtime=Mock(run=lambda spec, work: work()),
        client=None,
    )

    import asyncio

    result = asyncio.run(pipeline._export(interval(title="青花"), 1, context))
    path = pipeline.export_folder(tmp_path, 1, interval(title="青花")) / "青花.mp4"
    assert path.is_file() and path.read_bytes() == b"video"
    assert not exported.exists()
    assert result == str(path)
