import pytest

from segment.editor_projects import Projects
from segment.workspace_store import DocumentStore


def test_project_saves_drafts_without_encoding_and_rejects_stale_revision(tmp_path):
    store = DocumentStore(tmp_path / "workspace.sqlite3")
    projects = Projects(store)
    project = projects.create({"upload_id": "source", "name": "Recording", "duration": 120})
    clip = {
        "id": "song",
        "start_seconds": 10,
        "end_seconds": 80,
        "title": "Song",
        "artist": "Singer",
        "name": "Song.mp4",
    }
    saved = projects.save(project["id"], {"revision": 0, "clips": [clip]})
    assert saved["revision"] == 1
    assert store.get("projects", project["id"])["clips"] == [clip]
    with pytest.raises(ValueError, match="revision"):
        projects.save(project["id"], {"revision": 0, "clips": []})
    assert projects.get(project["id"])["clips"] == [clip]


@pytest.mark.parametrize(
    "changes",
    [
        {"end_seconds": 121},
        {"start_seconds": float("nan")},
        {"start_seconds": 81},
        {"name": "../escape.mp4"},
    ],
)
def test_project_rejects_invalid_bounds_and_filenames(tmp_path, changes):
    projects = Projects(DocumentStore(tmp_path / "workspace.sqlite3"))
    project = projects.create({"upload_id": "source", "name": "Recording", "duration": 120})
    clip = {
        "id": "song",
        "start_seconds": 10,
        "end_seconds": 80,
        "title": "",
        "artist": "",
        "name": "Song.mp4",
        **changes,
    }
    with pytest.raises(ValueError):
        projects.save(project["id"], {"revision": 0, "clips": [clip]})


def test_project_reference_prevents_source_removal(tmp_path):
    import io

    from segment.workspace_uploads import Uploads

    store = DocumentStore(tmp_path / "workspace.sqlite3")
    uploads = Uploads(tmp_path / "uploads", store)
    source = uploads.register({"name": "source.mp4", "size_bytes": 3})
    uploads.receive(source["id"], io.BytesIO(b"123"), 3)
    Projects(store).create({"upload_id": source["id"], "name": "source", "duration": 120})
    with pytest.raises(ValueError, match="project"):
        uploads.remove(source["id"])
