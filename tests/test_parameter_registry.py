import json
from unittest.mock import patch

from app import app
from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _make_pm():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


def _valid_define_parameter_payload():
    return {
        "name": "world_size_x",
        "target_type": "define",
        "target_ref": {"name": "world_solid_x_half"},
        "bounds": {"min": 1000, "max": 20000},
        "default": 10000,
        "units": "mm",
        "enabled": True,
        "constraint_group": None,
    }


def test_parameter_registry_upsert_and_list():
    pm = _make_pm()

    # create a define target first
    obj, err = pm.add_define("world_solid_x_half", "constant", "5000", "mm", "geometry")
    assert obj is not None and err is None

    payload = _valid_define_parameter_payload()
    entry, err = pm.upsert_parameter_registry_entry(payload["name"], payload)

    assert err is None
    assert entry["name"] == "world_size_x"
    reg = pm.list_parameter_registry()
    assert "world_size_x" in reg
    assert reg["world_size_x"]["bounds"]["min"] == 1000.0


def test_parameter_registry_rejects_invalid_bounds():
    pm = _make_pm()
    obj, err = pm.add_define("foo_define", "constant", "1", "mm", "geometry")
    assert obj is not None and err is None

    payload = {
        "name": "bad_bounds",
        "target_type": "define",
        "target_ref": {"name": "foo_define"},
        "bounds": {"min": 10, "max": 1},
        "default": 5,
    }

    entry, err = pm.upsert_parameter_registry_entry("bad_bounds", payload)
    assert entry is None
    assert "bounds.min" in err


def test_parameter_registry_persistence_roundtrip():
    pm = _make_pm()
    obj, err = pm.add_define("persist_define", "constant", "10", "mm", "geometry")
    assert obj is not None and err is None

    payload = {
        "name": "persist_param",
        "target_type": "define",
        "target_ref": {"name": "persist_define"},
        "bounds": {"min": 1, "max": 100},
        "default": 10,
        "units": "mm",
        "enabled": True,
    }

    entry, err = pm.upsert_parameter_registry_entry("persist_param", payload)
    assert entry is not None and err is None

    json_string = pm.save_project_to_json_string()

    pm2 = ProjectManager(ExpressionEvaluator())
    pm2.load_project_from_json_string(json_string)

    reg = pm2.list_parameter_registry()
    assert "persist_param" in reg
    assert reg["persist_param"]["target_type"] == "define"


def test_parameter_registry_backward_compat_when_missing_field():
    pm = _make_pm()
    json_string = pm.save_project_to_json_string()
    data = json.loads(json_string)
    data.pop("parameter_registry", None)

    pm2 = ProjectManager(ExpressionEvaluator())
    pm2.load_project_from_json_string(json.dumps(data))

    reg = pm2.list_parameter_registry()
    assert reg == {}


def test_parameter_registry_api_routes():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        obj, err = pm.add_define("api_define", "constant", "10", "mm", "geometry")
        assert obj is not None and err is None

        with patch("app.get_project_manager_for_session", return_value=pm):
            upsert_resp = client.post(
                "/api/parameter_registry/upsert",
                json={
                    "name": "api_param",
                    "target_type": "define",
                    "target_ref": {"name": "api_define"},
                    "bounds": {"min": 0, "max": 20},
                    "default": 10,
                    "units": "mm",
                    "enabled": True,
                },
            )
            assert upsert_resp.status_code == 200
            upsert_data = upsert_resp.get_json()
            assert upsert_data["success"] is True

            list_resp = client.get("/api/parameter_registry/list")
            assert list_resp.status_code == 200
            list_data = list_resp.get_json()
            assert list_data["success"] is True
            assert "api_param" in list_data["parameter_registry"]

            delete_resp = client.post("/api/parameter_registry/delete", json={"name": "api_param"})
            assert delete_resp.status_code == 200
            delete_data = delete_resp.get_json()
            assert delete_data["success"] is True
