from pathlib import Path

from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _load_silicon_detector_starter_pm():
    pm = ProjectManager(ExpressionEvaluator())
    starter_path = Path(__file__).resolve().parents[1] / "examples" / "silicon_detector" / "silicon_optimizer_starter.project.json"
    with starter_path.open("r", encoding="utf-8") as handle:
        pm.load_project_from_json_string(handle.read())
    return pm


def test_silicon_detector_first_run_starter_project_launch_is_deterministic():
    pm = _load_silicon_detector_starter_pm()

    studies = pm.list_param_studies()
    assert "si_first_run" in studies
    study = studies["si_first_run"]
    assert study["mode"] == "random"
    assert study["parameters"] == ["si_thickness", "src_z"]
    assert study["random"] == {"samples": 16, "seed": 42}
    assert [obj["name"] for obj in study["objectives"]] == ["edep_sum", "score"]

    selected_source_ids = list(pm.current_geometry_state.active_source_ids or [])
    assert selected_source_ids, "Starter project should expose an active source for the launch path."
    assert study["simulation_source_ids"] == selected_source_ids

    def mock_evaluator(*, run_record, project_manager, study):
        thickness = float(run_record["values"]["si_thickness"])
        source_z = abs(float(run_record["values"]["src_z"]))
        edep_sum = round(100.0 - 10.0 * thickness - source_z, 6)
        return {
            "success": True,
            "sim_metrics": {"edep_sum": edep_sum},
            "simulation": {"job_id": f"mock_{run_record['run_index']}"},
        }

    result1, err1 = pm.run_simulation_in_loop_optimizer(
        study_name="si_first_run",
        method="surrogate_gp",
        budget=16,
        seed=42,
        objective_name="score",
        direction="maximize",
        surrogate_config={"warmup_runs": 4, "candidate_pool_size": 64, "exploration_beta": 1.0},
        evaluator=mock_evaluator,
    )
    assert err1 is None
    assert result1["simulation_in_loop"] is True
    assert result1["method"] == "surrogate_gp"
    assert result1["objective"]["name"] == "score"
    assert result1["evaluations_used"] == 16
    assert len(result1["candidates"]) == 16

    pm_repeat = _load_silicon_detector_starter_pm()
    result2, err2 = pm_repeat.run_simulation_in_loop_optimizer(
        study_name="si_first_run",
        method="surrogate_gp",
        budget=16,
        seed=42,
        objective_name="score",
        direction="maximize",
        surrogate_config={"warmup_runs": 4, "candidate_pool_size": 64, "exploration_beta": 1.0},
        evaluator=mock_evaluator,
    )
    assert err2 is None

    candidate_values_1 = [candidate["values"] for candidate in result1["candidates"]]
    candidate_values_2 = [candidate["values"] for candidate in result2["candidates"]]
    assert candidate_values_1 == candidate_values_2

    candidate_scores_1 = [candidate["objectives"]["score"] for candidate in result1["candidates"]]
    candidate_scores_2 = [candidate["objectives"]["score"] for candidate in result2["candidates"]]
    assert candidate_scores_1 == candidate_scores_2
    assert all(candidate["objectives"]["score"] == candidate["objectives"]["edep_sum"] for candidate in result1["candidates"])

    best_run = result1["best_run"]
    assert best_run["objectives"]["score"] == best_run["objectives"]["edep_sum"]
    assert set(best_run["values"].keys()) == {"si_thickness", "src_z"}
    assert best_run["simulation"]["job_id"].startswith("mock_")
    assert pm.current_geometry_state.param_studies["si_first_run"]["random"] == {"samples": 16, "seed": 42}
    assert list(pm.current_geometry_state.active_source_ids or []) == selected_source_ids
