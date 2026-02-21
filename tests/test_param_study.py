from unittest.mock import patch

from app import app
from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _make_pm():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


def _add_define_param(pm, name="sweep_x"):
    obj, err = pm.add_define("sweep_define", "constant", "10", "mm", "geometry")
    assert obj is not None and err is None

    entry, err = pm.upsert_parameter_registry_entry(name, {
        "name": name,
        "target_type": "define",
        "target_ref": {"name": "sweep_define"},
        "bounds": {"min": 0, "max": 10},
        "default": 5,
        "units": "mm",
        "enabled": True,
    })
    assert entry is not None and err is None


def test_param_study_grid_run_basic():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("grid1", {
        "name": "grid1",
        "mode": "grid",
        "parameters": ["p1"],
        "grid": {"steps": 3},
    })
    assert study is not None and err is None

    result, err = pm.run_param_study("grid1")
    assert err is None
    assert result["requested_runs"] == 3
    assert result["successful_runs"] == 3
    vals = [r["values"]["p1"] for r in result["runs"]]
    assert vals[0] == 0.0
    assert vals[-1] == 10.0


def test_param_study_random_reproducible():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("rand1", {
        "name": "rand1",
        "mode": "random",
        "parameters": ["p1"],
        "random": {"samples": 4, "seed": 123},
    })
    assert study is not None and err is None

    r1, _ = pm.run_param_study("rand1")
    r2, _ = pm.run_param_study("rand1")

    vals1 = [x["values"]["p1"] for x in r1["runs"]]
    vals2 = [x["values"]["p1"] for x in r2["runs"]]
    assert vals1 == vals2


def test_param_study_persistence_roundtrip():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("grid_persist", {
        "name": "grid_persist",
        "mode": "grid",
        "parameters": ["p1"],
        "grid": {"steps": 2},
    })
    assert study is not None and err is None

    blob = pm.save_project_to_json_string()

    pm2 = ProjectManager(ExpressionEvaluator())
    pm2.load_project_from_json_string(blob)
    studies = pm2.list_param_studies()
    assert "grid_persist" in studies
    assert studies["grid_persist"]["mode"] == "grid"


def test_param_study_api_routes():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        with patch("app.get_project_manager_for_session", return_value=pm):
            upsert_resp = client.post("/api/param_study/upsert", json={
                "name": "grid_api",
                "mode": "grid",
                "parameters": ["p1"],
                "grid": {"steps": 3}
            })
            assert upsert_resp.status_code == 200
            assert upsert_resp.get_json()["success"] is True

            list_resp = client.get("/api/param_study/list")
            assert list_resp.status_code == 200
            assert "grid_api" in list_resp.get_json()["param_studies"]

            run_resp = client.post("/api/param_study/run", json={"name": "grid_api", "max_runs": 2})
            assert run_resp.status_code == 200
            run_data = run_resp.get_json()
            assert run_data["success"] is True
            assert run_data["study_result"]["requested_runs"] == 2

            del_resp = client.post("/api/param_study/delete", json={"name": "grid_api"})
            assert del_resp.status_code == 200
            assert del_resp.get_json()["success"] is True
