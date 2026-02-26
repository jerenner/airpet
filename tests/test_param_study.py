import json
import os
import tempfile
from unittest.mock import patch

import h5py
import numpy as np

import app as app_module
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


def test_param_study_parameter_value_objective_metric():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("obj_param_val", {
        "name": "obj_param_val",
        "mode": "grid",
        "parameters": ["p1"],
        "grid": {"steps": 2},
        "objectives": [{"metric": "parameter_value", "name": "p1_value", "direction": "maximize", "parameter": "p1"}],
    })
    assert study is not None and err is None

    result, err = pm.run_param_study("obj_param_val")
    assert err is None
    vals = [r["objectives"]["p1_value"] for r in result["runs"]]
    assert vals == [0.0, 10.0]


def test_param_study_silicon_slab_tradeoff_objectives():
    pm = _make_pm()
    _add_define_param(pm, name="thickness")

    study, err = pm.upsert_param_study("silicon_obj", {
        "name": "silicon_obj",
        "mode": "grid",
        "parameters": ["thickness"],
        "grid": {"steps": 3},
        "objectives": [
            {
                "metric": "silicon_slab_tradeoff",
                "name": "score",
                "direction": "maximize",
                "thickness_parameter": "thickness",
                "attenuation_length_mm": 2.0,
                "reference_thickness_mm": 5.0,
                "w_edep": 0.8,
                "w_cost": 0.2,
            },
            {
                "metric": "silicon_slab_edep_fraction",
                "name": "edep_fraction",
                "direction": "maximize",
                "thickness_parameter": "thickness",
                "attenuation_length_mm": 2.0,
            },
            {
                "metric": "silicon_slab_cost_norm",
                "name": "cost_norm",
                "direction": "minimize",
                "thickness_parameter": "thickness",
                "reference_thickness_mm": 5.0,
            },
        ],
    })
    assert study is not None and err is None

    result, err = pm.run_param_study("silicon_obj")
    assert err is None
    assert result["requested_runs"] == 3

    edep_vals = [r["objectives"]["edep_fraction"] for r in result["runs"]]
    cost_vals = [r["objectives"]["cost_norm"] for r in result["runs"]]
    score_vals = [r["objectives"]["score"] for r in result["runs"]]

    assert all(0.0 <= x <= 1.0 for x in edep_vals)
    assert cost_vals[0] < cost_vals[1] < cost_vals[2]
    assert score_vals[1] > score_vals[0]


def test_param_study_sim_metric_and_formula_evaluation():
    pm = _make_pm()

    run_record = {
        "success": True,
        "metrics": {"solids_count": 3},
        "values": {"thickness": 2.5},
        "sim_metrics": {"edep_sum": 12.0},
    }

    objectives = [
        {"metric": "sim_metric", "name": "edep", "key": "edep_sum", "direction": "maximize"},
        {"metric": "parameter_value", "name": "t", "parameter": "thickness", "direction": "minimize"},
        {"metric": "formula", "name": "score", "expression": "0.8*edep - 0.2*t", "direction": "maximize"},
    ]

    out = pm._evaluate_study_objectives(objectives, run_record)
    assert out["edep"] == 12.0
    assert out["t"] == 2.5
    assert abs(out["score"] - 9.1) < 1e-9


def test_param_study_sim_metric_formula_two_parameter_tradeoff():
    pm = _make_pm()

    run_record = {
        "success": True,
        "metrics": {"solids_count": 3},
        "values": {"thickness_mm": 2.0, "half_xy_mm": 15.0},
        "sim_metrics": {"edep_sum": 1.5},
    }

    objectives = [
        {"metric": "sim_metric", "name": "edep_sum", "key": "edep_sum", "direction": "maximize"},
        {"metric": "parameter_value", "name": "t", "parameter": "thickness_mm", "direction": "minimize"},
        {"metric": "parameter_value", "name": "w", "parameter": "half_xy_mm", "direction": "minimize"},
        {"metric": "formula", "name": "cost_norm", "expression": "(t/3.0) * (w/12.5)**2", "direction": "minimize"},
        {"metric": "formula", "name": "score", "expression": "0.8*edep_sum - 0.2*cost_norm", "direction": "maximize"},
    ]

    out = pm._evaluate_study_objectives(objectives, run_record)
    assert out["edep_sum"] == 1.5
    assert out["t"] == 2.0
    assert out["w"] == 15.0
    assert abs(out["cost_norm"] - 0.96) < 1e-9
    assert abs(out["score"] - 1.008) < 1e-9


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


def test_replay_best_api_requires_allow_apply_gate():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("opt_apply_gate", {
            "name": "opt_apply_gate",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 3, "seed": 42},
            "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
        })
        assert study is not None and err is None

        run, err = pm.run_param_optimizer("opt_apply_gate", method="random_search", budget=4, seed=11)
        assert run is not None and err is None
        run_id = run["run_id"]

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch("app.RUN_POLICY_REQUIRE_VERIFY_TOKEN", False):
            denied = client.post("/api/param_optimizer/replay_best", json={
                "run_id": run_id,
                "apply_to_project": True,
            })
            assert denied.status_code == 400
            denied_data = denied.get_json()
            assert denied_data["success"] is False
            assert denied_data["error"] == "Apply policy validation failed."

            allowed = client.post("/api/param_optimizer/replay_best", json={
                "run_id": run_id,
                "apply_to_project": True,
                "allow_apply": True,
            })
            assert allowed.status_code == 200
            allowed_data = allowed.get_json()
            assert allowed_data["success"] is True
            assert allowed_data["replay_result"]["run_id"] == run_id
            assert allowed_data["apply_policy"]["apply_to_project"] is True
            assert allowed_data["apply_policy"]["allow_apply"] is True


def test_replay_best_api_requires_verification_token_binding():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("opt_apply_token", {
            "name": "opt_apply_token",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 3, "seed": 42},
            "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
        })
        assert study is not None and err is None

        run, err = pm.run_param_optimizer("opt_apply_token", method="random_search", budget=4, seed=11)
        assert run is not None and err is None
        run_id = run["run_id"]

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch("app.RUN_POLICY_REQUIRE_VERIFY_TOKEN", True), \
             patch("app.RUN_POLICY_REQUIRE_ALLOW_APPLY", True):
            missing = client.post("/api/param_optimizer/replay_best", json={
                "run_id": run_id,
                "apply_to_project": True,
                "allow_apply": True,
            })
            assert missing.status_code == 400
            missing_data = missing.get_json()
            assert missing_data["success"] is False
            assert missing_data["error"] == "Apply policy validation failed."

            verify = client.post("/api/param_optimizer/verify_best", json={
                "run_id": run_id,
                "repeats": 3,
                "min_success_rate": 1.0,
            })
            assert verify.status_code == 200
            verify_data = verify.get_json()
            assert verify_data["success"] is True
            assert verify_data["verification_gate"]["passed"] is True
            token = verify_data["apply_token"]
            assert token is not None

            allowed = client.post("/api/param_optimizer/replay_best", json={
                "run_id": run_id,
                "apply_to_project": True,
                "allow_apply": True,
                "verification_token": token,
            })
            assert allowed.status_code == 200
            allowed_data = allowed.get_json()
            assert allowed_data["success"] is True
            assert allowed_data["apply_policy"]["verification_token"] == token

            reused = client.post("/api/param_optimizer/replay_best", json={
                "run_id": run_id,
                "apply_to_project": True,
                "allow_apply": True,
                "verification_token": token,
            })
            assert reused.status_code == 400
            reused_data = reused.get_json()
            assert reused_data["success"] is False
            assert reused_data["error"] == "Apply policy validation failed."


def test_verify_best_gate_requires_min_repeats_before_token_issue():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("opt_verify_min_repeats", {
            "name": "opt_verify_min_repeats",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 3, "seed": 42},
            "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
        })
        assert study is not None and err is None

        run, err = pm.run_param_optimizer("opt_verify_min_repeats", method="random_search", budget=4, seed=11)
        assert run is not None and err is None
        run_id = run["run_id"]

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch("app.RUN_POLICY_VERIFY_MIN_REPEATS", 3):
            verify = client.post("/api/param_optimizer/verify_best", json={
                "run_id": run_id,
                "repeats": 1,
            })

        assert verify.status_code == 200
        verify_data = verify.get_json()
        assert verify_data["success"] is True
        assert verify_data["verification_gate"]["passed"] is False
        assert verify_data["verification_gate"]["min_repeats"] == 3
        assert verify_data["apply_token"] is None


def test_objective_builder_schema_endpoint():
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/objective_builder/schema")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True

    schema = data["schema"]
    assert schema["version"].startswith("m6-objective-builder-")
    assert "simulation_extract_metrics" in schema
    assert "study_objective_metrics" in schema
    assert "formula" in schema
    assert "allowed_functions" in schema["formula"]
    assert "clip" in schema["formula"]["allowed_functions"]
    assert "run_policy" in schema
    assert "max_budget" in schema["run_policy"]


def test_objective_builder_example_endpoint_default_template():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        with patch("app.get_project_manager_for_session", return_value=pm):
            resp = client.get("/api/objective_builder/example")

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    payload = data["payload"]
    assert payload["template_id"] == "weighted_tradeoff"
    assert isinstance(payload["extract_objectives"], list)
    assert isinstance(payload["study_objectives"], list)
    assert "p1" in payload["study_parameters"]


def test_objective_builder_example_endpoint_invalid_template():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()

        with patch("app.get_project_manager_for_session", return_value=pm):
            resp = client.get("/api/objective_builder/example?template=does_not_exist")

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert "Unknown template" in data["error"]
    assert "available_templates" in data


def test_objective_builder_validate_endpoint_valid_payload():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        with patch("app.get_project_manager_for_session", return_value=pm):
            resp = client.post("/api/objective_builder/validate", json={
                "extract_objectives": [
                    {"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"},
                    {"name": "cost_norm", "metric": "context_value", "key": "cost_norm", "default": 0.0},
                ],
                "study_parameters": ["p1"],
                "study_objectives": [
                    {"name": "edep_sum", "metric": "sim_metric", "key": "edep_sum", "direction": "maximize"},
                    {"name": "p1_cost", "metric": "parameter_value", "parameter": "p1", "direction": "minimize"},
                    {"name": "score", "metric": "formula", "expression": "0.8*edep_sum - 0.2*p1_cost", "direction": "maximize"},
                ],
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    validation = data["validation"]
    assert validation["valid"] is True
    assert validation["errors"] == []


def test_objective_builder_validate_endpoint_invalid_formula():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        with patch("app.get_project_manager_for_session", return_value=pm):
            resp = client.post("/api/objective_builder/validate", json={
                "extract_objectives": [
                    {"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"}
                ],
                "study_parameters": ["p1"],
                "study_objectives": [
                    {"name": "score", "metric": "formula", "expression": "0.8*(edep_sum -", "direction": "maximize"}
                ],
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    validation = data["validation"]
    assert validation["valid"] is False
    assert any("formula" in e for e in validation["errors"])


def test_objective_builder_build_endpoint_valid_payload():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        with patch("app.get_project_manager_for_session", return_value=pm):
            resp = client.post("/api/objective_builder/build", json={
                "study_name": "m6_builder_demo",
                "extract_objectives": [
                    {"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"},
                    {"name": "cost_norm", "metric": "context_value", "key": "cost_norm", "default": 0.0},
                ],
                "study_parameters": ["p1"],
                "study_objectives": [
                    {"name": "edep_sum", "metric": "sim_metric", "key": "edep_sum", "direction": "maximize"},
                    {"name": "p1_cost", "metric": "parameter_value", "parameter": "p1", "direction": "minimize"},
                    {"name": "score", "metric": "formula", "expression": "0.8*edep_sum - 0.2*p1_cost", "direction": "maximize"},
                ],
                "run_method": "surrogate_gp",
                "run_budget": 12,
                "run_seed": 9,
            })

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["validation"]["valid"] is True

    build = data["build"]
    assert build["study_upsert_payload"]["name"] == "m6_builder_demo"
    assert len(build["sim_objectives"]) == 2
    assert build["run_sim_loop_payload"]["study_name"] == "m6_builder_demo"
    assert build["run_sim_loop_payload"]["method"] == "surrogate_gp"
    assert build["run_sim_loop_payload"]["budget"] == 12


def test_objective_builder_build_endpoint_invalid_payload():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        with patch("app.get_project_manager_for_session", return_value=pm):
            resp = client.post("/api/objective_builder/build", json={
                "extract_objectives": [
                    {"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"}
                ],
                "study_parameters": ["p1"],
                "study_objectives": [
                    {"name": "score", "metric": "formula", "expression": "0.8*(edep_sum -", "direction": "maximize"}
                ],
            })

    assert resp.status_code == 400
    data = resp.get_json()
    assert data["success"] is False
    assert data["error"] == "Objective builder payload is invalid."
    assert data["validation"]["valid"] is False


def test_objective_builder_upsert_study_endpoint_dry_run_and_apply():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        payload = {
            "study_name": "m6_upsert_demo",
            "study_mode": "random",
            "study_parameters": ["p1"],
            "extract_objectives": [
                {"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"}
            ],
            "study_objectives": [
                {"name": "edep_sum", "metric": "sim_metric", "key": "edep_sum", "direction": "maximize"},
                {"name": "p1_cost", "metric": "parameter_value", "parameter": "p1", "direction": "minimize"},
                {"name": "score", "metric": "formula", "expression": "0.8*edep_sum - 0.2*p1_cost", "direction": "maximize"},
            ],
        }

        with patch("app.get_project_manager_for_session", return_value=pm):
            dry = client.post("/api/objective_builder/upsert_study", json={**payload, "dry_run": True})
            assert dry.status_code == 200
            dry_data = dry.get_json()
            assert dry_data["success"] is True
            assert dry_data["dry_run"] is True
            assert "m6_upsert_demo" not in (pm.current_geometry_state.param_studies or {})

            apply = client.post("/api/objective_builder/upsert_study", json=payload)
            assert apply.status_code == 200
            apply_data = apply.get_json()
            assert apply_data["success"] is True
            assert apply_data["action"] == "created"
            assert apply_data["study_name"] == "m6_upsert_demo"
            assert "m6_upsert_demo" in (pm.current_geometry_state.param_studies or {})


def test_objective_builder_upsert_study_endpoint_rejects_invalid_param_registry_reference():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()

        payload = {
            "study_name": "m6_upsert_bad",
            "study_mode": "random",
            "study_parameters": ["missing_param"],
            "extract_objectives": [
                {"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"}
            ],
            "study_objectives": [
                {"name": "edep_sum", "metric": "sim_metric", "key": "edep_sum", "direction": "maximize"},
                {"name": "score", "metric": "formula", "expression": "edep_sum", "direction": "maximize"},
            ],
        }

        with patch("app.get_project_manager_for_session", return_value=pm):
            resp = client.post("/api/objective_builder/upsert_study", json={**payload, "dry_run": True})

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert "not found in registry" in data["error"]


def test_objective_builder_launch_endpoint_dry_run():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        payload = {
            "study_name": "m6_launch_demo",
            "study_mode": "random",
            "study_parameters": ["p1"],
            "extract_objectives": [
                {"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"}
            ],
            "study_objectives": [
                {"name": "edep_sum", "metric": "sim_metric", "key": "edep_sum", "direction": "maximize"},
                {"name": "p1_cost", "metric": "parameter_value", "parameter": "p1", "direction": "minimize"},
                {"name": "score", "metric": "formula", "expression": "0.8*edep_sum - 0.2*p1_cost", "direction": "maximize"},
            ],
            "run_budget": 12,
            "run_seed": 9,
            "sim_params": {"events": 10, "threads": 1},
            "dry_run": True,
        }

        with patch("app.get_project_manager_for_session", return_value=pm):
            resp = client.post("/api/objective_builder/launch", json=payload)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["dry_run"] is True
    assert data["launched"] is False
    assert data["study_action"] == "would_create"
    assert "m6_launch_demo" not in (pm.current_geometry_state.param_studies or {})


def test_objective_builder_launch_endpoint_run_with_mock_evaluator():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        payload = {
            "study_name": "m6_launch_demo_run",
            "study_mode": "random",
            "study_parameters": ["p1"],
            "extract_objectives": [
                {"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"}
            ],
            "study_objectives": [
                {"name": "edep_sum", "metric": "sim_metric", "key": "edep_sum", "direction": "maximize"},
                {"name": "p1_cost", "metric": "parameter_value", "parameter": "p1", "direction": "minimize"},
                {"name": "score", "metric": "formula", "expression": "0.8*edep_sum - 0.2*p1_cost", "direction": "maximize"},
            ],
            "run_method": "surrogate_gp",
            "run_budget": 8,
            "run_seed": 7,
            "sim_params": {"events": 10, "threads": 1},
            "surrogate": {"warmup_runs": 4, "candidate_pool_size": 64},
        }

        def mock_builder(**kwargs):
            def _evaluator(*, run_record, project_manager, study):
                p1 = float(run_record["values"]["p1"])
                return {"success": True, "sim_metrics": {"edep_sum": 2.0 * p1}, "simulation": {"job_id": "mock"}}
            return _evaluator

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch("app.GEANT4_EXECUTABLE", "/bin/echo"), \
             patch.object(pm, "run_preflight_checks", return_value={"summary": {"can_run": True}}), \
             patch("app._build_simulation_candidate_evaluator", side_effect=mock_builder):
            resp = client.post("/api/objective_builder/launch", json=payload)

    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["launched"] is True
    assert data["study_action"] == "created"
    assert data["optimizer_result"]["simulation_in_loop"] is True
    assert "m6_launch_demo_run" in (pm.current_geometry_state.param_studies or {})


def test_apply_audit_history_and_rollback_endpoint():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("opt_apply_audit", {
            "name": "opt_apply_audit",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 3, "seed": 42},
            "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
        })
        assert study is not None and err is None

        run, err = pm.run_param_optimizer("opt_apply_audit", method="random_search", budget=4, seed=11)
        assert run is not None and err is None
        run_id = run["run_id"]

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch("app.RUN_POLICY_REQUIRE_VERIFY_TOKEN", False), \
             patch("app.RUN_POLICY_REQUIRE_ALLOW_APPLY", True):
            apply_resp = client.post("/api/param_optimizer/replay_best", json={
                "run_id": run_id,
                "apply_to_project": True,
                "allow_apply": True,
            })
            assert apply_resp.status_code == 200
            apply_data = apply_resp.get_json()
            assert apply_data["success"] is True
            assert apply_data.get("apply_audit") is not None

            hist_resp = client.get("/api/param_optimizer/apply_audit_history")
            assert hist_resp.status_code == 200
            hist_data = hist_resp.get_json()
            assert hist_data["success"] is True
            assert len(hist_data["audits"]) >= 1

            rollback_resp = client.post("/api/param_optimizer/rollback_last_apply", json={})
            assert rollback_resp.status_code == 200
            rollback_data = rollback_resp.get_json()
            assert rollback_data["success"] is True
            assert rollback_data.get("rolled_back_audit") is not None
            assert rollback_data["rolled_back_audit"].get("rolled_back") is True


def test_optimizer_run_policy_rejects_wall_time_above_cap():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")
        study, err = pm.upsert_param_study("opt_wall_cap", {
            "name": "opt_wall_cap",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 3, "seed": 42},
            "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
        })
        assert study is not None and err is None

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch.object(app_module, "RUN_POLICY_MAX_WALL_TIME_SECONDS", 120):
            resp = client.post("/api/param_optimizer/run", json={
                "study_name": "opt_wall_cap",
                "method": "random_search",
                "budget": 4,
                "max_wall_time_seconds": 121,
            })
            assert resp.status_code == 400
            data = resp.get_json()
            assert data["success"] is False
            assert data["error"] == "Run policy validation failed."
            assert any("max_wall_time_seconds" in d for d in (data.get("details") or []))


def test_stop_active_run_endpoint_and_status():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()

        with patch("app.get_project_manager_for_session", return_value=pm):
            started, err = pm.start_managed_run(kind="optimizer", max_wall_time_seconds=300, metadata={"study_name": "x"})
            assert started is not None and err is None

            status_resp = client.get("/api/param_optimizer/active_run_status")
            assert status_resp.status_code == 200
            status_data = status_resp.get_json()
            assert status_data["success"] is True
            assert status_data["active"]["status"] == "running"

            stop_resp = client.post("/api/param_optimizer/stop_active_run", json={"reason": "user_requested_stop"})
            assert stop_resp.status_code == 200
            stop_data = stop_resp.get_json()
            assert stop_data["success"] is True
            assert stop_data["active"] is True
            assert stop_data["stop_requested"] is True


def test_optimizer_honors_user_requested_stop_reason():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("opt_stop_reason", {
        "name": "opt_stop_reason",
        "mode": "random",
        "parameters": ["p1"],
        "random": {"samples": 3, "seed": 42},
        "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
    })
    assert study is not None and err is None

    started, err = pm.start_managed_run(kind="optimizer", max_wall_time_seconds=300, metadata={"study_name": "opt_stop_reason"})
    assert started is not None and err is None
    pm.request_stop_managed_run(reason="user_requested_stop")

    result, err = pm.run_param_optimizer("opt_stop_reason", method="random_search", budget=8, seed=9)
    pm.finish_managed_run(status="completed", details={})

    assert err is None
    assert result is not None
    assert result.get("stop_reason") == "user_requested_stop"
    assert int(result.get("evaluations_used", 0)) == 0


def test_apply_audit_diagnostics_endpoint_reports_scope_and_storage():
    app.config["TESTING"] = True
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = os.path.join(tmpdir, "apply_audit_logs.json")

        with app.test_client() as client:
            pm = _make_pm()
            _add_define_param(pm, name="p1")

            study, err = pm.upsert_param_study("opt_apply_diag", {
                "name": "opt_apply_diag",
                "mode": "random",
                "parameters": ["p1"],
                "random": {"samples": 3, "seed": 42},
                "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
            })
            assert study is not None and err is None

            run, err = pm.run_param_optimizer("opt_apply_diag", method="random_search", budget=4, seed=11)
            assert run is not None and err is None
            run_id = run["run_id"]

            with patch("app.get_project_manager_for_session", return_value=pm), \
                 patch("app.RUN_POLICY_REQUIRE_VERIFY_TOKEN", False), \
                 patch("app.RUN_POLICY_REQUIRE_ALLOW_APPLY", True), \
                 patch.object(app_module, "APPLY_AUDIT_STORAGE_FILE", storage_path):

                with app_module.APPLY_AUDIT_LOCK:
                    app_module.APPLY_AUDIT_LOGS.clear()

                apply_resp = client.post("/api/param_optimizer/replay_best", json={
                    "run_id": run_id,
                    "apply_to_project": True,
                    "allow_apply": True,
                })
                assert apply_resp.status_code == 200

                diag_resp = client.get("/api/param_optimizer/apply_audit_diagnostics")
                assert diag_resp.status_code == 200
                diag = diag_resp.get_json()

                assert diag["success"] is True
                assert isinstance(diag.get("project_scope_id"), str) and diag["project_scope_id"]
                assert diag.get("scope_entry_count", 0) >= 1
                assert diag.get("storage", {}).get("path") == storage_path
                assert diag.get("storage", {}).get("exists") is True


def test_rollback_selected_non_latest_audit_is_blocked():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("opt_apply_audit_multi", {
            "name": "opt_apply_audit_multi",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 3, "seed": 42},
            "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
        })
        assert study is not None and err is None

        run, err = pm.run_param_optimizer("opt_apply_audit_multi", method="random_search", budget=4, seed=11)
        assert run is not None and err is None
        run_id = run["run_id"]

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch("app.RUN_POLICY_REQUIRE_VERIFY_TOKEN", False), \
             patch("app.RUN_POLICY_REQUIRE_ALLOW_APPLY", True):
            first = client.post("/api/param_optimizer/replay_best", json={
                "run_id": run_id,
                "apply_to_project": True,
                "allow_apply": True,
            })
            assert first.status_code == 200

            second = client.post("/api/param_optimizer/replay_best", json={
                "run_id": run_id,
                "apply_to_project": True,
                "allow_apply": True,
            })
            assert second.status_code == 200

            hist = client.get("/api/param_optimizer/apply_audit_history")
            hist_data = hist.get_json()
            audits = hist_data.get("audits", [])
            assert len(audits) >= 2
            latest_id = audits[0].get("audit_id")
            older_id = audits[1].get("audit_id")
            assert latest_id and older_id and latest_id != older_id

            blocked = client.post("/api/param_optimizer/rollback_last_apply", json={
                "audit_id": older_id,
            })
            assert blocked.status_code == 400
            blocked_data = blocked.get_json()
            assert blocked_data["success"] is False
            assert "latest unapplied" in blocked_data["error"]
            assert blocked_data.get("latest_unrolled_audit_id") == latest_id


def test_apply_audit_persists_to_disk_scoped_by_project_scope_id():
    app.config["TESTING"] = True
    with tempfile.TemporaryDirectory() as tmpdir:
        storage_path = os.path.join(tmpdir, "apply_audit_logs.json")

        with app.test_client() as client:
            pm = _make_pm()
            _add_define_param(pm, name="p1")

            study, err = pm.upsert_param_study("opt_apply_audit_persist", {
                "name": "opt_apply_audit_persist",
                "mode": "random",
                "parameters": ["p1"],
                "random": {"samples": 3, "seed": 42},
                "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
            })
            assert study is not None and err is None

            run, err = pm.run_param_optimizer("opt_apply_audit_persist", method="random_search", budget=4, seed=11)
            assert run is not None and err is None
            run_id = run["run_id"]

            with patch("app.get_project_manager_for_session", return_value=pm), \
                 patch("app.RUN_POLICY_REQUIRE_VERIFY_TOKEN", False), \
                 patch("app.RUN_POLICY_REQUIRE_ALLOW_APPLY", True), \
                 patch.object(app_module, "APPLY_AUDIT_STORAGE_FILE", storage_path):

                with app_module.APPLY_AUDIT_LOCK:
                    app_module.APPLY_AUDIT_LOGS.clear()

                apply_resp = client.post("/api/param_optimizer/replay_best", json={
                    "run_id": run_id,
                    "apply_to_project": True,
                    "allow_apply": True,
                })
                assert apply_resp.status_code == 200

                assert os.path.exists(storage_path)
                with open(storage_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)

                assert isinstance(payload, dict)
                user_bucket = payload.get("local_user", {})
                assert isinstance(user_bucket, dict)
                scope_id = app_module._project_scope_id_for_policy(pm)
                entries = user_bucket.get(scope_id, [])
                assert isinstance(entries, list)
                assert len(entries) >= 1
                assert entries[-1].get("run_id") == run_id


def test_surrogate_optimizer_backend_runs_and_logs_provenance():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("opt_surrogate", {
        "name": "opt_surrogate",
        "mode": "random",
        "parameters": ["p1"],
        "random": {"samples": 8, "seed": 11},
        "objectives": [{"metric": "parameter_value", "name": "p1_value", "parameter": "p1", "direction": "maximize"}],
    })
    assert study is not None and err is None

    result, err = pm.run_surrogate_param_optimizer(
        study_name="opt_surrogate",
        budget=14,
        seed=5,
        objective_name="p1_value",
        direction="maximize",
        warmup_runs=4,
        candidate_pool_size=64,
        exploration_beta=1.0,
    )

    assert err is None
    assert result["method"] == "surrogate_gp"
    assert result["budget"] == 14
    assert len(result["candidates"]) == 14
    assert result["surrogate"]["model_updates"] >= 1
    assert any(c.get("proposal_source") == "surrogate_ucb" for c in result["candidates"])


def test_surrogate_optimizer_api_route():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("opt_surrogate_api", {
            "name": "opt_surrogate_api",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 8, "seed": 11},
            "objectives": [{"metric": "parameter_value", "name": "p1_value", "parameter": "p1", "direction": "maximize"}],
        })
        assert study is not None and err is None

        with patch("app.get_project_manager_for_session", return_value=pm):
            resp = client.post("/api/param_optimizer/run_surrogate", json={
                "study_name": "opt_surrogate_api",
                "budget": 12,
                "seed": 7,
                "objective_name": "p1_value",
                "direction": "maximize",
                "warmup_runs": 4,
                "candidate_pool_size": 64,
            })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["optimizer_result"]["method"] == "surrogate_gp"
        assert len(data["optimizer_result"]["candidates"]) == 12


def test_optimizer_head_to_head_backend():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("opt_h2h", {
        "name": "opt_h2h",
        "mode": "random",
        "parameters": ["p1"],
        "random": {"samples": 8, "seed": 11},
        "objectives": [{"metric": "parameter_value", "name": "p1_value", "parameter": "p1", "direction": "maximize"}],
    })
    assert study is not None and err is None

    comparison, err = pm.run_optimizer_head_to_head(
        study_name="opt_h2h",
        budget=12,
        seed=3,
        objective_name="p1_value",
        direction="maximize",
        classical_method="random_search",
        surrogate_config={"warmup_runs": 4, "candidate_pool_size": 64},
    )

    assert err is None
    assert comparison["study_name"] == "opt_h2h"
    assert comparison["classical"]["method"] == "random_search"
    assert comparison["classical"]["run_id"] is not None
    assert comparison["surrogate"]["run_id"] is not None
    assert comparison["comparison"]["winner"] in {"classical", "surrogate", "tie", "undetermined"}


def test_optimizer_head_to_head_api_route():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("opt_h2h_api", {
            "name": "opt_h2h_api",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 8, "seed": 11},
            "objectives": [{"metric": "parameter_value", "name": "p1_value", "parameter": "p1", "direction": "maximize"}],
        })
        assert study is not None and err is None

        with patch("app.get_project_manager_for_session", return_value=pm):
            resp = client.post("/api/param_optimizer/head_to_head", json={
                "study_name": "opt_h2h_api",
                "budget": 10,
                "seed": 7,
                "objective_name": "p1_value",
                "direction": "maximize",
                "classical_method": "random_search",
                "surrogate": {"warmup_runs": 4, "candidate_pool_size": 64},
            })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        cmpd = data["comparison"]
        assert cmpd["classical"]["method"] == "random_search"
        assert cmpd["classical"]["run_id"] is not None
        assert cmpd["surrogate"]["run_id"] is not None


def test_simulation_in_loop_optimizer_backend_with_mock_evaluator():
    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("sim_loop_mock", {
        "name": "sim_loop_mock",
        "mode": "random",
        "parameters": ["p1"],
        "random": {"samples": 8, "seed": 11},
        "objectives": [
            {"metric": "sim_metric", "name": "edep", "key": "edep_sum", "direction": "maximize"},
            {"metric": "parameter_value", "name": "p1v", "parameter": "p1", "direction": "minimize"},
            {"metric": "formula", "name": "score", "expression": "0.8*edep - 0.2*p1v", "direction": "maximize"},
        ],
    })
    assert study is not None and err is None

    def mock_evaluator(*, run_record, project_manager, study):
        p1 = float(run_record["values"]["p1"])
        return {
            "success": True,
            "sim_metrics": {"edep_sum": 2.0 * p1},
            "simulation": {"job_id": f"mock_{run_record['run_index']}"},
        }

    result, err = pm.run_simulation_in_loop_optimizer(
        study_name="sim_loop_mock",
        method="surrogate_gp",
        budget=10,
        seed=7,
        objective_name="score",
        direction="maximize",
        surrogate_config={"warmup_runs": 4, "candidate_pool_size": 64},
        evaluator=mock_evaluator,
    )

    assert err is None
    assert result["simulation_in_loop"] is True
    assert result["method"] == "surrogate_gp"
    assert len(result["candidates"]) == 10
    assert all("sim_metrics" in c for c in result["candidates"])


def test_simulation_in_loop_optimizer_api_route_with_mock_evaluator():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("sim_loop_api", {
            "name": "sim_loop_api",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 8, "seed": 11},
            "objectives": [
                {"metric": "sim_metric", "name": "edep", "key": "edep_sum", "direction": "maximize"},
                {"metric": "parameter_value", "name": "p1v", "parameter": "p1", "direction": "minimize"},
                {"metric": "formula", "name": "score", "expression": "0.8*edep - 0.2*p1v", "direction": "maximize"},
            ],
        })
        assert study is not None and err is None

        def mock_builder(**kwargs):
            def _evaluator(*, run_record, project_manager, study):
                p1 = float(run_record["values"]["p1"])
                return {"success": True, "sim_metrics": {"edep_sum": 2.0 * p1}, "simulation": {"job_id": "mock"}}
            return _evaluator

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch("app.GEANT4_EXECUTABLE", "/bin/echo"), \
             patch.object(pm, "run_preflight_checks", return_value={"summary": {"can_run": True}}), \
             patch("app._build_simulation_candidate_evaluator", side_effect=mock_builder):
            resp = client.post("/api/param_optimizer/run_simulation_in_loop", json={
                "study_name": "sim_loop_api",
                "method": "surrogate_gp",
                "budget": 8,
                "seed": 7,
                "objective_name": "score",
                "direction": "maximize",
                "sim_params": {"events": 10, "threads": 1},
                "sim_objectives": [{"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"}],
                "surrogate": {"warmup_runs": 4, "candidate_pool_size": 64},
            })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["optimizer_result"]["simulation_in_loop"] is True
        assert data["optimizer_result"]["method"] == "surrogate_gp"


def test_simulation_in_loop_head_to_head_api_route_with_mock_evaluator():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("sim_loop_h2h_api", {
            "name": "sim_loop_h2h_api",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 8, "seed": 11},
            "objectives": [
                {"metric": "sim_metric", "name": "edep", "key": "edep_sum", "direction": "maximize"},
                {"metric": "parameter_value", "name": "p1v", "parameter": "p1", "direction": "minimize"},
                {"metric": "formula", "name": "score", "expression": "0.8*edep - 0.2*p1v", "direction": "maximize"},
            ],
        })
        assert study is not None and err is None

        def mock_builder(**kwargs):
            def _evaluator(*, run_record, project_manager, study):
                p1 = float(run_record["values"]["p1"])
                return {"success": True, "sim_metrics": {"edep_sum": 2.0 * p1}, "simulation": {"job_id": "mock"}}
            return _evaluator

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch("app.GEANT4_EXECUTABLE", "/bin/echo"), \
             patch.object(pm, "run_preflight_checks", return_value={"summary": {"can_run": True}}), \
             patch("app._build_simulation_candidate_evaluator", side_effect=mock_builder):
            resp = client.post("/api/param_optimizer/head_to_head_simulation_in_loop", json={
                "study_name": "sim_loop_h2h_api",
                "budget": 8,
                "seed": 7,
                "objective_name": "score",
                "direction": "maximize",
                "classical_method": "random_search",
                "sim_params": {"events": 10, "threads": 1},
                "sim_objectives": [{"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"}],
                "surrogate": {"warmup_runs": 4, "candidate_pool_size": 64},
            })

        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["comparison"]["simulation_in_loop"] is True


def test_simulation_in_loop_run_policy_rejects_budget_over_cap():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("sim_loop_policy_budget", {
            "name": "sim_loop_policy_budget",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 8, "seed": 11},
            "objectives": [
                {"metric": "sim_metric", "name": "edep", "key": "edep_sum", "direction": "maximize"},
                {"metric": "parameter_value", "name": "p1v", "parameter": "p1", "direction": "minimize"},
                {"metric": "formula", "name": "score", "expression": "0.8*edep - 0.2*p1v", "direction": "maximize"},
            ],
        })
        assert study is not None and err is None

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch("app.GEANT4_EXECUTABLE", "/bin/echo"), \
             patch("app.RUN_POLICY_MAX_BUDGET", 5):
            resp = client.post("/api/param_optimizer/run_simulation_in_loop", json={
                "study_name": "sim_loop_policy_budget",
                "method": "surrogate_gp",
                "budget": 6,
                "seed": 7,
                "objective_name": "score",
                "direction": "maximize",
                "sim_params": {"events": 10, "threads": 1},
                "sim_objectives": [{"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"}],
            })

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert data["error"] == "Run policy validation failed."
        assert any("max_budget" in msg for msg in data["details"])
        assert data["limits"]["max_budget"] == 5


def test_head_to_head_simulation_in_loop_run_policy_rejects_total_events():
    app.config["TESTING"] = True
    with app.test_client() as client:
        pm = _make_pm()
        _add_define_param(pm, name="p1")

        study, err = pm.upsert_param_study("sim_loop_policy_total", {
            "name": "sim_loop_policy_total",
            "mode": "random",
            "parameters": ["p1"],
            "random": {"samples": 8, "seed": 11},
            "objectives": [
                {"metric": "sim_metric", "name": "edep", "key": "edep_sum", "direction": "maximize"},
                {"metric": "parameter_value", "name": "p1v", "parameter": "p1", "direction": "minimize"},
                {"metric": "formula", "name": "score", "expression": "0.8*edep - 0.2*p1v", "direction": "maximize"},
            ],
        })
        assert study is not None and err is None

        with patch("app.get_project_manager_for_session", return_value=pm), \
             patch("app.GEANT4_EXECUTABLE", "/bin/echo"), \
             patch("app.RUN_POLICY_MAX_TOTAL_EVENTS", 50):
            resp = client.post("/api/param_optimizer/head_to_head_simulation_in_loop", json={
                "study_name": "sim_loop_policy_total",
                "budget": 10,
                "seed": 7,
                "objective_name": "score",
                "direction": "maximize",
                "classical_method": "random_search",
                "sim_params": {"events": 3, "threads": 1},
                "sim_objectives": [{"name": "edep_sum", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"}],
            })

        assert resp.status_code == 400
        data = resp.get_json()
        assert data["success"] is False
        assert data["error"] == "Run policy validation failed."
        assert any("effective_total_events" in msg for msg in data["details"])
        assert data["limits"]["max_total_events"] == 50


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
                            {"name": "edep_sum_path", "metric": "hdf5_reduce", "dataset_path": "default_ntuples/Hits/Edep", "reduce": "sum"},
                            {"name": "cost_norm", "metric": "context_value", "key": "cost_norm"},
                            {"name": "score", "metric": "formula", "expression": "0.5*edep_sum_path - cost_norm"},
                            {"name": "gamma_frac", "metric": "particle_fraction", "particle": "gamma"},
                        ],
                        "context": {
                            "cost_norm": 1.25
                        }
                    },
                )

            assert resp.status_code == 200
            data = resp.get_json()
            assert data["success"] is True
            assert data["objective_values"]["hits"] == 3.0
            assert data["objective_values"]["edep_sum"] == 6.0
            assert data["objective_values"]["edep_sum_path"] == 6.0
            assert data["objective_values"]["cost_norm"] == 1.25
            assert data["objective_values"]["score"] == 1.75
            assert data["objective_values"]["gamma_frac"] == 2.0 / 3.0
            assert "hdf5_reduce" in data["available_metrics"]
            assert "formula" in data["available_metrics"]
            assert "warnings" in data
