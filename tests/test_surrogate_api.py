import json
from unittest.mock import patch

import pandas as pd

from app import app
from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _make_pm():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


def _add_define_param(pm, name="p1"):
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


def test_surrogate_dataset_export_api(tmp_path):
    app.config["TESTING"] = True

    pm = _make_pm()
    _add_define_param(pm, name="p1")

    study, err = pm.upsert_param_study("opt_api_surrogate", {
        "name": "opt_api_surrogate",
        "mode": "random",
        "parameters": ["p1"],
        "random": {"samples": 5, "seed": 42},
        "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
    })
    assert study is not None and err is None

    result, err = pm.run_param_optimizer("opt_api_surrogate", budget=6, seed=3)
    assert result is not None and err is None

    with app.test_client() as client, patch("app.get_project_manager_for_session", return_value=pm):
        resp = client.post("/api/surrogate/dataset/export", json={
            "output_root": str(tmp_path / "datasets"),
            "dataset_name": "api_ds",
            "target_objective": "success",
            "val_ratio": 0.3,
            "split_seed": 11,
        })

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True

    manifest = payload["manifest"]
    assert manifest["dataset_name"] == "api_ds"
    assert manifest["counts"]["rows_total"] >= 1
    assert (tmp_path / "datasets" / "api_ds" / "dataset.csv").exists()


def test_surrogate_experiment_run_api_inline_config(tmp_path):
    app.config["TESTING"] = True

    train_df = pd.DataFrame({
        "param__p1": [0.0, 1.0, 2.0, 3.0],
        "target_value": [1.0, 3.0, 5.0, 7.0],
    })
    val_df = pd.DataFrame({
        "param__p1": [0.5, 1.5, 2.5],
        "target_value": [2.0, 4.0, 6.0],
    })

    ds_dir = tmp_path / "ds"
    ds_dir.mkdir(parents=True)
    train_path = ds_dir / "train.csv"
    val_path = ds_dir / "val.csv"
    train_df.to_csv(train_path, index=False)
    val_df.to_csv(val_path, index=False)

    config = {
        "experiment_name": "api_exp",
        "dataset": {
            "train_csv": str(train_path),
            "val_csv": str(val_path),
        },
        "model": {"type": "gp"},
        "features": {
            "input_params": ["p1"],
            "feature_scaling": {"enabled": True, "method": "standard"},
        },
        "output": {"root": str(tmp_path / "exp_out")},
    }

    with app.test_client() as client:
        resp = client.post("/api/surrogate/experiment/run", json={"config": config})

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    assert payload["report"]["experiment_name"] == "api_exp"
    assert (tmp_path / "exp_out" / "api_exp" / "report.json").exists()


def test_surrogate_synthetic_generate_api(tmp_path):
    app.config["TESTING"] = True

    with app.test_client() as client:
        resp = client.post("/api/surrogate/synthetic/generate", json={
            "preset": "linear_2d",
            "runs": 60,
            "seed": 5,
            "dataset_output_root": str(tmp_path / "datasets"),
            "artifacts_root": str(tmp_path / "benchmarks"),
            "dataset_name": "api_synth",
            "noise_sigma": 0.02,
            "failure_probability": 0.15,
            "val_ratio": 0.2,
            "split_seed": 17,
        })

    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["success"] is True
    bench = payload["benchmark"]
    assert bench["dataset_name"] == "api_synth"
    assert bench["dataset_counts"]["rows_total"] == 60
