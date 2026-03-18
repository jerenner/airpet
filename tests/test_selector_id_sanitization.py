import os

import pytest

from app import (
    _normalize_simulation_run_id,
    _normalize_single_segment_selector_id,
    _resolve_saved_version_json_path,
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
