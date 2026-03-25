#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.scoped_preflight_replay import (  # noqa: E402
    DEFAULT_ARTIFACT_PATH,
    format_scoped_preflight_replay_report,
    load_replay_artifact,
    run_scoped_preflight_workflow_replay,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Replay examples/preflight/scoped_preflight_route_ai_workflow_replay.json "
            "through route + AI wrapper and emit a compact PASS/FAIL report."
        )
    )
    parser.add_argument(
        "--artifact",
        default=str(DEFAULT_ARTIFACT_PATH),
        help="Path to a scoped preflight replay artifact JSON file.",
    )
    parser.add_argument(
        "--max-diff-lines",
        type=int,
        default=80,
        help="Maximum unified-diff lines to print per mismatch (0 disables truncation).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report instead of text.",
    )
    args = parser.parse_args()

    artifact_path = Path(args.artifact).expanduser().resolve()
    artifact = load_replay_artifact(artifact_path)
    result = run_scoped_preflight_workflow_replay(
        artifact,
        max_diff_lines=max(0, int(args.max_diff_lines)),
    )

    if args.json:
        payload = {
            "artifact": str(artifact_path),
            **result,
        }
        print(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False))
    else:
        print(
            format_scoped_preflight_replay_report(
                result,
                artifact_path=str(artifact_path),
            )
        )

    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
