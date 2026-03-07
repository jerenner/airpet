from app import app, SIMULATION_LOCK, SIMULATION_STATUS


def _set_sim_status(job_id, *, status="Running", progress=0, total_events=0, stdout=None, stderr=None):
    with SIMULATION_LOCK:
        SIMULATION_STATUS[job_id] = {
            "status": status,
            "progress": progress,
            "total_events": total_events,
            "stdout": list(stdout or []),
            "stderr": list(stderr or []),
        }


def _clear_sim_status(job_id):
    with SIMULATION_LOCK:
        SIMULATION_STATUS.pop(job_id, None)


def test_simulation_status_api_keeps_legacy_since_behavior():
    app.config["TESTING"] = True
    job_id = "api-sim-legacy"
    _set_sim_status(
        job_id,
        progress=20,
        total_events=100,
        stdout=["line-0", "line-1"],
        stderr=["err-0"],
    )

    try:
        with app.test_client() as client:
            resp = client.get(f"/api/simulation/status/{job_id}?since=1")

        assert resp.status_code == 200
        payload = resp.get_json()
        assert payload["success"] is True

        status = payload["status"]
        assert status["status"] == "Running"
        assert status["new_stdout"] == ["line-1", "stderr: err-0"]
        assert status["total_lines"] == 3
        assert status["next_since"] == 3
        assert status["has_more_logs"] is False
    finally:
        _clear_sim_status(job_id)


def test_simulation_status_api_supports_filter_aliases_and_pagination():
    app.config["TESTING"] = True
    job_id = "api-sim-filtered"
    _set_sim_status(
        job_id,
        progress=64,
        total_events=100,
        stdout=["init", "warning: drift", "done"],
        stderr=["fatal: overflow", "note: ignored"],
    )

    try:
        with app.test_client() as client:
            res_page_1 = client.get(
                f"/api/simulation/status/{job_id}"
                "?since=0"
                "&search_any=warn"
                "&search_any=fatal"
                "&max_lines=1"
                "&include_log_entries=true"
                "&include_log_summary=true"
            )
            res_page_2 = client.get(
                f"/api/simulation/status/{job_id}"
                "?since=1"
                "&search_any=warn"
                "&search_any=fatal"
                "&max_lines=1"
                "&include_log_entries=true"
            )

        assert res_page_1.status_code == 200
        payload_1 = res_page_1.get_json()
        assert payload_1["success"] is True
        status_1 = payload_1["status"]
        assert status_1["new_stdout"] == ["warning: drift"]
        assert status_1["log_total_lines"] == 2
        assert status_1["next_since"] == 1
        assert status_1["has_more_logs"] is True
        assert status_1["log_entries"] == [
            {"cursor": 0, "source": "stdout", "line": "warning: drift"}
        ]
        assert status_1["log_summary"] == {
            "stdout_lines": 3,
            "stderr_lines": 2,
            "has_errors": True,
            "latest_stdout": "done",
            "latest_stderr": "note: ignored",
        }

        assert res_page_2.status_code == 200
        payload_2 = res_page_2.get_json()
        assert payload_2["success"] is True
        status_2 = payload_2["status"]
        assert status_2["new_stdout"] == ["stderr: fatal: overflow"]
        assert status_2["next_since"] == 2
        assert status_2["has_more_logs"] is False
        assert status_2["log_entries"] == [
            {"cursor": 1, "source": "stderr", "line": "fatal: overflow"}
        ]
    finally:
        _clear_sim_status(job_id)
