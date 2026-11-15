from workspace_support import make_jobs, start, wait_for_job


def test_resume_reuses_successful_checkpoints_after_forced_analysis(tmp_path):
    jobs = make_jobs(tmp_path, code="raise SystemExit(1)")
    try:
        identity = start(jobs)
        assert wait_for_job(jobs, identity)["state"] == "failed"
        jobs.store.update("jobs", identity, lambda job: {**job, "refresh_recognition": True})
        jobs.retry(identity)
        result = wait_for_job(jobs, identity)
        assert result["refresh_recognition"] is False
        assert result["attempt"] == 2
    finally:
        jobs.close()
