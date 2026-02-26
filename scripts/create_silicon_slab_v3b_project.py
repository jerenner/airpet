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


def create_silicon_slab_v3b_project(output_path: Path) -> dict:
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
        *pm.add_define("si_thickness_mm", "constant", "1.5", "mm", "geometry"),
        context="add_define(thickness)",
    )
    half_x_define = _must(
        *pm.add_define("si_half_x_mm", "constant", "12.5", "mm", "geometry"),
        context="add_define(half_x)",
    )
    half_y_define = _must(
        *pm.add_define("si_half_y_mm", "constant", "12.5", "mm", "geometry"),
        context="add_define(half_y)",
    )
    slab_z_define = _must(
        *pm.add_define("si_slab_z_mm", "constant", "0.0", "mm", "geometry"),
        context="add_define(slab_z)",
    )

    slab_solid = _must(
        *pm.add_solid("si_slab_solid", "box", {
            "x": half_x_define["name"],
            "y": half_y_define["name"],
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
            {"x": "0", "y": "0", "z": slab_z_define["name"]},
            {"x": "0", "y": "0", "z": "0"},
            {"x": "1", "y": "1", "z": "1"},
        ),
        context="add_physical_volume",
    )

    source, err = pm.add_source(
        "src_electron",
        {
            "particle": "e-",
            "ene/type": "Mono",
            "ene/mono": "1000",
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
            "default": 1.5,
            "units": "mm",
            "enabled": True,
        }),
        context="param(thickness)",
    )

    _must(
        *pm.upsert_parameter_registry_entry("si_half_x", {
            "name": "si_half_x",
            "target_type": "define",
            "target_ref": {"name": half_x_define["name"]},
            "bounds": {"min": 5.0, "max": 35.0},
            "default": 12.5,
            "units": "mm",
            "enabled": True,
        }),
        context="param(half_x)",
    )

    _must(
        *pm.upsert_parameter_registry_entry("si_half_y", {
            "name": "si_half_y",
            "target_type": "define",
            "target_ref": {"name": half_y_define["name"]},
            "bounds": {"min": 5.0, "max": 35.0},
            "default": 12.5,
            "units": "mm",
            "enabled": True,
        }),
        context="param(half_y)",
    )

    _must(
        *pm.upsert_parameter_registry_entry("si_slab_z", {
            "name": "si_slab_z",
            "target_type": "define",
            "target_ref": {"name": slab_z_define["name"]},
            "bounds": {"min": -15.0, "max": 15.0},
            "default": 0.0,
            "units": "mm",
            "enabled": True,
        }),
        context="param(slab_z)",
    )

    _must(
        *pm.upsert_parameter_registry_entry("src_z", {
            "name": "src_z",
            "target_type": "source",
            "target_ref": {"name": "src_electron", "field": "position.z"},
            "bounds": {"min": -50.0, "max": -5.0},
            "default": -20.0,
            "units": "mm",
            "enabled": True,
        }),
        context="param(src_z)",
    )

    # v3.1b: robust-normalized objective composition to damp outliers.
    _must(
        *pm.upsert_param_study("silicon_slab_v3_1b", {
            "name": "silicon_slab_v3_1b",
            "mode": "random",
            "parameters": ["si_thickness", "si_half_x", "si_half_y", "si_slab_z", "src_z"],
            "random": {"samples": 120, "seed": 42},
            "objectives": [
                {"metric": "sim_metric", "name": "edep_sum", "key": "edep_sum", "direction": "maximize"},
                {"metric": "parameter_value", "name": "thickness_mm", "parameter": "si_thickness", "direction": "minimize"},
                {"metric": "parameter_value", "name": "half_x_mm", "parameter": "si_half_x", "direction": "minimize"},
                {"metric": "parameter_value", "name": "half_y_mm", "parameter": "si_half_y", "direction": "minimize"},
                {"metric": "parameter_value", "name": "slab_z_mm", "parameter": "si_slab_z", "direction": "minimize"},
                {"metric": "parameter_value", "name": "src_z_mm", "parameter": "src_z", "direction": "minimize"},
                {"metric": "formula", "name": "edep_log", "direction": "maximize", "expression": "log(1 + max(edep_sum, 0))"},
                {"metric": "formula", "name": "area_norm", "direction": "minimize", "expression": "clip((half_x_mm/12.5) * (half_y_mm/12.5), 0, 6)"},
                {"metric": "formula", "name": "thickness_norm", "direction": "minimize", "expression": "clip(thickness_mm/3.0, 0, 3)"},
                {"metric": "formula", "name": "cost_norm", "direction": "minimize", "expression": "clip(area_norm * thickness_norm, 0, 8)"},
                {"metric": "formula", "name": "distance_norm", "direction": "minimize", "expression": "clip(abs(src_z_mm - slab_z_mm)/20.0, 0, 3)"},
                {"metric": "formula", "name": "score", "direction": "maximize", "expression": "0.8*edep_log - 0.15*cost_norm - 0.05*distance_norm"},
            ],
        }),
        context="upsert_param_study(v3_1b)",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(pm.save_project_to_json_string(), encoding="utf-8")

    sim_objectives = [
        {
            "name": "edep_sum",
            "metric": "hdf5_reduce",
            "dataset_path": "default_ntuples/Hits/Edep",
            "reduce": "sum",
        }
    ]
    sim_obj_path = output_path.parent / "silicon_slab_v3_1b_sim_objectives.json"
    sim_obj_path.write_text(json.dumps(sim_objectives, indent=2), encoding="utf-8")

    return {
        "project_json": str(output_path),
        "study_name": "silicon_slab_v3_1b",
        "n_parameters": 5,
        "sim_objectives": str(sim_obj_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a 5-parameter Silicon Slab v3.1b (robust-normalized objective) benchmark project.")
    parser.add_argument(
        "--output",
        default="surrogate/benchmarks/silicon_slab_v3b/project.json",
        help="Output project JSON path.",
    )
    args = parser.parse_args()

    summary = create_silicon_slab_v3b_project(Path(args.output).expanduser().resolve())
    print(json.dumps({"success": True, **summary}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
