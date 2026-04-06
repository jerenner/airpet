import json

from src.expression_evaluator import ExpressionEvaluator
from src.geometry_types import EnvironmentState, GeometryState
from src.project_manager import ProjectManager


def test_environment_state_defaults_and_roundtrip():
    state = GeometryState()

    field = state.environment.global_uniform_magnetic_field
    assert field.enabled is False
    assert field.field_vector_tesla == {"x": 0.0, "y": 0.0, "z": 0.0}

    payload = state.to_dict()
    assert payload["environment"] == {
        "global_uniform_magnetic_field": {
            "enabled": False,
            "field_vector_tesla": {"x": 0.0, "y": 0.0, "z": 0.0},
        }
    }

    round_tripped = GeometryState.from_dict(payload)
    assert round_tripped.environment.global_uniform_magnetic_field.to_dict() == payload["environment"][
        "global_uniform_magnetic_field"
    ]


def test_environment_state_validation_and_project_roundtrip():
    valid_payload = {
        "global_uniform_magnetic_field": {
            "enabled": True,
            "field_vector_tesla": {"x": 0.0, "y": 1.5, "z": -0.25},
        }
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

    bad_payload = {
        "global_uniform_magnetic_field": {
            "enabled": True,
            "field_vector_tesla": {"x": "not-a-number", "y": 0.0, "z": 0.0},
        }
    }

    ok, err = EnvironmentState.validate(bad_payload)
    assert ok is False
    assert "field_vector_tesla.x" in err

    defaulted = GeometryState.from_dict({"environment": bad_payload})
    assert defaulted.environment.global_uniform_magnetic_field.enabled is False
    assert defaulted.environment.global_uniform_magnetic_field.field_vector_tesla == {
        "x": 0.0,
        "y": 0.0,
        "z": 0.0,
    }

    legacy_loaded = GeometryState.from_dict(
        {
            "global_uniform_magnetic_field": {
                "enabled": True,
                "field_vector_tesla": {"x": 0.0, "y": 0.0, "z": 2.0},
            }
        }
    )
    assert legacy_loaded.environment.global_uniform_magnetic_field.to_dict() == {
        "enabled": True,
        "field_vector_tesla": {"x": 0.0, "y": 0.0, "z": 2.0},
    }

    pm = ProjectManager(ExpressionEvaluator())
    pm.current_geometry_state.environment = EnvironmentState.from_dict(
        {"global_uniform_magnetic_field": valid_payload["global_uniform_magnetic_field"]}
    )
    json_string = pm.save_project_to_json_string()
    data = json.loads(json_string)

    assert data["environment"] == valid_payload

    pm2 = ProjectManager(ExpressionEvaluator())
    pm2.load_project_from_json_string(json_string)
    assert pm2.current_geometry_state.environment.global_uniform_magnetic_field.to_dict() == {
        "enabled": True,
        "field_vector_tesla": {"x": 0.0, "y": 1.5, "z": -0.25},
    }
