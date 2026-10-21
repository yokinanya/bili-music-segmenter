import logging
from datetime import date, datetime
from pathlib import Path

import pytest

from segment import logs


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "log_root", tmp_path)
    monkeypatch.setattr(logs, "CONTAINER_LOG_DIR", tmp_path / "missing-container-dir")
    return tmp_path


def test_all_logs_share_one_directory(project):
    assert logs.log_dir() == project / "logs"
    paths = [
        logs.job_log_path("abc123"),
        logs.agent_log_path(Path("直播 回放.mp4")),
        logs.server_log_path(),
        logs.inaseg_log_path(),
    ]
    for path in paths:
        assert path.parent == project / "logs"
        assert path.parent.is_dir()


def test_filenames_rotate_by_date(project):
    day = date(2026, 10, 21)
    assert logs.job_log_path("abc123", today=day).name == "webui-20261021-abc123.log"
    assert logs.server_log_path(today=day).name == "webui-server-20261021.log"
    assert logs.inaseg_log_path(today=day).name == "inaseg-20261021.log"
    agent = logs.agent_log_path(Path("直播 回放.mp4"), started=datetime(2026, 10, 21, 23, 59, 59))
    assert agent.name == "music-agent-20261021-直播_回放.log"
    # A different day yields a different file instead of appending to the old one.
    other = day.replace(day=22)
    assert logs.server_log_path(today=other) != logs.server_log_path(today=day)


def test_concurrent_jobs_on_one_day_do_not_share_a_file(project):
    day = date(2026, 10, 21)
    first = logs.job_log_path("aaa", today=day)
    second = logs.job_log_path("bbb", today=day)
    assert first != second
    assert first.parent == second.parent


def test_unsafe_media_name_is_sanitized(project):
    name = logs.agent_log_path(Path("a/b:c*?.mkv"), started=datetime(2026, 10, 21)).name
    assert name.startswith("music-agent-20261021-")
    assert all(char not in name for char in ':*/?"<>|')


def test_container_directory_wins_when_present(tmp_path, monkeypatch):
    monkeypatch.setattr(logs, "CONTAINER_LOG_DIR", tmp_path / "mounted")
    (tmp_path / "mounted").mkdir()
    assert logs.log_dir() == tmp_path / "mounted"


def test_configure_logging_writes_file_and_console(project, capsys):
    target = logs.server_log_path()
    logs.configure_logging(logging.INFO, log_file=target)
    try:
        logging.getLogger("segment.test").info("落盘日志")
        for handler in logging.getLogger().handlers:
            handler.flush()
        assert "落盘日志" in target.read_text(encoding="utf-8")
        assert "落盘日志" in capsys.readouterr().err
    finally:
        for handler in logging.getLogger().handlers:
            handler.close()
        logging.getLogger().handlers.clear()
