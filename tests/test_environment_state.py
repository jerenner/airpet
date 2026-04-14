import json

from src.expression_evaluator import ExpressionEvaluator
from src.geometry_types import EnvironmentState, GeometryState
from src.project_manager import ProjectManager


def test_environment_state_defaults_and_roundtrip():
    state = GeometryState()

    field = state.environment.global_uniform_magnetic_field
    electric_field = state.environment.global_uniform_electric_field
    local_field = state.environment.local_uniform_magnetic_field
    local_electric_field = state.environment.local_uniform_electric_field
    region_controls = state.environment.region_cuts_and_limits
    assert field.enabled is False
    assert field.field_vector_tesla == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert electric_field.enabled is False
    assert electric_field.field_vector_volt_per_meter == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert local_field.enabled is False
    assert local_field.target_volume_names == []
    assert local_field.field_vector_tesla == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert local_electric_field.enabled is False
    assert local_electric_field.target_volume_names == []
    assert local_electric_field.field_vector_volt_per_meter == {"x": 0.0, "y": 0.0, "z": 0.0}
    assert region_controls.enabled is False
    assert region_controls.region_name == "airpet_region"
    assert region_controls.target_volume_names == []
    assert region_controls.production_cut_mm == 1.0
    assert region_controls.max_step_mm == 0.0
    assert region_controls.max_track_length_mm == 0.0
    assert region_controls.max_time_ns == 0.0
    assert region_controls.min_kinetic_energy_mev == 0.0
    assert region_controls.min_range_mm == 0.0

    payload = state.to_dict()
    assert payload["environment"] == {
        "global_uniform_magnetic_field": {
            "enabled": False,
            "field_vector_tesla": {"x": 0.0, "y": 0.0, "z": 0.0},
        },
        "global_uniform_electric_field": {
            "enabled": False,
            "field_vector_volt_per_meter": {"x": 0.0, "y": 0.0, "z": 0.0},
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

    assert state.environment.to_summary_dict() == {
        "has_active_controls": False,
        "active_control_count": 0,
        "summary_text": "No environment controls enabled.",
        "active_controls": [],
    }

    round_tripped = GeometryState.from_dict(payload)
    assert round_tripped.environment.to_dict() == payload["environment"]


def test_environment_state_validation_and_project_roundtrip():
    valid_payload = {
        "global_uniform_magnetic_field": {
            "enabled": True,
            "field_vector_tesla": {"x": 0.0, "y": 1.5, "z": -0.25},
        },
        "global_uniform_electric_field": {
            "enabled": True,
            "field_vector_volt_per_meter": {"x": 0.0, "y": -1.0, "z": 0.25},
        },
        "local_uniform_magnetic_field": {
            "enabled": True,
            "target_volume_names": ["box_LV", "detector_LV"],
            "field_vector_tesla": {"x": 0.0, "y": -0.75, "z": 0.5},
        },
        "local_uniform_electric_field": {
            "enabled": True,
            "target_volume_names": ["box_LV"],
            "field_vector_volt_per_meter": {"x": 0.0, "y": 0.25, "z": -0.5},
        },
        "region_cuts_and_limits": {
            "enabled": True,
            "region_name": "tracker_region",
            "target_volume_names": ["box_LV", "detector_LV"],
            "production_cut_mm": 0.5,
            "max_step_mm": 0.1,
            "max_track_length_mm": 5.0,
            "max_time_ns": 20.0,
            "min_kinetic_energy_mev": 0.002,
            "min_range_mm": 0.05,
        },
    }

    ok, err = EnvironmentState.validate(valid_payload)
    assert ok is True
    assert err is None

    loaded = GeometryState.from_dict({"environment": valid_payload})
    assert loaded.environment.global_uniform_magnetic_field.enabled is True
    assert loaded.environment.global_uniform_magnetic_field.field_vector_tesla == {
        "x": 0.0,
        "y": 1.5,
        "z": -0.25,
    }
    assert loaded.environment.global_uniform_electric_field.enabled is True
    assert loaded.environment.global_uniform_electric_field.field_vector_volt_per_meter == {
        "x": 0.0,
        "y": -1.0,
        "z": 0.25,
    }
    assert loaded.environment.local_uniform_magnetic_field.enabled is True
    assert loaded.environment.local_uniform_magnetic_field.target_volume_names == ["box_LV", "detector_LV"]
    assert loaded.environment.local_uniform_magnetic_field.field_vector_tesla == {
        "x": 0.0,
        "y": -0.75,
        "z": 0.5,
    }
    assert loaded.environment.local_uniform_electric_field.enabled is True
    assert loaded.environment.local_uniform_electric_field.target_volume_names == ["box_LV"]
    assert loaded.environment.local_uniform_electric_field.field_vector_volt_per_meter == {
        "x": 0.0,
        "y": 0.25,
        "z": -0.5,
    }
    assert loaded.environment.region_cuts_and_limits.enabled is True
    assert loaded.environment.region_cuts_and_limits.region_name == "tracker_region"
    assert loaded.environment.region_cuts_and_limits.target_volume_names == ["box_LV", "detector_LV"]
    assert loaded.environment.region_cuts_and_limits.production_cut_mm == 0.5
    assert loaded.environment.region_cuts_and_limits.max_step_mm == 0.1
    assert loaded.environment.region_cuts_and_limits.max_track_length_mm == 5.0
    assert loaded.environment.region_cuts_and_limits.max_time_ns == 20.0
    assert loaded.environment.region_cuts_and_limits.min_kinetic_energy_mev == 0.002
    assert loaded.environment.region_cuts_and_limits.min_range_mm == 0.05

    summary = loaded.environment.to_summary_dict()
    assert summary["has_active_controls"] is True
    assert summary["active_control_count"] == 5
    assert summary["active_controls"][0]["kind"] == "global_uniform_magnetic_field"
    assert summary["active_controls"][-1]["kind"] == "region_cuts_and_limits"
    assert "Global magnetic field: (0, 1.5, -0.25) T" in summary["summary_text"]
    assert "Region cuts and limits: region tracker_region" in summary["summary_text"]

    electric_bad_payload = {
        "global_uniform_electric_field": {
            "enabled": True,
            "field_vector_volt_per_meter": {"x": "not-a-number", "y": 0.0, "z": 0.0},
        }
    }

    ok, err = EnvironmentState.validate(electric_bad_payload)
    assert ok is False
    assert "global_uniform_electric_field.field_vector_volt_per_meter.x" in err

    region_bad_payload = {
        "region_cuts_and_limits": {
            "enabled": True,
            "region_name": "tracker_region",
            "target_volume_names": ["box_LV"],
            "production_cut_mm": "not-a-number",
        }
    }

    ok, err = EnvironmentState.validate(region_bad_payload)
    assert ok is False
    assert "region_cuts_and_limits.production_cut_mm" in err

    bad_payload = {
        "local_uniform_magnetic_field": {
            "enabled": True,
            "target_volume_names": ["box_LV"],
            "field_vector_tesla": {"x": "not-a-number", "y": 0.0, "z": 0.0},
        }
    }

    ok, err = EnvironmentState.validate(bad_payload)
    assert ok is False
    assert "local_uniform_magnetic_field.field_vector_tesla.x" in err

    defaulted = GeometryState.from_dict({"environment": bad_payload})
    assert defaulted.environment.local_uniform_magnetic_field.enabled is False
    assert defaulted.environment.local_uniform_magnetic_field.target_volume_names == []
    assert defaulted.environment.local_uniform_magnetic_field.field_vector_tesla == {
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
    }
    assert defaulted.environment.global_uniform_electric_field.to_dict() == {
        "enabled": False,
        "field_vector_volt_per_meter": {"x": 0.0, "y": 0.0, "z": 0.0},
    }
    assert defaulted.environment.local_uniform_electric_field.to_dict() == {
        "enabled": False,
        "target_volume_names": [],
        "field_vector_volt_per_meter": {"x": 0.0, "y": 0.0, "z": 0.0},
    }
    assert defaulted.environment.region_cuts_and_limits.to_dict() == {
        "enabled": False,
        "region_name": "airpet_region",
        "target_volume_names": [],
        "production_cut_mm": 1.0,
        "max_step_mm": 0.0,
        "max_track_length_mm": 0.0,
        "max_time_ns": 0.0,
        "min_kinetic_energy_mev": 0.0,
        "min_range_mm": 0.0,
    }

    legacy_loaded = GeometryState.from_dict(
        {
            "global_uniform_magnetic_field": {
                "enabled": True,
                "field_vector_tesla": {"x": 0.0, "y": 0.0, "z": 2.0},
            },
            "global_uniform_electric_field": {
                "enabled": True,
                "field_vector_volt_per_meter": {"x": 0.0, "y": 0.0, "z": -3.0},
            },
            "region_cuts_and_limits": {
                "enabled": True,
                "region_name": "legacy_region",
                "target_volume_names": ["box_LV"],
                "production_cut_mm": 0.75,
                "max_step_mm": 0.0,
                "max_track_length_mm": 2.5,
                "max_time_ns": 10.0,
                "min_kinetic_energy_mev": 0.001,
                "min_range_mm": 0.02,
            },
        }
    )
    assert legacy_loaded.environment.global_uniform_magnetic_field.to_dict() == {
        "enabled": True,
        "field_vector_tesla": {"x": 0.0, "y": 0.0, "z": 2.0},
    }
    assert legacy_loaded.environment.global_uniform_electric_field.to_dict() == {
        "enabled": True,
        "field_vector_volt_per_meter": {"x": 0.0, "y": 0.0, "z": -3.0},
    }
    assert legacy_loaded.environment.local_uniform_magnetic_field.to_dict() == {
        "enabled": False,
        "target_volume_names": [],
        "field_vector_tesla": {"x": 0.0, "y": 0.0, "z": 0.0},
    }
    assert legacy_loaded.environment.local_uniform_electric_field.to_dict() == {
        "enabled": False,
        "target_volume_names": [],
        "field_vector_volt_per_meter": {"x": 0.0, "y": 0.0, "z": 0.0},
    }
    assert legacy_loaded.environment.region_cuts_and_limits.to_dict() == {
        "enabled": True,
        "region_name": "legacy_region",
        "target_volume_names": ["box_LV"],
        "production_cut_mm": 0.75,
        "max_step_mm": 0.0,
        "max_track_length_mm": 2.5,
        "max_time_ns": 10.0,
        "min_kinetic_energy_mev": 0.001,
        "min_range_mm": 0.02,
    }

    pm = ProjectManager(ExpressionEvaluator())
    pm.current_geometry_state.environment = EnvironmentState.from_dict(valid_payload)
    json_string = pm.save_project_to_json_string()
    data = json.loads(json_string)

    assert data["environment"] == valid_payload

    pm2 = ProjectManager(ExpressionEvaluator())
    pm2.load_project_from_json_string(json_string)
    assert pm2.current_geometry_state.environment.to_dict() == valid_payload
