import os

import pytest

from app import (
    _normalize_simulation_run_id,
    _normalize_single_segment_selector_id,
    _resolve_saved_version_json_path,
    compare_autosave_preflight_vs_saved_version,
    compare_autosave_preflight_vs_snapshot_version,
    compare_autosave_snapshot_preflight_versions,
    compare_preflight_versions,
)
from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _make_pm(tmp_path):
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    pm.projects_dir = str(tmp_path)
    pm.project_name = "selector_id_sanitization_test_project"
    return pm


@pytest.mark.parametrize("raw_selector", [None, "", "   "])
def test_normalize_single_segment_selector_id_rejects_empty_and_null_values(raw_selector):
    with pytest.raises(ValueError, match="simulation_run_id is required"):
        _normalize_single_segment_selector_id(
            raw_selector,
            field_name="simulation_run_id",
            required_error=(
                "simulation_run_id is required to compare autosave against simulation-linked manual saves."
            ),
        )


@pytest.mark.parametrize("path_like_selector", [".", "..", "nested/run/id", r"nested\\run\\id"])
def test_normalize_single_segment_selector_id_rejects_path_like_values(path_like_selector):
    with pytest.raises(ValueError, match=r"Invalid version_id"):
        _normalize_single_segment_selector_id(
            path_like_selector,
            field_name="version_id",
            required_error="version_id must be a non-empty string.",
        )



def test_normalize_single_segment_selector_id_preserves_valid_alias_style_value():
    selector = _normalize_single_segment_selector_id(
        "run_id_alias_001",
        field_name="simulation_run_id",
        required_error="simulation_run_id is required to compare autosave against simulation-linked manual saves.",
    )
    assert selector == "run_id_alias_001"


@pytest.mark.parametrize("raw_selector", [None, "", "   ", ".", "..", "nested/run/id", r"nested\\run\\id"])
def test_normalize_simulation_run_id_uses_shared_single_segment_contract(raw_selector):
    with pytest.raises(ValueError):
        _normalize_simulation_run_id(raw_selector)



def test_resolve_saved_version_json_path_uses_shared_single_segment_contract(tmp_path):
    pm = _make_pm(tmp_path)

    saved_version_id, _ = pm.save_project_version("selector-sanitization-baseline")

    resolved_version_id, version_json_path = _resolve_saved_version_json_path(
        pm,
        pm.project_name,
        saved_version_id,
    )
    assert resolved_version_id == saved_version_id
    assert version_json_path == os.path.realpath(
        os.path.join(pm._get_version_dir(saved_version_id), "version.json")
    )

    with pytest.raises(ValueError, match="version_id must be a non-empty string"):
        _resolve_saved_version_json_path(pm, pm.project_name, " ")

    with pytest.raises(ValueError, match=r"Invalid version_id"):
        _resolve_saved_version_json_path(pm, pm.project_name, "nested/run/id")


@pytest.mark.parametrize(
    "selector_field,path_like_version_id",
    [
        ("baseline_version_id", "."),
        ("candidate_version_id", ".."),
        ("baseline_version_id", "nested/run/id"),
        ("candidate_version_id", r"nested\\run\\id"),
    ],
)
def test_compare_preflight_versions_rejects_path_like_baseline_or_candidate_version_selectors(
    selector_field,
    path_like_version_id,
    tmp_path,
):
    pm = _make_pm(tmp_path)

    baseline_version_id, _ = pm.save_project_version("selector-sanitization-compare-baseline")
    candidate_version_id, _ = pm.save_project_version("selector-sanitization-compare-candidate")

    compare_kwargs = {
        "baseline_version_id": baseline_version_id,
        "candidate_version_id": candidate_version_id,
    }
    compare_kwargs[selector_field] = path_like_version_id

    with pytest.raises(ValueError, match=r"Invalid version_id"):
        compare_preflight_versions(
            pm,
            project_name=pm.project_name,
            **compare_kwargs,
        )


@pytest.mark.parametrize("path_like_version_id", [".", "..", "nested/run/id", r"nested\\run\\id"])
def test_compare_autosave_vs_saved_version_rejects_path_like_selected_saved_version_ids(path_like_version_id, tmp_path):
    pm = _make_pm(tmp_path)

    with pytest.raises(ValueError, match=r"Invalid version_id"):
        compare_autosave_preflight_vs_saved_version(
            pm,
            saved_version_id=path_like_version_id,
            project_name=pm.project_name,
        )


@pytest.mark.parametrize("path_like_snapshot_id", [".", "..", "nested/run/id", r"nested\\run\\id"])
def test_compare_autosave_vs_snapshot_version_rejects_path_like_selected_snapshot_ids(path_like_snapshot_id, tmp_path):
    pm = _make_pm(tmp_path)

    with pytest.raises(ValueError, match=r"Invalid version_id"):
        compare_autosave_preflight_vs_snapshot_version(
            pm,
            autosave_snapshot_version_id=path_like_snapshot_id,
            project_name=pm.project_name,
        )


@pytest.mark.parametrize(
    "baseline_snapshot_version_id,candidate_snapshot_version_id",
    [
        (".", "20260318_autosave_snapshot_candidate"),
        ("20260318_autosave_snapshot_baseline", ".."),
        ("nested/run/id", "20260318_autosave_snapshot_candidate"),
        ("20260318_autosave_snapshot_baseline", r"nested\\run\\id"),
    ],
)
def test_compare_autosave_snapshot_versions_reject_path_like_baseline_or_candidate_selectors(
    baseline_snapshot_version_id,
    candidate_snapshot_version_id,
    tmp_path,
):
    pm = _make_pm(tmp_path)

    with pytest.raises(ValueError, match=r"Invalid version_id"):
        compare_autosave_snapshot_preflight_versions(
            pm,
            baseline_snapshot_version_id=baseline_snapshot_version_id,
            candidate_snapshot_version_id=candidate_snapshot_version_id,
            project_name=pm.project_name,
        )
