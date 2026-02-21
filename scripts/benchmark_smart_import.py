#!/usr/bin/env python3
"""Benchmark harness for Smart CAD import reliability/performance comparisons.

Runs the same STEP import in two modes:
1) smartImport = false (full tessellated baseline)
2) smartImport = true  (hybrid smart import)

Optionally launches a simulation run and records elapsed time to completion.
This script uses Flask's in-process test client (no external server required).
"""

from __future__ import annotations

import argparse
import io
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app import app


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _post_json(client, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    resp = client.post(url, json=payload)
    return {"status": resp.status_code, "json": resp.get_json(silent=True)}


def _normalize_import_metrics(payload: Dict[str, Any], report: Dict[str, Any], options: Dict[str, Any]) -> Dict[str, Any]:
    summary = report.get("summary") or {}
    mode_counts = summary.get("selected_mode_counts") or {}

    project_state = payload.get("project_state") or {}
    solids = project_state.get("solids") or {}
    grouping_name = str(options.get("groupingName", ""))
    imported_solid_count = 0
    if grouping_name:
        prefix = f"{grouping_name}_solid_"
        imported_solid_count = sum(1 for solid_name in solids.keys() if str(solid_name).startswith(prefix))

    report_available = bool(report)
    report_enabled = bool(report.get("enabled", False)) if report_available else False

    def _val(v):
        return v if report_enabled else None

    return {
        "report_available": report_available,
        "report_enabled": report_enabled,
        "imported_solid_count": imported_solid_count,
        "candidate_total": _val(summary.get("total", 0)),
        "candidate_primitive_count": _val(summary.get("primitive_count", 0)),
        "candidate_tessellated_count": _val(summary.get("tessellated_count", 0)),
        "selected_primitive_count": _val(mode_counts.get("primitive", 0)),
        "selected_tessellated_count": _val(mode_counts.get("tessellated", 0)),
        "selected_primitive_ratio": _val(summary.get("selected_primitive_ratio", 0.0)),
        "counts_by_classification": _val(summary.get("counts_by_classification") or {}),
    }


def _run_import_once(client, step_file: Path, options: Dict[str, Any]) -> Dict[str, Any]:
    with step_file.open("rb") as f:
        binary = f.read()

    data = {
        "stepFile": (io.BytesIO(binary), step_file.name),
        "options": json.dumps(options),
    }

    t0 = time.perf_counter()
    resp = client.post("/import_step_with_options", data=data, content_type="multipart/form-data")
    dt = time.perf_counter() - t0

    payload = resp.get_json(silent=True) or {}
    report = payload.get("step_import_report") or {}
    summary = report.get("summary") or {}
    normalized = _normalize_import_metrics(payload, report, options)

    return {
        "http_status": resp.status_code,
        "elapsed_s": dt,
        "success": bool(payload.get("success", False)),
        "error": payload.get("error"),
        "summary": summary,
        "normalized_summary": normalized,
        "report": report,
    }


def _run_simulation_once(client, sim_cfg: Dict[str, Any]) -> Dict[str, Any]:
    t0 = time.perf_counter()
    run_resp = _post_json(client, "/api/simulation/run", sim_cfg)

    payload = run_resp.get("json") or {}
    if run_resp["status"] != 200 or not payload.get("success"):
        return {
            "started": False,
            "http_status": run_resp["status"],
            "error": payload.get("error", "failed_to_start_simulation"),
            "elapsed_s": time.perf_counter() - t0,
        }

    job_id = payload.get("job_id")
    timeout_s = float(sim_cfg.get("benchmark_timeout_s", 1800))
    poll_interval_s = float(sim_cfg.get("benchmark_poll_interval_s", 1.0))

    final_status = None
    final_payload = None

    while True:
        elapsed = time.perf_counter() - t0
        if elapsed > timeout_s:
            return {
                "started": True,
                "job_id": job_id,
                "timed_out": True,
                "elapsed_s": elapsed,
                "status": final_status,
            }

        status_resp = client.get(f"/api/simulation/status/{job_id}?since=0")
        final_payload = status_resp.get_json(silent=True) or {}
        status_obj = final_payload.get("status") or {}
        final_status = status_obj.get("status")

        if final_status in {"Completed", "Error", "Stopped"}:
            break

        time.sleep(poll_interval_s)

    return {
        "started": True,
        "job_id": job_id,
        "timed_out": False,
        "elapsed_s": time.perf_counter() - t0,
        "status": final_status,
        "status_payload": final_payload,
    }


def benchmark(config: Dict[str, Any]) -> Dict[str, Any]:
    step_file = Path(config["step_file"]).expanduser().resolve()
    if not step_file.exists():
        raise FileNotFoundError(f"STEP file not found: {step_file}")

    import_cfg = config.get("import", {})
    sim_cfg = config.get("simulation", {})

    results = {
        "benchmark_name": config.get("name", "smart_import_benchmark"),
        "created_at": _now_iso(),
        "step_file": str(step_file),
        "modes": {},
    }

    app.config["TESTING"] = True
    with app.test_client() as client:
        for mode_name, smart_import in (("tessellated_baseline", False), ("smart_import", True)):
            reset = _post_json(client, "/new_project", {})
            if reset["status"] != 200:
                results["modes"][mode_name] = {
                    "success": False,
                    "error": "failed_to_reset_project",
                    "reset": reset,
                }
                continue

            options = {
                "groupingName": import_cfg.get("groupingName", f"benchmark_{mode_name}"),
                "placementMode": import_cfg.get("placementMode", "assembly"),
                "parentLVName": import_cfg.get("parentLVName", "World"),
                "offset": import_cfg.get("offset", {"x": "0", "y": "0", "z": "0"}),
                "smartImport": smart_import,
            }

            if "smartImportConfidenceThreshold" in import_cfg:
                options["smartImportConfidenceThreshold"] = import_cfg["smartImportConfidenceThreshold"]

            import_result = _run_import_once(client, step_file, options)
            mode_entry: Dict[str, Any] = {
                "success": import_result["success"],
                "smart_import_requested": smart_import,
                "import": {
                    "elapsed_s": import_result["elapsed_s"],
                    "http_status": import_result["http_status"],
                    "error": import_result["error"],
                    "summary": import_result["summary"],
                    "normalized_summary": import_result["normalized_summary"],
                },
            }

            run_sim = bool(sim_cfg.get("enabled", False))
            if run_sim and import_result["success"]:
                sim_payload = {
                    "events": int(sim_cfg.get("events", 1000)),
                    "threads": int(sim_cfg.get("threads", 1)),
                    "print_progress": int(sim_cfg.get("print_progress", 1000)),
                    "save_hits": bool(sim_cfg.get("save_hits", False)),
                    "save_particles": bool(sim_cfg.get("save_particles", False)),
                    "save_tracks_range": sim_cfg.get("save_tracks_range", ""),
                    "physics_list": sim_cfg.get("physics_list", "FTFP_BERT"),
                    "optical_physics": bool(sim_cfg.get("optical_physics", False)),
                    "benchmark_timeout_s": float(sim_cfg.get("timeout_s", 1800)),
                    "benchmark_poll_interval_s": float(sim_cfg.get("poll_interval_s", 1.0)),
                }
                mode_entry["simulation"] = _run_simulation_once(client, sim_payload)

            results["modes"][mode_name] = mode_entry

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark Smart CAD import baseline vs hybrid mode.")
    parser.add_argument("--config", required=True, help="Path to benchmark config JSON")
    parser.add_argument("--output", default=None, help="Optional output JSON path")
    args = parser.parse_args()

    cfg_path = Path(args.config).expanduser().resolve()
    cfg = _read_json(cfg_path)

    result = benchmark(cfg)

    output_path = Path(args.output).expanduser().resolve() if args.output else None
    if output_path is None:
        out_dir = Path("benchmarks/results").resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = out_dir / f"smart_import_benchmark_{ts}.json"
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    print(f"Wrote benchmark result: {output_path}")


if __name__ == "__main__":
    main()
