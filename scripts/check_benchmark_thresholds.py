#!/usr/bin/env python3
"""Threshold checker for smart-import benchmark results.

Exits with non-zero status if any configured threshold fails.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


def _read_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _safe_get(d: Dict[str, Any], *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def evaluate(result: Dict[str, Any], policy: Dict[str, Any]) -> List[str]:
    errors: List[str] = []

    modes = result.get("modes", {})
    baseline = modes.get("tessellated_baseline", {})
    smart = modes.get("smart_import", {})

    if policy.get("require_success", True):
        if not baseline.get("success", False):
            errors.append("Baseline mode did not succeed")
        if not smart.get("success", False):
            errors.append("Smart mode did not succeed")

    b_time = _safe_get(baseline, "import", "elapsed_s")
    s_time = _safe_get(smart, "import", "elapsed_s")

    if isinstance(b_time, (int, float)) and isinstance(s_time, (int, float)) and b_time > 0:
        overhead_pct = ((s_time - b_time) / b_time) * 100.0
        max_overhead = policy.get("max_import_overhead_pct")
        if isinstance(max_overhead, (int, float)) and overhead_pct > max_overhead:
            errors.append(
                f"Import overhead too high: {overhead_pct:.2f}% > {max_overhead:.2f}%"
            )
    else:
        errors.append("Missing import elapsed times for baseline/smart")

    sel_ratio = _safe_get(smart, "import", "normalized_summary", "selected_primitive_ratio")
    min_ratio = policy.get("min_selected_primitive_ratio")
    if isinstance(min_ratio, (int, float)):
        if not isinstance(sel_ratio, (int, float)):
            errors.append("Missing smart selected_primitive_ratio")
        elif sel_ratio < min_ratio:
            errors.append(
                f"Selected primitive ratio too low: {sel_ratio:.4f} < {min_ratio:.4f}"
            )

    return errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Check benchmark result against thresholds.")
    parser.add_argument("--thresholds", required=True, help="Threshold policy JSON")
    parser.add_argument("--result", required=True, help="Benchmark result JSON")
    args = parser.parse_args()

    thresholds = _read_json(Path(args.thresholds).expanduser().resolve())
    result = _read_json(Path(args.result).expanduser().resolve())

    benchmark_name = result.get("benchmark_name")
    if benchmark_name not in thresholds:
        print(f"ERROR: no threshold policy found for benchmark '{benchmark_name}'", file=sys.stderr)
        sys.exit(2)

    policy = thresholds[benchmark_name]
    errors = evaluate(result, policy)

    if errors:
        print(f"Benchmark '{benchmark_name}' FAILED thresholds:")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)

    print(f"Benchmark '{benchmark_name}' PASSED thresholds.")


if __name__ == "__main__":
    main()
