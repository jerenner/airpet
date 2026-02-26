from pathlib import Path

from src.surrogate_synthetic import generate_synthetic_surrogate_benchmark


def test_generate_synthetic_surrogate_benchmark_outputs(tmp_path):
    report = generate_synthetic_surrogate_benchmark(
        preset="nonlinear_3d",
        n_runs=120,
        seed=9,
        noise_sigma=0.03,
        failure_probability=0.1,
        dataset_output_root=str(tmp_path / "datasets"),
        artifacts_root=str(tmp_path / "benchmarks"),
        dataset_name="synthetic_unit",
        target_objective="score",
        val_ratio=0.25,
        split_seed=3,
        only_success=False,
        write_example_configs=True,
    )

    assert report["success"] is True
    assert report["dataset_name"] == "synthetic_unit"
    assert report["dataset_counts"]["rows_total"] == 120
    assert Path(report["dataset_manifest"]).exists()
    assert Path(report["synthetic_payload"]).exists()
    assert Path(report["report_path"]).exists()
    assert len(report["generated_experiment_configs"]) == 2
    for cfg in report["generated_experiment_configs"]:
        assert Path(cfg).exists()


def test_generate_synthetic_surrogate_benchmark_only_success_filter(tmp_path):
    report = generate_synthetic_surrogate_benchmark(
        preset="linear_2d",
        n_runs=80,
        seed=2,
        noise_sigma=0.01,
        failure_probability=0.5,
        dataset_output_root=str(tmp_path / "datasets"),
        artifacts_root=str(tmp_path / "benchmarks"),
        dataset_name="synthetic_success_only",
        target_objective="score",
        val_ratio=0.2,
        split_seed=12,
        only_success=True,
        write_example_configs=False,
    )

    assert report["success"] is True
    # By construction, rows are filtered to successes only.
    assert report["dataset_counts"]["rows_failed"] == 0
    assert report["dataset_counts"]["rows_total"] > 0
