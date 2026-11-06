from segment.music_agent.export_inventory import initialize_inventory, remove_superseded_exports


def test_legacy_retained_but_new_superseded_exports_removed(tmp_path):
    clips = tmp_path / "clips"
    clips.mkdir()
    legacy = clips / "legacy.mp4"
    legacy.write_bytes(b"original batch")
    initialize_inventory(tmp_path)
    obsolete = clips / "obsolete.mp4"
    obsolete.write_bytes(b"new duplicate")
    current = clips / "current.mp4"
    current.write_bytes(b"new final")
    initialize_inventory(tmp_path)
    records = [{"singing_intervals": [{"file": str(current)}]}]
    remove_superseded_exports(tmp_path, records)
    assert legacy.exists()
    assert current.exists()
    assert not obsolete.exists()


def test_new_workspace_keeps_only_manifest_referenced_files(tmp_path):
    initialize_inventory(tmp_path)
    clips = tmp_path / "clips"
    clips.mkdir()
    stale = clips / "segment.part.mp4"
    stale.write_bytes(b"interrupted export")
    remove_superseded_exports(tmp_path, [])
    assert not list(clips.rglob("*.mp4"))
