#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import app
from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


def _make_pm() -> ProjectManager:
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


def _add_define_param(pm: ProjectManager, name: str = "p1"):
    obj, err = pm.add_define("sweep_define", "constant", "10", "mm", "geometry")
    if obj is None or err is not None:
        raise RuntimeError(f"Failed to add define: {err}")

    entry, err = pm.upsert_parameter_registry_entry(name, {
        "name": name,
        "target_type": "define",
        "target_ref": {"name": "sweep_define"},
        "bounds": {"min": 0, "max": 10},
        "default": 5,
        "units": "mm",
        "enabled": True,
    })
    if entry is None or err is not None:
        raise RuntimeError(f"Failed to register parameter '{name}': {err}")


def _ensure_study(pm: ProjectManager, study_name: str, parameter_name: str, samples: int, seed: int):
    study, err = pm.upsert_param_study(study_name, {
        "name": study_name,
        "mode": "random",
        "parameters": [parameter_name],
        "random": {"samples": int(samples), "seed": int(seed)},
        "objectives": [{"metric": "success_flag", "name": "success", "direction": "maximize"}],
    })
    if study is None or err is not None:
        raise RuntimeError(f"Failed to upsert study '{study_name}': {err}")


def _record_step(steps, name: str, ok: bool, **details):
    steps.append({"step": name, "ok": bool(ok), **details})


def main() -> int:
    parser = argparse.ArgumentParser(description="Run AIRPET Phase D closeout sanity flow (verify -> apply -> token-reuse block -> audit history -> rollback).")
    parser.add_argument("--study-name", default="phase_d_closeout_sanity")
    parser.add_argument("--parameter-name", default="p1")
    parser.add_argument("--study-samples", type=int, default=4)
    parser.add_argument("--study-seed", type=int, default=7)
    parser.add_argument("--optimizer-budget", type=int, default=5)
    parser.add_argument("--optimizer-seed", type=int, default=13)
    parser.add_argument("--verify-repeats", type=int, default=3)
    parser.add_argument("--json-out", default=None, help="Optional output file path for JSON report.")
    parser.add_argument("--strict", action="store_true", default=True, help="Return non-zero if any sanity check fails (default: true).")
    parser.add_argument("--no-strict", dest="strict", action="store_false")
    args = parser.parse_args()

    report = {
        "success": False,
        "flow": "phase_d_closeout_sanity",
        "config": {
            "study_name": args.study_name,
            "parameter_name": args.parameter_name,
            "study_samples": args.study_samples,
            "study_seed": args.study_seed,
            "optimizer_budget": args.optimizer_budget,
            "optimizer_seed": args.optimizer_seed,
            "verify_repeats": args.verify_repeats,
        },
        "steps": [],
        "artifacts": {},
        "errors": [],
    }

    try:
        pm = _make_pm()
        _add_define_param(pm, name=args.parameter_name)
        _ensure_study(pm, args.study_name, args.parameter_name, args.study_samples, args.study_seed)

        run, err = pm.run_param_optimizer(
            args.study_name,
            method="random_search",
            budget=int(args.optimizer_budget),
            seed=int(args.optimizer_seed),
        )
        if run is None or err is not None:
            raise RuntimeError(f"Failed to run optimizer: {err}")

        run_id = run.get("run_id")
        if not run_id:
            raise RuntimeError("Optimizer run did not return run_id.")
        report["artifacts"]["run_id"] = run_id

        app.config["TESTING"] = True
        with app.test_client() as client:
            with patch("app.get_project_manager_for_session", return_value=pm), \
                 patch("app.RUN_POLICY_REQUIRE_VERIFY_TOKEN", True), \
                 patch("app.RUN_POLICY_REQUIRE_ALLOW_APPLY", True):

                verify_resp = client.post("/api/param_optimizer/verify_best", json={
                    "run_id": run_id,
                    "repeats": int(args.verify_repeats),
                })
                verify_data = verify_resp.get_json() or {}
                gate = (verify_data.get("verification_gate") or {})
                token = verify_data.get("apply_token")
                gate_passed = bool(gate.get("passed"))
                _record_step(
                    report["steps"],
                    "verify_best",
                    verify_resp.status_code == 200 and gate_passed and bool(token),
                    status_code=verify_resp.status_code,
                    gate_passed=gate_passed,
                    token_issued=bool(token),
                )
                report["artifacts"]["apply_token_issued"] = bool(token)

                apply_resp = client.post("/api/param_optimizer/replay_best", json={
                    "run_id": run_id,
                    "apply_to_project": True,
                    "allow_apply": True,
                    "verification_token": token,
                })
                apply_data = apply_resp.get_json() or {}
                audit = apply_data.get("apply_audit") or {}
                audit_id = audit.get("audit_id")
                _record_step(
                    report["steps"],
                    "apply_best",
                    apply_resp.status_code == 200 and bool(audit_id),
                    status_code=apply_resp.status_code,
                    audit_created=bool(audit_id),
                )
                report["artifacts"]["audit_id"] = audit_id

                reuse_resp = client.post("/api/param_optimizer/replay_best", json={
                    "run_id": run_id,
                    "apply_to_project": True,
                    "allow_apply": True,
                    "verification_token": token,
                })
                reuse_data = reuse_resp.get_json() or {}
                reuse_blocked = reuse_resp.status_code == 400 and (reuse_data.get("error") == "Apply policy validation failed.")
                _record_step(
                    report["steps"],
                    "token_reuse_blocked",
                    reuse_blocked,
                    status_code=reuse_resp.status_code,
                    error=reuse_data.get("error"),
                    details=reuse_data.get("details"),
                )

                hist_resp = client.get("/api/param_optimizer/apply_audit_history")
                hist_data = hist_resp.get_json() or {}
                hist_count = int(hist_data.get("count") or 0)
                _record_step(
                    report["steps"],
                    "apply_audit_history",
                    hist_resp.status_code == 200 and hist_count >= 1,
                    status_code=hist_resp.status_code,
                    count=hist_count,
                )

                rollback_resp = client.post("/api/param_optimizer/rollback_last_apply", json={
                    "audit_id": audit_id,
                })
                rollback_data = rollback_resp.get_json() or {}
                rolled = bool((rollback_data.get("rolled_back_audit") or {}).get("rolled_back"))
                _record_step(
                    report["steps"],
                    "rollback_selected",
                    rollback_resp.status_code == 200 and rolled,
                    status_code=rollback_resp.status_code,
                    rolled_back=rolled,
                )

    except Exception as exc:
        report["errors"].append(str(exc))

    all_ok = all(bool(s.get("ok")) for s in report["steps"]) and len(report["errors"]) == 0
    report["success"] = all_ok

    text = json.dumps(report, indent=2)
    print(text)

    if args.json_out:
        out_path = Path(args.json_out).expanduser().resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text + "\n", encoding="utf-8")

    if args.strict and not all_ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
