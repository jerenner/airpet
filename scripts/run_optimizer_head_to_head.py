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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run classical vs surrogate optimizer head-to-head on a saved project JSON.")
    parser.add_argument("--project-json", required=True, help="Path to project/version JSON containing param study + registry.")
    parser.add_argument("--study-name", required=True, help="Param study name to optimize.")
    parser.add_argument("--budget", type=int, default=40)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--objective-name", default=None)
    parser.add_argument("--direction", default=None, help="maximize|minimize (optional)")
    parser.add_argument("--classical-method", default="cmaes", choices=["random_search", "cmaes"])
    parser.add_argument("--cmaes-population-size", type=int, default=None)
    parser.add_argument("--warmup-runs", type=int, default=10)
    parser.add_argument("--candidate-pool-size", type=int, default=256)
    parser.add_argument("--exploration-beta", type=float, default=1.0)
    parser.add_argument("--gp-noise", type=float, default=1e-6)
    args = parser.parse_args()

    project_path = Path(args.project_json).expanduser().resolve()
    payload = project_path.read_text(encoding="utf-8")

    pm = ProjectManager(ExpressionEvaluator())
    pm.load_project_from_json_string(payload)

    cmaes_cfg = None
    if args.cmaes_population_size is not None:
        cmaes_cfg = {"population_size": int(args.cmaes_population_size)}

    result, err = pm.run_optimizer_head_to_head(
        study_name=args.study_name,
        budget=args.budget,
        seed=args.seed,
        objective_name=args.objective_name,
        direction=args.direction,
        classical_method=args.classical_method,
        cmaes_config=cmaes_cfg,
        surrogate_config={
            "warmup_runs": args.warmup_runs,
            "candidate_pool_size": args.candidate_pool_size,
            "exploration_beta": args.exploration_beta,
            "gp_noise": args.gp_noise,
        },
    )

    if not result:
        print(json.dumps({"success": False, "error": err}, indent=2))
        return 1

    print(json.dumps({"success": True, "comparison": result}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
