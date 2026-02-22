import os
import tempfile
from unittest.mock import patch

import h5py
import numpy as np

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
        "objectives": [
            {"metric": "success_flag", "name": "success", "direction": "maximize"},
            {"metric": "placements_count", "name": "placements", "direction": "maximize"}
        ]
    })
    assert study is not None and err is None

    result, err = pm.run_param_study("grid1")
    assert err is None
    assert result["requested_runs"] == 3
    assert result["successful_runs"] == 3
    vals = [r["values"]["p1"] for r in result["runs"]]
    assert vals[0] == 0.0
    assert vals[-1] == 10.0
    assert "success" in result["runs"][0]["objectives"]
    assert "placements" in result["runs"][0]["objectives"]


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


def test_param_optimizer_basic_and_provenance():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("opt1", {
        "name": "opt1",
        "mode": "random",
        "parameters": ["p1"],
        "random": {"samples": 4, "seed": 123},
        "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
    })
    assert study is not None and err is None

    result, err = pm.run_param_optimizer("opt1", budget=5, seed=7)
    assert err is None
    assert result["budget"] == 5
    assert len(result["candidates"]) == 5
    assert result["best_run"] is not None
    assert result["objective"]["name"] == "success"

    runs = pm.list_optimizer_runs(study_name="opt1")
    assert len(runs) >= 1
    assert runs[0]["study_name"] == "opt1"


def test_param_optimizer_budget_cap_is_enforced():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("opt_cap", {
        "name": "opt_cap",
        "mode": "random",
        "parameters": ["p1"],
        "random": {"samples": 4, "seed": 123},
        "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
    })
    assert study is not None and err is None

    result, err = pm.run_param_optimizer("opt_cap", budget=100000, seed=1)
    assert err is None
    assert result["budget"] == pm.MAX_OPTIMIZER_BUDGET
    assert len(result["candidates"]) == pm.MAX_OPTIMIZER_BUDGET


def test_param_optimizer_cmaes_backend_and_provenance():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("opt_cmaes", {
        "name": "opt_cmaes",
        "mode": "random",
        "parameters": ["p1"],
        "random": {"samples": 4, "seed": 123},
        "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
    })
    assert study is not None and err is None

    result, err = pm.run_param_optimizer(
        "opt_cmaes",
        method="cmaes",
        budget=18,
        seed=5,
        objective_name="success",
        direction="maximize",
        cmaes_config={"population_size": 6, "stagnation_generations": 2, "min_improvement": 1.0},
    )
    assert err is None
    assert result["method"] == "cmaes"
    assert len(result["candidates"]) <= 18
    assert result["evaluations_used"] == len(result["candidates"])
    assert "stop_reason" in result
    assert "generation_stats" in result
    assert "step_size_history" in result
    assert "cmaes" in result

    for cand in result["candidates"]:
        assert 0.0 <= float(cand["values"]["p1"]) <= 10.0


def test_param_optimizer_replay_and_verify_backend():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("opt_replay", {
        "name": "opt_replay",
        "mode": "random",
        "parameters": ["p1"],
        "random": {"samples": 3, "seed": 42},
        "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
    })
    assert study is not None and err is None

    opt, err = pm.run_param_optimizer("opt_replay", method="random_search", budget=4, seed=1)
    assert err is None
    run_id = opt["run_id"]

    replay, err = pm.replay_optimizer_best_candidate(run_id, apply_to_project=False)
    assert err is None
    assert replay["run_id"] == run_id
    assert replay["replay_record"]["success"] is True

    verify, err = pm.verify_optimizer_best_candidate(run_id, repeats=4)
    assert err is None
    assert verify["verification_record"]["repeats"] == 4
    assert verify["verification_record"]["stats"]["count"] >= 1


def test_param_optimizer_api_routes():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("opt_api", {
            "name": "opt_api",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 3, "seed": 42},
            "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
        })
        assert study is not None and err is None

        with patch("app.get_project_manager_for_session", return_value=pm):
            run_resp = client.post("/api/param_optimizer/run", json={
                "study_name": "opt_api",
                "method": "random_search",
                "budget": 4,
                "seed": 11,
                "objective_name": "success",
                "direction": "maximize",
            })
            assert run_resp.status_code == 200
            run_data = run_resp.get_json()
            assert run_data["success"] is True
            assert run_data["optimizer_result"]["budget"] == 4
            run_id = run_data["optimizer_result"]["run_id"]

            cmaes_resp = client.post("/api/param_optimizer/run", json={
                "study_name": "opt_api",
                "method": "cmaes",
                "budget": 6,
                "seed": 11,
                "objective_name": "success",
                "direction": "maximize",
                "cmaes": {"population_size": 4}
            })
            assert cmaes_resp.status_code == 200
            cmaes_data = cmaes_resp.get_json()
            assert cmaes_data["success"] is True
            assert cmaes_data["optimizer_result"]["method"] == "cmaes"

            replay_resp = client.post("/api/param_optimizer/replay_best", json={"run_id": run_id, "apply_to_project": False})
            assert replay_resp.status_code == 200
            replay_data = replay_resp.get_json()
            assert replay_data["success"] is True
            assert replay_data["replay_result"]["run_id"] == run_id

            verify_resp = client.post("/api/param_optimizer/verify_best", json={"run_id": run_id, "repeats": 3})
            assert verify_resp.status_code == 200
            verify_data = verify_resp.get_json()
            assert verify_data["success"] is True
            assert verify_data["verification_result"]["verification_record"]["repeats"] == 3

            list_resp = client.get("/api/param_optimizer/list?study_name=opt_api")
            assert list_resp.status_code == 200
            list_data = list_resp.get_json()
            assert list_data["success"] is True
            assert len(list_data["optimizer_runs"]) >= 2


def test_objective_extraction_api_from_hdf5():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()

        with tempfile.TemporaryDirectory() as tmp:
            version_id = "v_test"
            job_id = "j_test"
            run_dir = os.path.join(tmp, "sim_runs", job_id)
            os.makedirs(run_dir, exist_ok=True)
            output_path = os.path.join(run_dir, "output.hdf5")

            with h5py.File(output_path, "w") as f:
                g = f.create_group("default_ntuples/Hits")
                edep = np.array([1.0, 2.0, 3.0], dtype=float)
                copy_no = np.array([1, 1, 2], dtype=int)
                pnames = np.array([b"gamma", b"e-", b"gamma"])
                g.create_dataset("Edep", data=edep)
                g.create_dataset("CopyNo", data=copy_no)
                g.create_dataset("ParticleName", data=pnames)
                g.create_dataset("entries", data=np.array([3], dtype=int))

            with patch("app.get_project_manager_for_session", return_value=pm), \
                 patch.object(pm, "_get_version_dir", return_value=os.path.join(tmp)):
                resp = client.post(
                    f"/api/objectives/extract/{version_id}/{job_id}",
                    json={
                        "objectives": [
                            {"name": "hits", "metric": "total_hits"},
                            {"name": "edep_sum", "metric": "edep_sum"},
                            {"name": "gamma_frac", "metric": "particle_fraction", "particle": "gamma"},
                        ]
                    },
                )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["objective_values"]["hits"] == 3.0
            assert data["objective_values"]["edep_sum"] == 6.0
            assert data["objective_values"]["gamma_frac"] == 2.0 / 3.0
