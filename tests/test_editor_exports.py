from pathlib import Path
from threading import Event

import pytest

from segment.editor_exports import Exports
from segment.editor_projects import Projects
from segment.workspace_store import DocumentStore


@pytest.mark.parametrize("suffix, name", [("-小葵", "Song-小葵.mp4"), ("", "Song.mp4")])
def test_export_suffix_only_changes_snapshot_filename(tmp_path, suffix, name):
    store = DocumentStore(tmp_path / "workspace.sqlite3")
    project = {
        "id": "p",
        "upload_id": "u",
        "revision": 0,
        "clips": [{"id": "song", "start_seconds": 0, "end_seconds": 5, "name": "Song.mp4"}],
    }
    exports = Exports(
        store, tmp_path, {"source": lambda _: Path("source.mp4"), "export": lambda *args: args[-1].write_bytes(b"clip")}
    )
    try:
        task = exports.start(project, ["song"], filename_suffix=suffix)
    finally:
        exports.close()
    assert store.get("editor_exports", task["id"])["clips"][0]["name"] == name
    assert project["clips"][0]["name"] == "Song.mp4"


def test_export_rejects_path_characters_in_suffix(tmp_path):
    store = DocumentStore(tmp_path / "workspace.sqlite3")
    exports = Exports(store, tmp_path, {})
    try:
        with pytest.raises(ValueError, match="后缀"):
            exports.start({"clips": []}, ["song"], filename_suffix="/bad")
    finally:
        exports.close()


def test_export_uses_saved_revision_and_does_not_follow_later_edits(tmp_path):
    store = DocumentStore(tmp_path / "workspace.sqlite3")
    projects = Projects(store)
    project = projects.create({"upload_id": "source", "name": "Recording", "duration": 100})
    clip = {"id": "song", "start_seconds": 10, "end_seconds": 30, "title": "Song", "artist": "", "name": "Song.mp4"}
    project = projects.save(project["id"], {"revision": 0, "clips": [clip]})
    entered, release = Event(), Event()
    calls = []

    def export(source, start, end, destination):
        entered.set()
        assert release.wait(3)
        calls.append((start, end))
        destination.write_bytes(b"real test exporter")

    exports = Exports(store, tmp_path, {"source": lambda identity: Path("source.mp4"), "export": export})
    task = exports.start(project, ["song"])
    assert entered.wait(3)
    projects.save(project["id"], {"revision": 1, "clips": [{**clip, "end_seconds": 40}]})
    release.set()
    exports.close()
    result = store.get("editor_exports", task["id"])
    assert result["state"] == "succeeded"
    assert result["revision"] == 1
    assert calls == [(10, 30)]
    assert Path(result["clips"][0]["path"]).is_file()


def test_export_failure_never_reports_success(tmp_path):
    store = DocumentStore(tmp_path / "workspace.sqlite3")
    project = {
        "id": "p",
        "upload_id": "u",
        "revision": 0,
        "clips": [{"id": "song", "start_seconds": 0, "end_seconds": 5, "name": "Song.mp4"}],
    }

    def export(*args):
        raise RuntimeError("encoder failed")

    exports = Exports(store, tmp_path, {"source": lambda identity: Path("source.mp4"), "export": export})
    task = exports.start(project, ["song"])
    exports.close()
    result = store.get("editor_exports", task["id"])
    assert result["state"] == "failed"
    assert "encoder failed" in result["error"]
