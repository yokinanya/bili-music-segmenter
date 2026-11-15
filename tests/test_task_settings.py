import pytest

from segment.webui import create_jobs


def test_task_defaults_persist_and_invalid_changes_leave_settings_unchanged(tmp_path):
    jobs = create_jobs(tmp_path)
    original = dict(jobs.defaults)
    try:
        jobs.save_defaults({**original, "minimum_confidence": 0.92, "use_shazam": False})
        with pytest.raises(ValueError):
            jobs.save_defaults({"recognizer_timeout": 0})
        assert jobs.defaults["minimum_confidence"] == 0.92
    finally:
        jobs.close()
    reopened = create_jobs(tmp_path)
    try:
        assert reopened.defaults["minimum_confidence"] == 0.92
        assert reopened.defaults["use_shazam"] is False
        assert reopened.defaults["recognizer_timeout"] == original["recognizer_timeout"]
    finally:
        reopened.close()
