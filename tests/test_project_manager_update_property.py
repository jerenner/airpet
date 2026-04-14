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


def test_update_object_property_supports_global_uniform_magnetic_field_updates():
    pm = _make_pm()

    success, error = pm.update_object_property(
        "environment",
        "global_uniform_magnetic_field",
        "enabled",
        True,
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.global_uniform_magnetic_field.enabled is True

    success, error = pm.update_object_property(
        "environment",
        "global_uniform_magnetic_field",
        "field_vector_tesla.y",
        "1.5",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.global_uniform_magnetic_field.field_vector_tesla == {
        "x": 0.0,
        "y": 1.5,
        "z": 0.0,
    }


def test_update_object_property_supports_global_uniform_electric_field_updates():
    pm = _make_pm()

    success, error = pm.update_object_property(
        "environment",
        "global_uniform_electric_field",
        "enabled",
        "true",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.global_uniform_electric_field.enabled is True

    success, error = pm.update_object_property(
        "environment",
        "global_uniform_electric_field",
        "field_vector_volt_per_meter.y",
        "2.5",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.global_uniform_electric_field.field_vector_volt_per_meter == {
        "x": 0.0,
        "y": 2.5,
        "z": 0.0,
    }


def test_update_object_property_supports_local_uniform_magnetic_field_updates():
    pm = _make_pm()

    success, error = pm.update_object_property(
        "environment",
        "local_uniform_magnetic_field",
        "enabled",
        "true",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.local_uniform_magnetic_field.enabled is True

    success, error = pm.update_object_property(
        "environment",
        "local_uniform_magnetic_field",
        "target_volume_names",
        "box_LV, detector_LV, box_LV",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.local_uniform_magnetic_field.target_volume_names == [
        "box_LV",
        "detector_LV",
    ]

    success, error = pm.update_object_property(
        "environment",
        "local_uniform_magnetic_field",
        "field_vector_tesla.z",
        "-0.5",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.local_uniform_magnetic_field.field_vector_tesla == {
        "x": 0.0,
        "y": 0.0,
        "z": -0.5,
    }


def test_update_object_property_supports_local_uniform_electric_field_updates():
    pm = _make_pm()

    success, error = pm.update_object_property(
        "environment",
        "local_uniform_electric_field",
        "enabled",
        True,
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.local_uniform_electric_field.enabled is True

    success, error = pm.update_object_property(
        "environment",
        "local_uniform_electric_field",
        "target_volume_names",
        "box_LV, detector_LV, box_LV",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.local_uniform_electric_field.target_volume_names == [
        "box_LV",
        "detector_LV",
    ]

    success, error = pm.update_object_property(
        "environment",
        "local_uniform_electric_field",
        "field_vector_volt_per_meter.z",
        "-0.75",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.local_uniform_electric_field.field_vector_volt_per_meter == {
        "x": 0.0,
        "y": 0.0,
        "z": -0.75,
    }


def test_update_object_property_supports_region_cuts_and_limits_updates():
    pm = _make_pm()

    success, error = pm.update_object_property(
        "environment",
        "region_cuts_and_limits",
        "enabled",
        "true",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.region_cuts_and_limits.enabled is True

    success, error = pm.update_object_property(
        "environment",
        "region_cuts_and_limits",
        "region_name",
        "tracker_region",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.region_cuts_and_limits.region_name == "tracker_region"

    success, error = pm.update_object_property(
        "environment",
        "region_cuts_and_limits",
        "target_volume_names",
        "box_LV, detector_LV, box_LV",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.region_cuts_and_limits.target_volume_names == [
        "box_LV",
        "detector_LV",
    ]

    success, error = pm.update_object_property(
        "environment",
        "region_cuts_and_limits",
        "production_cut_mm",
        "0.5",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.region_cuts_and_limits.production_cut_mm == 0.5

    success, error = pm.update_object_property(
        "environment",
        "region_cuts_and_limits",
        "max_step_mm",
        "0.1",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.region_cuts_and_limits.max_step_mm == 0.1

    success, error = pm.update_object_property(
        "environment",
        "region_cuts_and_limits",
        "max_track_length_mm",
        4.5,
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.region_cuts_and_limits.max_track_length_mm == 4.5

    success, error = pm.update_object_property(
        "environment",
        "region_cuts_and_limits",
        "max_time_ns",
        "25",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.region_cuts_and_limits.max_time_ns == 25.0

    success, error = pm.update_object_property(
        "environment",
        "region_cuts_and_limits",
        "min_kinetic_energy_mev",
        "0.002",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.region_cuts_and_limits.min_kinetic_energy_mev == 0.002

    success, error = pm.update_object_property(
        "environment",
        "region_cuts_and_limits",
        "min_range_mm",
        "0.05",
    )

    assert success is True
    assert error is None
    assert pm.current_geometry_state.environment.region_cuts_and_limits.min_range_mm == 0.05
