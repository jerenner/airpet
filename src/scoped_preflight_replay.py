from __future__ import annotations

import contextlib
import difflib
import io
import json
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
