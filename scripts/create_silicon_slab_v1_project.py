#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _must(ok_or_obj, err, context):
    if err:
        raise RuntimeError(f"{context}: {err}")
    return ok_or_obj


def create_silicon_slab_v1_project(output_path: Path) -> dict:
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()

    # Material: Silicon (self-contained; no external material DB assumptions).
    silicon_mat = _must(
        *pm.add_material("Silicon", {
            "Z_expr": "14",
            "A_expr": "28.085",
            "density_expr": "2.33",
            "state": "solid",
        }),
        context="add_material",
    )

    # Geometry: a single slab in front of the default world center.
    thickness_define = _must(
        *pm.add_define("si_thickness_mm", "constant", "1.0", "mm", "geometry"),
        context="add_define",
    )

    slab_solid = _must(
        *pm.add_solid("si_slab_solid", "box", {
            "x": "25.0",
            "y": "25.0",
            "z": thickness_define["name"],
        }),
        context="add_solid",
    )

    slab_lv = _must(
        *pm.add_logical_volume(
            "si_slab_lv",
            slab_solid["name"],
            silicon_mat["name"],
            is_sensitive=True,
        ),
        context="add_logical_volume",
    )

    _must(
        *pm.add_physical_volume(
            "World",
            "si_slab_pv",
            slab_lv["name"],
            {"x": "0", "y": "0", "z": "0"},
            {"x": "0", "y": "0", "z": "0"},
            {"x": "1", "y": "1", "z": "1"},
        ),
        context="add_physical_volume",
    )

    # Optimization parameter: slab thickness in mm.
    _must(
        *pm.upsert_parameter_registry_entry("si_thickness", {
            "name": "si_thickness",
            "target_type": "define",
            "target_ref": {"name": thickness_define["name"]},
            "bounds": {"min": 0.05, "max": 6.0},
            "default": 1.0,
            "units": "mm",
            "enabled": True,
        }),
        context="upsert_parameter_registry_entry",
    )

    # Silicon Slab v1 objective family:
    # score = w_edep * (1 - exp(-t / attenuation_len)) - w_cost * (t / ref_thickness)
    # This is a fast stand-in objective to prototype optimizer/surrogate behavior.
    _must(
        *pm.upsert_param_study("silicon_slab_v1", {
            "name": "silicon_slab_v1",
            "mode": "random",
            "parameters": ["si_thickness"],
            "random": {"samples": 60, "seed": 42},
            "objectives": [
                {
                    "metric": "silicon_slab_tradeoff",
                    "name": "score",
                    "direction": "maximize",
                    "thickness_parameter": "si_thickness",
                    "attenuation_length_mm": 1.5,
                    "reference_thickness_mm": 3.0,
                    "w_edep": 0.8,
                    "w_cost": 0.2,
                },
                {
                    "metric": "silicon_slab_edep_fraction",
                    "name": "edep_fraction",
                    "direction": "maximize",
                    "thickness_parameter": "si_thickness",
                    "attenuation_length_mm": 1.5,
                },
                {
                    "metric": "silicon_slab_cost_norm",
                    "name": "cost_norm",
                    "direction": "minimize",
                    "thickness_parameter": "si_thickness",
                    "reference_thickness_mm": 3.0,
                },
            ],
        }),
        context="upsert_param_study",
    )

    # Silicon Slab v1.1 objective schema (simulation-backed path + formula composition).
    # Note: this study expects run_record['sim_metrics'] to be populated by a simulation runner.
    _must(
        *pm.upsert_param_study("silicon_slab_v1_1", {
            "name": "silicon_slab_v1_1",
            "mode": "random",
            "parameters": ["si_thickness"],
            "random": {"samples": 60, "seed": 42},
            "objectives": [
                {"metric": "sim_metric", "name": "edep_sum", "key": "edep_sum", "direction": "maximize"},
                {"metric": "parameter_value", "name": "thickness_mm", "parameter": "si_thickness", "direction": "minimize"},
                {"metric": "formula", "name": "score", "direction": "maximize", "expression": "0.8*edep_sum - 0.2*thickness_mm"},
            ],
        }),
        context="upsert_param_study(v1_1)",
    )

    payload = pm.save_project_to_json_string()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload, encoding="utf-8")

    objectives_v11 = [
        {
            "name": "edep_sum",
            "metric": "hdf5_reduce",
            "dataset_path": "default_ntuples/Hits/Edep",
            "reduce": "sum"
        },
        {
            "name": "cost_norm",
            "metric": "context_value",
            "key": "cost_norm",
            "default": 0.0
        },
        {
            "name": "score",
            "metric": "formula",
            "expression": "0.8*edep_sum - 0.2*cost_norm"
        }
    ]
    objective_spec_path = output_path.parent / "silicon_slab_v1_1_objectives.json"
    objective_spec_path.write_text(json.dumps(objectives_v11, indent=2), encoding="utf-8")

    return {
        "project_json": str(output_path),
        "study_name": "silicon_slab_v1",
        "study_name_v11": "silicon_slab_v1_1",
        "objective_spec_v11": str(objective_spec_path),
        "notes": {
            "objective": "score = 0.8*edep_fraction - 0.2*cost_norm",
            "edep_fraction_model": "1 - exp(-thickness_mm / attenuation_length_mm)",
            "cost_model": "thickness_mm / reference_thickness_mm",
            "v11": "Uses sim_metric + formula path; objective spec provided for /api/objectives/extract context/formula flow.",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a self-contained Silicon Slab v1 optimization project JSON.")
    parser.add_argument(
        "--output",
        default="surrogate/benchmarks/silicon_slab_v1/project.json",
        help="Output project JSON path.",
    )
    args = parser.parse_args()

    summary = create_silicon_slab_v1_project(Path(args.output).expanduser().resolve())
    print(json.dumps({
        "success": True,
        **summary,
        "next": [
            f"python scripts/run_optimizer_head_to_head.py --project-json {summary['project_json']} --study-name {summary['study_name']} --budget 40 --classical-method cmaes --objective-name score --direction maximize",
            f"python scripts/run_optimizer_head_to_head.py --project-json {summary['project_json']} --study-name {summary['study_name']} --budget 40 --classical-method random_search --objective-name score --direction maximize",
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
