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


def create_silicon_slab_v2_project(output_path: Path) -> dict:
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()

    silicon_mat = _must(
        *pm.add_material("Silicon", {
            "Z_expr": "14",
            "A_expr": "28.085",
            "density_expr": "2.33",
            "state": "solid",
        }),
        context="add_material",
    )

    thickness_define = _must(
        *pm.add_define("si_thickness_mm", "constant", "1.0", "mm", "geometry"),
        context="add_define(thickness)",
    )
    half_xy_define = _must(
        *pm.add_define("si_half_xy_mm", "constant", "12.5", "mm", "geometry"),
        context="add_define(half_xy)",
    )

    slab_solid = _must(
        *pm.add_solid("si_slab_solid", "box", {
            "x": half_xy_define["name"],
            "y": half_xy_define["name"],
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

    # Add a default active source so sim-loop runs are plug-and-play.
    source, err = pm.add_source(
        "src_electron",
        {
            "particle": "e-",
            "ene/type": "Mono",
            "ene/mono": "1000",  # keV
            "ang/type": "iso",
            "pos/type": "Point",
        },
        {"x": 0, "y": 0, "z": -20},
        {"x": 0, "y": 0, "z": 0},
        activity=1.0,
    )
    source = _must(source, err, "add_source")
    pm.current_geometry_state.active_source_ids = [source["id"]]

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
        context="upsert_parameter_registry_entry(thickness)",
    )

    _must(
        *pm.upsert_parameter_registry_entry("si_half_xy", {
            "name": "si_half_xy",
            "target_type": "define",
            "target_ref": {"name": half_xy_define["name"]},
            "bounds": {"min": 5.0, "max": 40.0},
            "default": 12.5,
            "units": "mm",
            "enabled": True,
        }),
        context="upsert_parameter_registry_entry(half_xy)",
    )

    # 2-parameter simulation-backed objective composition:
    # score = 0.8*edep_sum - 0.2*cost_norm
    # cost_norm = (thickness_mm/3.0) * (half_xy_mm/12.5)^2
    _must(
        *pm.upsert_param_study("silicon_slab_v2_1", {
            "name": "silicon_slab_v2_1",
            "mode": "random",
            "parameters": ["si_thickness", "si_half_xy"],
            "random": {"samples": 80, "seed": 42},
            "objectives": [
                {"metric": "sim_metric", "name": "edep_sum", "key": "edep_sum", "direction": "maximize"},
                {"metric": "parameter_value", "name": "thickness_mm", "parameter": "si_thickness", "direction": "minimize"},
                {"metric": "parameter_value", "name": "half_xy_mm", "parameter": "si_half_xy", "direction": "minimize"},
                {"metric": "formula", "name": "cost_norm", "direction": "minimize", "expression": "(thickness_mm/3.0) * (half_xy_mm/12.5)**2"},
                {"metric": "formula", "name": "score", "direction": "maximize", "expression": "0.8*edep_sum - 0.2*cost_norm"},
            ],
        }),
        context="upsert_param_study(v2_1)",
    )

    payload = pm.save_project_to_json_string()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(payload, encoding="utf-8")

    sim_objectives = [
        {
            "name": "edep_sum",
            "metric": "hdf5_reduce",
            "dataset_path": "default_ntuples/Hits/Edep",
            "reduce": "sum",
        }
    ]
    sim_obj_path = output_path.parent / "silicon_slab_v2_1_sim_objectives.json"
    sim_obj_path.write_text(json.dumps(sim_objectives, indent=2), encoding="utf-8")

    return {
        "project_json": str(output_path),
        "study_name": "silicon_slab_v2_1",
        "sim_objectives": str(sim_obj_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a 2-parameter Silicon Slab v2.1 simulation-in-loop project JSON.")
    parser.add_argument(
        "--output",
        default="surrogate/benchmarks/silicon_slab_v2/project.json",
        help="Output project JSON path.",
    )
    args = parser.parse_args()

    summary = create_silicon_slab_v2_project(Path(args.output).expanduser().resolve())

    print(json.dumps({
        "success": True,
        **summary,
        "next": [
            "Use /api/param_optimizer/head_to_head_simulation_in_loop with study_name=silicon_slab_v2_1",
            "Set sim_params.save_hits=true and sim_params.save_particles=true",
        ],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
