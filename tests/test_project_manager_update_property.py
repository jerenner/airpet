import pytest

from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _make_pm():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


@pytest.mark.parametrize("property_path", [".material_ref", "material_ref.", "content..number", "content...number"])
def test_update_object_property_rejects_invalid_nested_path_segments(property_path):
    pm = _make_pm()

    success, error = pm.update_object_property(
        "logical_volume",
        "box_LV",
        property_path,
        "G4_Si",
    )

    assert success is False
    assert error == f"Invalid property path '{property_path}'"


@pytest.mark.parametrize("property_path", [None, "", "   "])
def test_update_object_property_rejects_non_string_or_blank_property_path(property_path):
    pm = _make_pm()

    success, error = pm.update_object_property(
        "logical_volume",
        "box_LV",
        property_path,
        "G4_Si",
    )

    assert success is False
    assert error == f"Invalid property path '{property_path}'"


def test_update_object_property_reports_intermediate_dict_traversal_failures():
    pm = _make_pm()

    success, error = pm.update_object_property(
        "solid",
        "box_solid",
        "raw_parameters.inner.value",
        "10",
    )

    assert success is False
    assert error.startswith("Invalid property path 'raw_parameters.inner.value':")
    assert "'inner'" in error


def test_update_object_property_reports_intermediate_object_traversal_failures():
    pm = _make_pm()

    success, error = pm.update_object_property(
        "logical_volume",
        "World",
        "content.missing_attr.value",
        "10",
    )

    assert success is False
    assert error.startswith("Invalid property path 'content.missing_attr.value':")
    assert "missing_attr" in error


def test_update_object_property_keeps_valid_nested_dict_updates_working():
    pm = _make_pm()

    success, error = pm.update_object_property(
        "solid",
        "box_solid",
        "raw_parameters.x",
        "250",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.solids["box_solid"].raw_parameters["x"] == "250"
