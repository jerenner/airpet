from __future__ import annotations

import contextlib
import difflib
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

from app import app as flask_app
from app import dispatch_ai_tool
from src.expression_evaluator import ExpressionEvaluator
from src.geometry_types import ReplicaVolume
from src.project_manager import ProjectManager


DEFAULT_ARTIFACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "preflight"
    / "scoped_preflight_route_ai_workflow_replay.json"
)

DEFAULT_SAVED_VERSION_COMPARE_ARTIFACT_PATH = (
    Path(__file__).resolve().parents[1]
    / "examples"
    / "preflight"
    / "saved_version_preflight_compare_workflow_replay.json"
)


def load_replay_artifact(path: str | Path = DEFAULT_ARTIFACT_PATH) -> dict[str, Any]:
    artifact_path = Path(path)
    with artifact_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _create_project_manager() -> ProjectManager:
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


def _seed_scoped_preflight_drift_replica_overlap_fixture(pm: ProjectManager) -> dict[str, Any]:
    scope_name = "scope_drift_container_LV"

    scope_container, err = pm.add_logical_volume(scope_name, "box_solid", "G4_Galactic")
    if err is not None:
        raise RuntimeError(f"Failed creating scoped container LV: {err}")
    if scope_container["name"] != scope_name:
        raise RuntimeError("Unexpected scoped container LV name after fixture seed.")

    scope_leaf, err = pm.add_logical_volume("scope_drift_leaf_LV", "box_solid", "G4_Galactic")
    if err is not None:
        raise RuntimeError(f"Failed creating scoped leaf LV: {err}")

    replica_host, err = pm.add_logical_volume("scope_drift_replica_host_LV", "box_solid", "G4_Galactic")
    if err is not None:
        raise RuntimeError(f"Failed creating scoped replica host LV: {err}")

    _, err = pm.add_physical_volume(
        "box_LV",
        "scope_drift_container_PV",
        scope_name,
        {"x": "0", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    if err is not None:
        raise RuntimeError(f"Failed placing scoped container PV: {err}")

    _, err = pm.add_physical_volume(
        scope_name,
        "scope_drift_overlap_pv_a",
        scope_leaf["name"],
        {"x": "0", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    if err is not None:
        raise RuntimeError(f"Failed placing overlap PV A: {err}")

    _, err = pm.add_physical_volume(
        scope_name,
        "scope_drift_overlap_pv_b",
        scope_leaf["name"],
        {"x": "0", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    if err is not None:
        raise RuntimeError(f"Failed placing overlap PV B: {err}")

    _, err = pm.add_physical_volume(
        scope_name,
        "scope_drift_replica_host_pv",
        replica_host["name"],
        {"x": "1000", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    if err is not None:
        raise RuntimeError(f"Failed placing replica host PV: {err}")

    replica_lv = pm.current_geometry_state.logical_volumes[replica_host["name"]]
    replica_lv.content_type = "replica"
    replica_lv.content = ReplicaVolume(
        name="scope_drift_bad_replica",
        volume_ref="MissingScopedReplicaTarget",
        number="0",
        direction={"x": "0", "y": "0", "z": "0"},
        width="0",
        offset="0",
    )

    pm.current_geometry_state.logical_volumes[scope_leaf["name"]].material_ref = "MissingScopedMaterial"
    pm.current_geometry_state.logical_volumes["box_LV"].material_ref = "MissingOutsideScopeMaterial"

    return {
        "scope_name": scope_name,
        "expected_scope_summary_delta": {
            "errors": 5,
            "warnings": 1,
            "infos": 0,
            "issue_count": 6,
        },
        "expected_outside_scope_summary_delta": {
            "errors": 1,
            "warnings": 0,
            "infos": 0,
            "issue_count": 1,
        },
    }


def _call_preflight_route_with_pm(
    pm: ProjectManager,
    route_path: str,
    payload: dict[str, Any],
) -> tuple[int, dict[str, Any]]:
    with patch("app.get_project_manager_for_session", return_value=pm):
        with flask_app.test_client() as client:
            response = client.post(route_path, json=payload)
    return response.status_code, response.get_json()


def _json_text(data: Any) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)


def _build_diff(expected: Any, actual: Any, *, fromfile: str, tofile: str, max_lines: int) -> str:
    expected_text = _json_text(expected).splitlines()
    actual_text = _json_text(actual).splitlines()
    diff_lines = list(
        difflib.unified_diff(
            expected_text,
            actual_text,
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
        )
    )
    if not diff_lines:
        return "(no textual diff available)"
    if max_lines > 0 and len(diff_lines) > max_lines:
        hidden_count = len(diff_lines) - max_lines
        diff_lines = diff_lines[:max_lines] + [f"... ({hidden_count} additional diff lines hidden)"]
    return "\n".join(diff_lines)


def _sorted_scoped_issue_codes(route_data: dict[str, Any]) -> list[str]:
    scoped_report = route_data.get("scoped_preflight_report")
    if not isinstance(scoped_report, dict):
        return []

    issues = scoped_report.get("issues")
    if not isinstance(issues, list):
        return []

    codes: list[str] = []
    for issue in issues:
        if isinstance(issue, dict) and isinstance(issue.get("code"), str):
            codes.append(issue["code"])
    return sorted(codes)


def run_scoped_preflight_workflow_replay(
    artifact: dict[str, Any],
    *,
    max_diff_lines: int = 80,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record_check(name: str, ok: bool, details: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "details": details})

    workflow = artifact.get("workflow") if isinstance(artifact, dict) else None
    if not isinstance(workflow, dict):
        return {
            "passed": False,
            "checks": [
                {
                    "name": "workflow",
                    "ok": False,
                    "details": "Artifact is missing an object-valued 'workflow' section.",
                }
            ],
            "mismatches": ["Artifact is missing required 'workflow' structure."],
        }

    expected_contract = workflow.get("expected_contract")
    if not isinstance(expected_contract, dict):
        expected_contract = {}

    expected_excerpt = artifact.get("expected_response_excerpt")
    if not isinstance(expected_excerpt, dict):
        expected_excerpt = {}

    route_path = artifact.get("route") or "POST /api/preflight/check_scope"
    route_path = str(route_path)
    route_suffix = route_path.split(" ", 1)[1] if " " in route_path else route_path

    ai_wrapper = str(artifact.get("ai_wrapper") or "run_preflight_scope")
    route_payload = workflow.get("route_payload") if isinstance(workflow.get("route_payload"), dict) else {}
    ai_args = workflow.get("ai_args") if isinstance(workflow.get("ai_args"), dict) else {}

    expected_status = expected_contract.get("route_status_code")
    expect_identical = bool(expected_contract.get("route_ai_payload_identical"))

    pm = _create_project_manager()
    fixture = _seed_scoped_preflight_drift_replica_overlap_fixture(pm)

    route_status_code, route_data = _call_preflight_route_with_pm(pm, route_suffix, route_payload)
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        ai_data = dispatch_ai_tool(pm, ai_wrapper, ai_args)

    mismatches: list[str] = []

    if isinstance(expected_status, int):
        status_ok = route_status_code == expected_status
        record_check(
            "route_status_code",
            status_ok,
            f"expected={expected_status} actual={route_status_code}",
        )
        if not status_ok:
            mismatches.append(
                f"Route status mismatch: expected {expected_status}, got {route_status_code}."
            )
    else:
        record_check(
            "route_status_code",
            False,
            "Artifact missing integer workflow.expected_contract.route_status_code",
        )
        mismatches.append("Artifact contract is missing integer route_status_code.")

    if expect_identical:
        identical_ok = route_data == ai_data
        record_check("route_ai_payload_identical", identical_ok, f"expected=True actual={identical_ok}")
        if not identical_ok:
            mismatches.append(
                "Route/AI payload mismatch:\n"
                + _build_diff(route_data, ai_data, fromfile="route", tofile="ai", max_lines=max_diff_lines)
            )
    else:
        record_check("route_ai_payload_identical", True, "Artifact contract does not require strict equality.")

    if "success" in expected_excerpt:
        actual_success = route_data.get("success") if isinstance(route_data, dict) else None
        success_ok = actual_success == expected_excerpt.get("success")
        record_check("expected_response.success", success_ok, f"expected={expected_excerpt.get('success')} actual={actual_success}")
        if not success_ok:
            mismatches.append(
                "expected_response_excerpt.success mismatch:\n"
                + _build_diff(expected_excerpt.get("success"), actual_success, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    if "scope" in expected_excerpt:
        actual_scope = route_data.get("scope") if isinstance(route_data, dict) else None
        expected_scope = expected_excerpt.get("scope")
        scope_ok = actual_scope == expected_scope
        record_check("expected_response.scope", scope_ok, "scope payload comparison")
        if not scope_ok:
            mismatches.append(
                "expected_response_excerpt.scope mismatch:\n"
                + _build_diff(expected_scope, actual_scope, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    if "summary_delta" in expected_excerpt:
        actual_summary_delta = route_data.get("summary_delta") if isinstance(route_data, dict) else None
        expected_summary_delta = expected_excerpt.get("summary_delta")
        summary_delta_ok = actual_summary_delta == expected_summary_delta
        record_check("expected_response.summary_delta", summary_delta_ok, "summary_delta comparison")
        if not summary_delta_ok:
            mismatches.append(
                "expected_response_excerpt.summary_delta mismatch:\n"
                + _build_diff(expected_summary_delta, actual_summary_delta, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    if "scoped_issue_codes" in expected_excerpt:
        actual_scoped_issue_codes = _sorted_scoped_issue_codes(route_data if isinstance(route_data, dict) else {})
        expected_scoped_issue_codes = expected_excerpt.get("scoped_issue_codes")
        issue_codes_ok = actual_scoped_issue_codes == expected_scoped_issue_codes
        record_check("expected_response.scoped_issue_codes", issue_codes_ok, "sorted scoped issue-code comparison")
        if not issue_codes_ok:
            mismatches.append(
                "expected_response_excerpt.scoped_issue_codes mismatch:\n"
                + _build_diff(expected_scoped_issue_codes, actual_scoped_issue_codes, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    if "issue_family_correlations" in expected_excerpt:
        actual_correlations = route_data.get("issue_family_correlations") if isinstance(route_data, dict) else None
        expected_correlations = expected_excerpt.get("issue_family_correlations")
        correlations_ok = actual_correlations == expected_correlations
        record_check("expected_response.issue_family_correlations", correlations_ok, "issue-family correlation comparison")
        if not correlations_ok:
            mismatches.append(
                "expected_response_excerpt.issue_family_correlations mismatch:\n"
                + _build_diff(expected_correlations, actual_correlations, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    route_summary_delta = route_data.get("summary_delta") if isinstance(route_data, dict) else None
    scope_delta_ok = (
        isinstance(route_summary_delta, dict)
        and route_summary_delta.get("scope") == fixture["expected_scope_summary_delta"]
    )
    outside_scope_delta_ok = (
        isinstance(route_summary_delta, dict)
        and route_summary_delta.get("outside_scope") == fixture["expected_outside_scope_summary_delta"]
    )

    record_check("fixture_anchor.scope_summary_delta", scope_delta_ok, "fixture anchor check")
    if not scope_delta_ok:
        mismatches.append(
            "Fixture anchor mismatch for summary_delta.scope:\n"
            + _build_diff(
                fixture["expected_scope_summary_delta"],
                route_summary_delta.get("scope") if isinstance(route_summary_delta, dict) else None,
                fromfile="expected",
                tofile="actual",
                max_lines=max_diff_lines,
            )
        )

    record_check("fixture_anchor.outside_scope_summary_delta", outside_scope_delta_ok, "fixture anchor check")
    if not outside_scope_delta_ok:
        mismatches.append(
            "Fixture anchor mismatch for summary_delta.outside_scope:\n"
            + _build_diff(
                fixture["expected_outside_scope_summary_delta"],
                route_summary_delta.get("outside_scope") if isinstance(route_summary_delta, dict) else None,
                fromfile="expected",
                tofile="actual",
                max_lines=max_diff_lines,
            )
        )

    passed = all(check["ok"] for check in checks) and not mismatches

    return {
        "passed": passed,
        "checks": checks,
        "mismatches": mismatches,
        "route_status_code": route_status_code,
        "route_path": route_suffix,
        "ai_wrapper": ai_wrapper,
    }


def format_scoped_preflight_replay_report(
    result: dict[str, Any],
    *,
    artifact_path: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"STATUS: {'PASS' if result.get('passed') else 'FAIL'}")
    if artifact_path:
        lines.append(f"artifact: {artifact_path}")
    if result.get("route_path"):
        lines.append(f"route: {result['route_path']}")
    if result.get("ai_wrapper"):
        lines.append(f"ai_wrapper: {result['ai_wrapper']}")

    checks = result.get("checks") or []
    passed_count = sum(1 for check in checks if check.get("ok"))
    lines.append(f"checks: {passed_count}/{len(checks)} passed")

    for check in checks:
        status = "PASS" if check.get("ok") else "FAIL"
        lines.append(f"- [{status}] {check.get('name')}: {check.get('details')}")

    mismatches = result.get("mismatches") or []
    if mismatches:
        lines.append("mismatches:")
        for mismatch in mismatches:
            for idx, line in enumerate(str(mismatch).splitlines()):
                prefix = "  - " if idx == 0 else "    "
                lines.append(f"{prefix}{line}")

    return "\n".join(lines)


def _seed_saved_version_compare_fixture(
    pm: ProjectManager,
    *,
    baseline_version_id: str,
    candidate_version_id: str,
) -> None:
    baseline_version_dir = pm._get_version_dir(baseline_version_id)
    candidate_version_dir = pm._get_version_dir(candidate_version_id)

    os.makedirs(os.path.join(baseline_version_dir, "sim_runs"), exist_ok=True)
    with open(os.path.join(baseline_version_dir, "version.json"), "w", encoding="utf-8") as handle:
        handle.write(pm.save_project_to_json_string())

    pm.current_geometry_state.logical_volumes["box_LV"].material_ref = "MissingMat"
    pm.recalculate_geometry_state()

    os.makedirs(os.path.join(candidate_version_dir, "sim_runs"), exist_ok=True)
    with open(os.path.join(candidate_version_dir, "version.json"), "w", encoding="utf-8") as handle:
        handle.write(pm.save_project_to_json_string())


def _nested_subset_matches(actual: Any, expected: Any) -> bool:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(
            key in actual and _nested_subset_matches(actual[key], expected_value)
            for key, expected_value in expected.items()
        )

    if isinstance(expected, list):
        if not isinstance(actual, list) or len(actual) != len(expected):
            return False
        return all(
            _nested_subset_matches(actual_item, expected_item)
            for actual_item, expected_item in zip(actual, expected)
        )

    return actual == expected


def run_saved_version_compare_workflow_replay(
    artifact: dict[str, Any],
    *,
    max_diff_lines: int = 80,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def record_check(name: str, ok: bool, details: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "details": details})

    workflow = artifact.get("workflow") if isinstance(artifact, dict) else None
    if not isinstance(workflow, dict):
        return {
            "passed": False,
            "checks": [
                {
                    "name": "workflow",
                    "ok": False,
                    "details": "Artifact is missing an object-valued 'workflow' section.",
                }
            ],
            "mismatches": ["Artifact is missing required 'workflow' structure."],
        }

    expected_contract = workflow.get("expected_contract")
    if not isinstance(expected_contract, dict):
        expected_contract = {}

    expected_excerpt = artifact.get("expected_response_excerpt")
    if not isinstance(expected_excerpt, dict):
        expected_excerpt = {}

    route_path = str(artifact.get("route") or "POST /api/preflight/compare_versions")
    route_suffix = route_path.split(" ", 1)[1] if " " in route_path else route_path
    ai_wrapper = str(artifact.get("ai_wrapper") or "compare_preflight_versions")

    route_payload = workflow.get("route_payload") if isinstance(workflow.get("route_payload"), dict) else {}
    ai_args = workflow.get("ai_args") if isinstance(workflow.get("ai_args"), dict) else {}

    project_name = str(
        route_payload.get("project_name")
        or ai_args.get("project_name")
        or artifact.get("project_name")
        or "workflow_compare_project"
    ).strip()
    baseline_version_id = str(
        route_payload.get("baseline_version_id")
        or route_payload.get("baseline_version")
        or route_payload.get("before_version")
        or ai_args.get("baseline_version_id")
        or ai_args.get("baseline_version")
        or ai_args.get("before_version")
        or "workflow_compare_baseline"
    )
    candidate_version_id = str(
        route_payload.get("candidate_version_id")
        or route_payload.get("candidate_version")
        or route_payload.get("after_version")
        or ai_args.get("candidate_version_id")
        or ai_args.get("candidate_version")
        or ai_args.get("after_version")
        or "workflow_compare_candidate"
    )

    mismatches: list[str] = []

    with tempfile.TemporaryDirectory() as projects_dir:
        pm = _create_project_manager()
        pm.projects_dir = projects_dir
        pm.project_name = project_name
        pm.create_empty_project()
        _seed_saved_version_compare_fixture(
            pm,
            baseline_version_id=baseline_version_id,
            candidate_version_id=candidate_version_id,
        )

        route_status_code, route_data = _call_preflight_route_with_pm(pm, route_suffix, route_payload)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            ai_data = dispatch_ai_tool(pm, ai_wrapper, ai_args)

    if isinstance(expected_contract.get("route_status_code"), int):
        status_ok = route_status_code == expected_contract["route_status_code"]
        record_check(
            "route_status_code",
            status_ok,
            f"expected={expected_contract['route_status_code']} actual={route_status_code}",
        )
        if not status_ok:
            mismatches.append(
                f"Route status mismatch: expected {expected_contract['route_status_code']}, got {route_status_code}."
            )
    else:
        record_check(
            "route_status_code",
            False,
            "Artifact missing integer workflow.expected_contract.route_status_code",
        )
        mismatches.append("Artifact contract is missing integer route_status_code.")

    if "route_ai_payload_identical" in expected_contract:
        identical_ok = route_data == ai_data
        record_check(
            "route_ai_payload_identical",
            identical_ok == bool(expected_contract.get("route_ai_payload_identical")),
            f"expected={expected_contract.get('route_ai_payload_identical')} actual={identical_ok}",
        )
        if bool(expected_contract.get("route_ai_payload_identical")) and not identical_ok:
            mismatches.append(
                "Route/AI payload mismatch:\n"
                + _build_diff(route_data, ai_data, fromfile="route", tofile="ai", max_lines=max_diff_lines)
            )
    else:
        identical_ok = route_data == ai_data
        record_check("route_ai_payload_identical", identical_ok, f"expected=True actual={identical_ok}")
        if not identical_ok:
            mismatches.append(
                "Route/AI payload mismatch:\n"
                + _build_diff(route_data, ai_data, fromfile="route", tofile="ai", max_lines=max_diff_lines)
            )

    if "success" in expected_excerpt:
        actual_success = route_data.get("success") if isinstance(route_data, dict) else None
        success_ok = actual_success == expected_excerpt.get("success")
        record_check(
            "expected_response.success",
            success_ok,
            f"expected={expected_excerpt.get('success')} actual={actual_success}",
        )
        if not success_ok:
            mismatches.append(
                "expected_response_excerpt.success mismatch:\n"
                + _build_diff(expected_excerpt.get("success"), actual_success, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    for field_name in ("project_name", "baseline_version_id", "candidate_version_id"):
        if field_name in expected_excerpt:
            actual_value = route_data.get(field_name) if isinstance(route_data, dict) else None
            expected_value = expected_excerpt.get(field_name)
            value_ok = actual_value == expected_value
            record_check(
                f"expected_response.{field_name}",
                value_ok,
                f"expected={expected_value} actual={actual_value}",
            )
            if not value_ok:
                mismatches.append(
                    f"expected_response_excerpt.{field_name} mismatch:\n"
                    + _build_diff(expected_value, actual_value, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
                )

    if "baseline_report" in expected_excerpt:
        actual_baseline_report = route_data.get("baseline_report") if isinstance(route_data, dict) else None
        expected_baseline_report = expected_excerpt.get("baseline_report")
        baseline_ok = _nested_subset_matches(actual_baseline_report, expected_baseline_report)
        record_check("expected_response.baseline_report", baseline_ok, "baseline_report subset comparison")
        if not baseline_ok:
            mismatches.append(
                "expected_response_excerpt.baseline_report mismatch:\n"
                + _build_diff(expected_baseline_report, actual_baseline_report, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    if "candidate_report" in expected_excerpt:
        actual_candidate_report = route_data.get("candidate_report") if isinstance(route_data, dict) else None
        expected_candidate_report = expected_excerpt.get("candidate_report")
        candidate_ok = _nested_subset_matches(actual_candidate_report, expected_candidate_report)
        record_check("expected_response.candidate_report", candidate_ok, "candidate_report subset comparison")
        if not candidate_ok:
            mismatches.append(
                "expected_response_excerpt.candidate_report mismatch:\n"
                + _build_diff(expected_candidate_report, actual_candidate_report, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    if "comparison" in expected_excerpt:
        actual_comparison = route_data.get("comparison") if isinstance(route_data, dict) else None
        expected_comparison = expected_excerpt.get("comparison")
        comparison_ok = _nested_subset_matches(actual_comparison, expected_comparison)
        record_check("expected_response.comparison", comparison_ok, "comparison subset comparison")
        if not comparison_ok:
            mismatches.append(
                "expected_response_excerpt.comparison mismatch:\n"
                + _build_diff(expected_comparison, actual_comparison, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    if "ordering_metadata" in expected_excerpt:
        actual_ordering_metadata = route_data.get("ordering_metadata") if isinstance(route_data, dict) else None
        expected_ordering_metadata = expected_excerpt.get("ordering_metadata")
        ordering_ok = _nested_subset_matches(actual_ordering_metadata, expected_ordering_metadata)
        record_check("expected_response.ordering_metadata", ordering_ok, "ordering_metadata subset comparison")
        if not ordering_ok:
            mismatches.append(
                "expected_response_excerpt.ordering_metadata mismatch:\n"
                + _build_diff(expected_ordering_metadata, actual_ordering_metadata, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    if "version_sources" in expected_excerpt:
        actual_version_sources = route_data.get("version_sources") if isinstance(route_data, dict) else None
        expected_version_sources = expected_excerpt.get("version_sources")
        version_sources_ok = _nested_subset_matches(actual_version_sources, expected_version_sources)
        record_check("expected_response.version_sources", version_sources_ok, "version_sources subset comparison")
        if not version_sources_ok:
            mismatches.append(
                "expected_response_excerpt.version_sources mismatch:\n"
                + _build_diff(expected_version_sources, actual_version_sources, fromfile="expected", tofile="actual", max_lines=max_diff_lines)
            )

    passed = all(check["ok"] for check in checks) and not mismatches

    return {
        "passed": passed,
        "checks": checks,
        "mismatches": mismatches,
        "route_status_code": route_status_code,
        "route_path": route_suffix,
        "ai_wrapper": ai_wrapper,
    }


def format_saved_version_compare_replay_report(
    result: dict[str, Any],
    *,
    artifact_path: str | None = None,
) -> str:
    lines: list[str] = []
    lines.append(f"STATUS: {'PASS' if result.get('passed') else 'FAIL'}")
    if artifact_path:
        lines.append(f"artifact: {artifact_path}")
    if result.get("route_path"):
        lines.append(f"route: {result['route_path']}")
    if result.get("ai_wrapper"):
        lines.append(f"ai_wrapper: {result['ai_wrapper']}")

    checks = result.get("checks") or []
    passed_count = sum(1 for check in checks if check.get("ok"))
    lines.append(f"checks: {passed_count}/{len(checks)} passed")

    for check in checks:
        status = "PASS" if check.get("ok") else "FAIL"
        lines.append(f"- [{status}] {check.get('name')}: {check.get('details')}")

    mismatches = result.get("mismatches") or []
    if mismatches:
        lines.append("mismatches:")
        for mismatch in mismatches:
            for idx, line in enumerate(str(mismatch).splitlines()):
                prefix = "  - " if idx == 0 else "    "
                lines.append(f"{prefix}{line}")

    return "\n".join(lines)
