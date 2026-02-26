import json

import numpy as np
import pandas as pd

from src.surrogate_experiment import run_surrogate_experiment, run_surrogate_experiment_from_path


def _make_linear_dataset(tmp_path):
    rng = np.random.default_rng(123)

    x_train = np.linspace(-1.0, 1.0, 60)
    y_train = 2.5 * x_train + 0.2
    x_train = x_train + rng.normal(0.0, 0.01, size=x_train.shape)

    x_val = np.linspace(-0.9, 0.9, 20)
    y_val = 2.5 * x_val + 0.2

    train_df = pd.DataFrame({
        "param__p1": x_train,
        "objective__score": y_train,
        "target_value": y_train,
        "split": "train",
    })
    val_df = pd.DataFrame({
        "param__p1": x_val,
        "objective__score": y_val,
        "target_value": y_val,
        "split": "val",
    })

    ds_dir = tmp_path / "dataset"
    ds_dir.mkdir(parents=True)
    train_csv = ds_dir / "train.csv"
    val_csv = ds_dir / "val.csv"
    train_df.to_csv(train_csv, index=False)
    val_df.to_csv(val_csv, index=False)

    manifest = {
        "target_objective": "score",
        "outputs": {
            "train_csv": str(train_csv),
            "val_csv": str(val_csv),
            "dataset_csv": str(ds_dir / "dataset.csv"),
        },
    }
    manifest_path = ds_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    return manifest_path


def test_run_surrogate_experiment_gp(tmp_path):
    manifest_path = _make_linear_dataset(tmp_path)

    config = {
        "experiment_name": "gp_unit",
        "dataset": {
            "manifest": str(manifest_path),
        },
        "model": {
            "type": "gp",
            "gp": {
                "noise": 1e-6,
            },
        },
        "features": {
            "input_params": ["p1"],
            "target_objective": "score",
            "feature_scaling": {"enabled": True, "method": "standard"},
        },
        "training": {"seed": 7},
        "output": {"root": str(tmp_path / "experiments")},
    }

    report = run_surrogate_experiment(config=config, config_dir=tmp_path)
    assert report["success"] is True
    assert report["metrics"]["rmse"] < 0.1


def test_run_surrogate_experiment_mlp_from_config_path(tmp_path):
    manifest_path = _make_linear_dataset(tmp_path)

    config = {
        "experiment_name": "mlp_unit",
        "dataset": {
            "manifest": str(manifest_path),
        },
        "model": {
            "type": "mlp",
            "mlp": {
                "hidden_size": 12,
                "epochs": 600,
                "learning_rate": 0.03,
            },
        },
        "features": {
            "input_params": ["p1"],
            "target_objective": "score",
            "feature_scaling": {"enabled": True, "method": "standard"},
        },
        "training": {"seed": 123},
        "output": {"root": str(tmp_path / "experiments")},
    }

    config_path = tmp_path / "exp.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    report = run_surrogate_experiment_from_path(str(config_path))
    assert report["success"] is True
    assert report["metrics"]["rmse"] < 0.25
    assert (tmp_path / "experiments" / "mlp_unit" / "report.json").exists()
