import json
from pathlib import Path

from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _load_field_aware_starter_pm():
    pm = ProjectManager(ExpressionEvaluator())
    starter_path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "field_aware"
        / "field_aware_silicon_starter.project.json"
    )
    with starter_path.open("r", encoding="utf-8") as handle:
        pm.load_project_from_json_string(handle.read())
    return pm


def test_field_aware_silicon_starter_saves_explicit_fields():
    pm = _load_field_aware_starter_pm()

    environment = pm.current_geometry_state.environment.to_dict()
    assert environment == {
        "global_uniform_magnetic_field": {
            "enabled": True,
            "field_vector_tesla": {"x": 0.0, "y": 1.5, "z": 0.0},
        },
        "global_uniform_electric_field": {
            "enabled": True,
            "field_vector_volt_per_meter": {"x": 0.0, "y": 0.0, "z": 2500.0},
        },
        "local_uniform_magnetic_field": {
            "enabled": False,
            "target_volume_names": [],
            "field_vector_tesla": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "local_uniform_electric_field": {
            "enabled": False,
            "target_volume_names": [],
            "field_vector_volt_per_meter": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "region_cuts_and_limits": {
            "enabled": False,
            "region_name": "airpet_region",
            "target_volume_names": [],
            "production_cut_mm": 1.0,
            "max_step_mm": 0.0,
            "max_track_length_mm": 0.0,
            "max_time_ns": 0.0,
            "min_kinetic_energy_mev": 0.0,
            "min_range_mm": 0.0,
        },
    }

    assert pm.current_geometry_state.param_studies["si_first_run"]["parameters"] == ["si_thickness", "src_z"]
    assert list(pm.current_geometry_state.active_source_ids or [])

    saved_payload = json.loads(pm.save_project_to_json_string())
    assert saved_payload["environment"] == environment
    assert saved_payload["param_studies"]["si_first_run"]["parameters"] == ["si_thickness", "src_z"]
