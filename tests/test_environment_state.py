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

    electric_bad_payload = {
        "global_uniform_electric_field": {
            "enabled": True,
            "field_vector_volt_per_meter": {"x": "not-a-number", "y": 0.0, "z": 0.0},
        }
    }

    ok, err = EnvironmentState.validate(electric_bad_payload)
    assert ok is False
    assert "global_uniform_electric_field.field_vector_volt_per_meter.x" in err

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

    pm = ProjectManager(ExpressionEvaluator())
    pm.current_geometry_state.environment = EnvironmentState.from_dict(valid_payload)
    json_string = pm.save_project_to_json_string()
    data = json.loads(json_string)

    assert data["environment"] == valid_payload

    pm2 = ProjectManager(ExpressionEvaluator())
    pm2.load_project_from_json_string(json_string)
    assert pm2.current_geometry_state.environment.to_dict() == valid_payload
