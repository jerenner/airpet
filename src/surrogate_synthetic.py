from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .surrogate_dataset import build_surrogate_dataset_from_payloads


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _timestamp_tag() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _preset_parameter_specs(preset: str) -> List[Dict[str, Any]]:
    p = preset.lower().strip()
    if p == "linear_2d":
        return [
            {"name": "p1", "min": -1.0, "max": 1.0},
            {"name": "p2", "min": -1.0, "max": 1.0},
        ]
    if p == "nonlinear_3d":
        return [
            {"name": "p1", "min": -1.0, "max": 1.0},
            {"name": "p2", "min": -1.0, "max": 1.0},
            {"name": "p3", "min": -1.0, "max": 1.0},
        ]
    raise ValueError(f"Unsupported preset '{preset}'. Use 'linear_2d' or 'nonlinear_3d'.")


def _objective_noiseless(values: Dict[str, float], preset: str) -> float:
    p = preset.lower().strip()
    p1 = float(values.get("p1", 0.0))
    p2 = float(values.get("p2", 0.0))
    p3 = float(values.get("p3", 0.0))

    if p == "linear_2d":
        return 2.3 * p1 - 1.7 * p2 + 0.15

    if p == "nonlinear_3d":
        return (
            np.sin(2.0 * np.pi * p1)
            + 0.8 * (p2 ** 2)
            - 0.6 * p3
            + 0.45 * p1 * p2
            - 0.25 * p2 * p3
        )

    raise ValueError(f"Unsupported preset '{preset}'.")


def _sample_values(param_specs: Sequence[Dict[str, Any]], rng: np.random.Generator) -> Dict[str, float]:
    values: Dict[str, float] = {}
    for spec in param_specs:
        mn = float(spec["min"])
        mx = float(spec["max"])
        values[str(spec["name"])] = float(rng.uniform(mn, mx))
    return values


def _determine_success(values: Dict[str, float], preset: str, failure_probability: float, rng: np.random.Generator) -> bool:
    fail = float(max(0.0, min(1.0, failure_probability)))

    # Stochastic failures to simulate unstable simulation outcomes.
    if rng.uniform(0.0, 1.0) < fail:
        return False

    # Structured failure region to emulate physics/geometry invalid zones.
    p = preset.lower().strip()
    p1 = float(values.get("p1", 0.0))
    p2 = float(values.get("p2", 0.0))
    p3 = float(values.get("p3", 0.0))

    if p == "linear_2d":
        return abs(p1 + 0.85 * p2) < 1.45

    if p == "nonlinear_3d":
        return (p1 ** 2 + p2 ** 2 + p3 ** 2) < 2.25

    return True


def build_synthetic_optimizer_run(
    *,
    preset: str,
    n_runs: int,
    seed: int,
    noise_sigma: float,
    failure_probability: float,
    objective_name: str = "score",
) -> Dict[str, Any]:
    n = max(1, int(n_runs))
    rng = np.random.default_rng(int(seed))
    specs = _preset_parameter_specs(preset)

    run_id = f"synthetic_{preset}_{_timestamp_tag()}"
    created_at = _utc_now_iso()

    candidates: List[Dict[str, Any]] = []
    best: Optional[Dict[str, Any]] = None
    best_score = -float("inf")

    for i in range(n):
        values = _sample_values(specs, rng)
        noiseless = float(_objective_noiseless(values, preset))
        noisy = float(noiseless + rng.normal(0.0, float(noise_sigma)))

        success = _determine_success(values, preset, failure_probability, rng)
        objective_val = noisy if success else None

        objectives = {
            objective_name: objective_val,
            f"{objective_name}_noiseless": noiseless,
            "stability_flag": 1.0 if success else 0.0,
        }

        score = float(objective_val) if objective_val is not None else -float("inf")

        candidate = {
            "run_index": i,
            "values": values,
            "success": bool(success),
            "error": None if success else "Synthetic failure region/probability trigger",
            "metrics": {},
            "objectives": objectives,
            "optimizer_score": score,
            "optimizer_raw_score": score,
            "optimizer_penalty": 0.0,
        }
        candidates.append(candidate)

        if score > best_score:
            best_score = score
            best = candidate

    run_summary = {
        "run_id": run_id,
        "created_at": created_at,
        "study_name": f"synthetic_{preset}",
        "method": "synthetic_sampler",
        "seed": int(seed),
        "budget": int(n),
        "objective": {
            "name": objective_name,
            "direction": "maximize",
        },
        "success_count": int(sum(1 for c in candidates if c.get("success"))),
        "failure_count": int(sum(1 for c in candidates if not c.get("success"))),
        "best_run": best,
        "candidates": candidates,
        "stop_reason": "budget_exhausted",
        "evaluations_used": int(len(candidates)),
        "generation_stats": [],
        "step_size_history": [],
    }

    return run_summary


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def generate_synthetic_surrogate_benchmark(
    *,
    preset: str,
    n_runs: int,
    seed: int,
    noise_sigma: float,
    failure_probability: float,
    dataset_output_root: str,
    artifacts_root: str,
    dataset_name: Optional[str] = None,
    target_objective: str = "score",
    val_ratio: float = 0.2,
    split_seed: int = 42,
    only_success: bool = False,
    write_example_configs: bool = True,
) -> Dict[str, Any]:
    run_summary = build_synthetic_optimizer_run(
        preset=preset,
        n_runs=n_runs,
        seed=seed,
        noise_sigma=noise_sigma,
        failure_probability=failure_probability,
        objective_name=target_objective,
    )

    payload = {"optimizer_runs": {run_summary["run_id"]: run_summary}}

    if not dataset_name:
        dataset_name = f"synthetic_{preset}_{_timestamp_tag()}"

    manifest = build_surrogate_dataset_from_payloads(
        payloads=[(f"synthetic:{preset}", payload)],
        output_root=dataset_output_root,
        dataset_name=dataset_name,
        target_objective=target_objective,
        val_ratio=val_ratio,
        split_seed=split_seed,
        only_success=only_success,
    )

    artifacts_dir = Path(artifacts_root).expanduser().resolve() / dataset_name
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    payload_path = artifacts_dir / "synthetic_optimizer_runs.json"
    _write_json(payload_path, payload)

    manifest_path = Path(manifest["outputs"]["manifest"]).resolve()

    generated_configs: List[str] = []
    if write_example_configs:
        gp_cfg = {
            "experiment_name": f"{dataset_name}_gp",
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
                "input_params": list(manifest.get("schema", {}).get("parameter_fields", [])),
                "target_objective": manifest.get("target_objective"),
                "feature_scaling": {
                    "enabled": True,
                    "method": "standard",
                },
            },
            "training": {"seed": int(seed)},
            "output": {
                "root": "surrogate/experiments",
            },
        }

        mlp_cfg = {
            **gp_cfg,
            "experiment_name": f"{dataset_name}_mlp",
            "model": {
                "type": "mlp",
                "mlp": {
                    "hidden_size": 24,
                    "epochs": 600,
                    "learning_rate": 0.02,
                    "l2": 0.0,
                },
            },
        }

        gp_path = artifacts_dir / "example_experiment_gp.json"
        mlp_path = artifacts_dir / "example_experiment_mlp.json"
        _write_json(gp_path, gp_cfg)
        _write_json(mlp_path, mlp_cfg)
        generated_configs.extend([str(gp_path), str(mlp_path)])

    report = {
        "success": True,
        "created_at": _utc_now_iso(),
        "preset": preset,
        "dataset_name": dataset_name,
        "n_runs_requested": int(n_runs),
        "seed": int(seed),
        "noise_sigma": float(noise_sigma),
        "failure_probability": float(max(0.0, min(1.0, failure_probability))),
        "target_objective": target_objective,
        "dataset_manifest": str(manifest_path),
        "dataset_counts": manifest.get("counts", {}),
        "synthetic_payload": str(payload_path),
        "generated_experiment_configs": generated_configs,
    }

    report_path = artifacts_dir / "benchmark_report.json"
    _write_json(report_path, report)
    report["report_path"] = str(report_path)
    return report


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a minimal synthetic benchmark for surrogate strategy testing.")
    parser.add_argument("--preset", default="nonlinear_3d", choices=["linear_2d", "nonlinear_3d"])
    parser.add_argument("--runs", type=int, default=300, help="Number of synthetic candidate runs.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--noise-sigma", type=float, default=0.05)
    parser.add_argument("--failure-probability", type=float, default=0.08)
    parser.add_argument("--dataset-output-root", default="surrogate/datasets")
    parser.add_argument("--artifacts-root", default="surrogate/benchmarks")
    parser.add_argument("--dataset-name", default=None)
    parser.add_argument("--target-objective", default="score")
    parser.add_argument("--val-ratio", type=float, default=0.2)
    parser.add_argument("--split-seed", type=int, default=42)
    parser.add_argument("--only-success", action="store_true")
    parser.add_argument("--no-example-configs", action="store_true")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    report = generate_synthetic_surrogate_benchmark(
        preset=args.preset,
        n_runs=args.runs,
        seed=args.seed,
        noise_sigma=args.noise_sigma,
        failure_probability=args.failure_probability,
        dataset_output_root=args.dataset_output_root,
        artifacts_root=args.artifacts_root,
        dataset_name=args.dataset_name,
        target_objective=args.target_objective,
        val_ratio=args.val_ratio,
        split_seed=args.split_seed,
        only_success=bool(args.only_success),
        write_example_configs=not bool(args.no_example_configs),
    )

    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
