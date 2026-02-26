import csv
import json

from src.surrogate_dataset import build_surrogate_dataset


def test_build_surrogate_dataset_from_version_optimizer_runs(tmp_path):
    version_payload = {
        "optimizer_runs": {
            "opt_1": {
                "run_id": "opt_1",
                "study_name": "study_alpha",
                "method": "random_search",
                "seed": 7,
                "created_at": "2026-02-24T10:00:00Z",
                "objective": {"name": "objective_main", "direction": "maximize"},
                "candidates": [
                    {
                        "run_index": 0,
                        "values": {"p1": 1.5, "p2": 2.0},
                        "success": True,
                        "error": None,
                        "objectives": {"objective_main": 0.9, "aux_metric": 4.2},
                    },
                    {
                        "run_index": 1,
                        "values": {"p1": 2.5, "p2": 3.0},
                        "success": False,
                        "error": "geometry failed",
                        "objectives": {"objective_main": 0.1, "aux_metric": 1.0},
                    },
                ],
            }
        }
    }

    inputs_dir = tmp_path / "inputs"
    inputs_dir.mkdir(parents=True)
    (inputs_dir / "version.json").write_text(json.dumps(version_payload), encoding="utf-8")

    manifest = build_surrogate_dataset(
        input_paths=[str(inputs_dir)],
        output_root=str(tmp_path / "surrogate_datasets"),
        dataset_name="unit_ds",
        target_objective="objective_main",
        val_ratio=0.5,
        split_seed=11,
    )

    assert manifest["dataset_name"] == "unit_ds"
    assert manifest["target_objective"] == "objective_main"
    assert manifest["counts"]["rows_total"] == 2
    assert manifest["counts"]["rows_train"] == 1
    assert manifest["counts"]["rows_val"] == 1
    assert manifest["source_run_ids"] == ["opt_1"]

    dataset_csv = tmp_path / "surrogate_datasets" / "unit_ds" / "dataset.csv"
    assert dataset_csv.exists()

    with dataset_csv.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 2
    assert "param__p1" in reader.fieldnames
    assert "param__p2" in reader.fieldnames
    assert "objective__aux_metric" in reader.fieldnames
    assert "target_value" in reader.fieldnames


def test_build_surrogate_dataset_from_study_result_wrapper(tmp_path):
    study_payload = {
        "study_result": {
            "study_name": "grid_demo",
            "requested_runs": 2,
            "runs": [
                {
                    "run_index": 0,
                    "values": {"p1": 0.0},
                    "success": True,
                    "error": None,
                    "objectives": {"score": 1.0},
                },
                {
                    "run_index": 1,
                    "values": {"p1": 1.0},
                    "success": True,
                    "error": None,
                    "objectives": {"score": 2.0},
                },
            ],
        }
    }

    study_file = tmp_path / "study_result.json"
    study_file.write_text(json.dumps(study_payload), encoding="utf-8")

    manifest = build_surrogate_dataset(
        input_paths=[str(study_file)],
        output_root=str(tmp_path / "surrogate_datasets"),
        dataset_name="study_ds",
        val_ratio=0.0,
        split_seed=1,
    )

    assert manifest["target_objective"] == "score"
    assert manifest["counts"]["rows_total"] == 2
    assert manifest["counts"]["rows_val"] == 0
    assert manifest["counts"]["rows_train"] == 2
    assert len(manifest["source_run_ids"]) == 1
