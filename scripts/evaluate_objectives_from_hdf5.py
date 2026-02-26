#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.objective_engine import extract_objective_values_from_hdf5


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate objective definitions against an HDF5 simulation output.")
    parser.add_argument("--hdf5", required=True, help="Path to output.hdf5")
    parser.add_argument("--objectives", required=True, help="Path to objectives JSON (list)")
    parser.add_argument("--context", default=None, help="Optional JSON object string or JSON file path.")
    args = parser.parse_args()

    hdf5_path = Path(args.hdf5).expanduser().resolve()
    objectives_path = Path(args.objectives).expanduser().resolve()

    objectives = json.loads(objectives_path.read_text(encoding="utf-8"))
    if not isinstance(objectives, list):
        raise ValueError("Objectives file must be a JSON list.")

    context = {}
    if args.context:
        raw = args.context.strip()
        p = Path(raw).expanduser()
        if p.exists():
            context = json.loads(p.read_text(encoding="utf-8"))
        else:
            context = json.loads(raw)
        if not isinstance(context, dict):
            raise ValueError("Context must decode to a JSON object.")

    values, warnings, available = extract_objective_values_from_hdf5(
        output_path=str(hdf5_path),
        objectives=objectives,
        context=context,
    )

    print(json.dumps({
        "success": True,
        "hdf5": str(hdf5_path),
        "objective_values": values,
        "warnings": warnings,
        "available_metrics": available,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
