import pytest


@pytest.fixture(autouse=True)
def isolated_log_dir(tmp_path_factory, monkeypatch):
    """Logs live in one shared directory; every test gets its own so runs never touch the real one."""
    root = tmp_path_factory.mktemp("project")
    monkeypatch.setattr("segment.logs.log_root", root)
    return root
