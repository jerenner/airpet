#!/usr/bin/env python3
"""Print a compact summary from smart-import benchmark JSON output."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def _read(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _safe_get(d: Dict[str, Any], *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def _pct(x: float | None) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:.2f}%"


def summarize(data: Dict[str, Any]) -> str:
    modes = data.get("modes", {})
    base = modes.get("tessellated_baseline", {})
    smart = modes.get("smart_import", {})

    b_time = _safe_get(base, "import", "elapsed_s")
    s_time = _safe_get(smart, "import", "elapsed_s")

    b_norm = _safe_get(base, "import", "normalized_summary", default={}) or {}
    s_norm = _safe_get(smart, "import", "normalized_summary", default={}) or {}

    delta_s = None
    delta_pct = None
    if isinstance(b_time, (int, float)) and isinstance(s_time, (int, float)) and b_time > 0:
        delta_s = s_time - b_time
        delta_pct = delta_s / b_time

    lines = []
    lines.append(f"Benchmark: {data.get('benchmark_name', 'unknown')}")
    lines.append(f"STEP: {data.get('step_file', 'unknown')}")
    lines.append("")
    lines.append(f"Import time (baseline): {b_time:.3f}s" if isinstance(b_time, (int, float)) else "Import time (baseline): n/a")
    lines.append(f"Import time (smart):    {s_time:.3f}s" if isinstance(s_time, (int, float)) else "Import time (smart): n/a")
    if delta_s is not None and delta_pct is not None:
        sign = "+" if delta_s >= 0 else ""
        lines.append(f"Delta (smart-baseline): {sign}{delta_s:.3f}s ({sign}{delta_pct*100:.2f}%)")
    else:
        lines.append("Delta (smart-baseline): n/a")

    lines.append("")
    lines.append(f"Imported solids (baseline): {b_norm.get('imported_solid_count', 'n/a')}")
    lines.append(f"Imported solids (smart):    {s_norm.get('imported_solid_count', 'n/a')}")

    lines.append(f"Smart candidate total:      {s_norm.get('candidate_total', 'n/a')}")
    lines.append(f"Smart selected primitive:   {s_norm.get('selected_primitive_count', 'n/a')}")
    lines.append(f"Smart selected tessellated: {s_norm.get('selected_tessellated_count', 'n/a')}")
    lines.append(f"Smart selected ratio:       {_pct(s_norm.get('selected_primitive_ratio'))}")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize smart-import benchmark output JSON.")
    parser.add_argument("result", help="Path to benchmark result JSON")
    args = parser.parse_args()

    path = Path(args.result).expanduser().resolve()
    data = _read(path)
    print(summarize(data))


if __name__ == "__main__":
    main()
