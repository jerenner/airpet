import copy

from src.scoped_preflight_replay import (
    DEFAULT_ARTIFACT_PATH,
    format_scoped_preflight_replay_report,
    load_replay_artifact,
    run_scoped_preflight_workflow_replay,
)


def test_scoped_preflight_replay_harness_passes_default_artifact():
    artifact = load_replay_artifact(DEFAULT_ARTIFACT_PATH)

    result = run_scoped_preflight_workflow_replay(artifact)

    assert result["passed"] is True
    assert result["route_path"] == "/api/preflight/check_scope"
    assert result["ai_wrapper"] == "run_preflight_scope"
    assert all(check["ok"] for check in result["checks"])
    assert result["mismatches"] == []


def test_scoped_preflight_replay_harness_reports_contract_mismatch():
    artifact = load_replay_artifact(DEFAULT_ARTIFACT_PATH)
    artifact = copy.deepcopy(artifact)
    artifact["workflow"]["expected_contract"]["route_status_code"] = 201

    result = run_scoped_preflight_workflow_replay(artifact, max_diff_lines=20)

    assert result["passed"] is False
    assert any(
        check["name"] == "route_status_code" and check["ok"] is False
        for check in result["checks"]
    )

    rendered = format_scoped_preflight_replay_report(result)
    assert "Route status mismatch" in rendered
    assert "expected 201" in rendered
