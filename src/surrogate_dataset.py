from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass
class ExtractedRow:
    source_kind: str
    source_path: str
    source_run_id: str
    study_name: Optional[str]
    method: Optional[str]
    seed: Optional[int]
    timestamp: Optional[str]
    run_index: Optional[int]
    success: bool
    error: Optional[str]
    params: Dict[str, Any]
    objectives: Dict[str, Any]
    suggested_target_objective: Optional[str] = None
    split: Optional[str] = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _hash_suffix(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:10]


def _as_dict(value: Any) -> Dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _as_list(value: Any) -> List[Any]:
    return list(value) if isinstance(value, list) else []


def discover_json_inputs(input_paths: Sequence[str]) -> List[Path]:
    discovered: List[Path] = []
    seen: set[str] = set()

    for raw in input_paths:
        p = Path(raw).expanduser().resolve()
        if not p.exists():
            continue

        candidates: List[Path] = []
        if p.is_file() and p.suffix.lower() == ".json":
            candidates = [p]
        elif p.is_dir():
            version_files = sorted(p.rglob("version.json"))
            other_json = sorted(x for x in p.rglob("*.json") if x.name != "version.json")
            candidates = version_files + other_json

        for c in candidates:
            key = str(c)
            if key not in seen:
                seen.add(key)
                discovered.append(c)

    return discovered


def _extract_from_optimizer_run(run: Dict[str, Any], source_path: str, source_kind: str) -> List[ExtractedRow]:
    rows: List[ExtractedRow] = []

    run_id = run.get("run_id")
    if not run_id:
        run_id = f"opt_{_hash_suffix(source_path + json.dumps(run, sort_keys=True, default=str))}"

    study_name = run.get("study_name")
    method = run.get("method")
    seed = _safe_int(run.get("seed"))
    timestamp = run.get("created_at")
    suggested_target = _as_dict(run.get("objective")).get("name")

    for cand in _as_list(run.get("candidates")):
        values = _as_dict(cand.get("values"))
        objectives = _as_dict(cand.get("objectives"))

        rows.append(
            ExtractedRow(
                source_kind=source_kind,
                source_path=source_path,
                source_run_id=str(run_id),
                study_name=study_name,
                method=method,
                seed=seed,
                timestamp=timestamp,
                run_index=_safe_int(cand.get("run_index")),
                success=bool(cand.get("success", False)),
                error=cand.get("error"),
                params=values,
                objectives=objectives,
                suggested_target_objective=suggested_target,
            )
        )

    return rows


def _extract_from_study_result(study: Dict[str, Any], source_path: str, source_kind: str) -> List[ExtractedRow]:
    rows: List[ExtractedRow] = []

    study_name = study.get("study_name") or study.get("name")
    run_id = study.get("run_id") or f"study_{study_name or 'unknown'}_{_hash_suffix(source_path)}"
    timestamp = study.get("created_at")
    seed = _safe_int(_as_dict(study.get("random")).get("seed"))

    for run in _as_list(study.get("runs")):
        values = _as_dict(run.get("values"))
        objectives = _as_dict(run.get("objectives"))

        rows.append(
            ExtractedRow(
                source_kind=source_kind,
                source_path=source_path,
                source_run_id=str(run_id),
                study_name=study_name,
                method="study",
                seed=seed,
                timestamp=timestamp,
                run_index=_safe_int(run.get("run_index")),
                success=bool(run.get("success", False)),
                error=run.get("error"),
                params=values,
                objectives=objectives,
            )
        )

    return rows


def extract_rows_from_payload(payload: Any, source_path: str) -> List[ExtractedRow]:
    rows: List[ExtractedRow] = []

    if isinstance(payload, list):
        for item in payload:
            rows.extend(extract_rows_from_payload(item, source_path))
        return rows

    if not isinstance(payload, dict):
        return rows

    # API wrapper: {"study_result": {...}}
    if isinstance(payload.get("study_result"), dict):
        rows.extend(_extract_from_study_result(payload["study_result"], source_path, "study_result"))

    # Direct study result shape
    if "runs" in payload and ("study_name" in payload or "requested_runs" in payload):
        rows.extend(_extract_from_study_result(payload, source_path, "study_result"))

    # API wrapper / list shape: {"optimizer_runs": [...]}
    optimizer_runs = payload.get("optimizer_runs")
    if isinstance(optimizer_runs, list):
        for run in optimizer_runs:
            if isinstance(run, dict):
                rows.extend(_extract_from_optimizer_run(run, source_path, "optimizer_run"))

    # Project state shape: {"optimizer_runs": {"run_id": {...}}}
    if isinstance(optimizer_runs, dict):
        for run in optimizer_runs.values():
            if isinstance(run, dict):
                rows.extend(_extract_from_optimizer_run(run, source_path, "optimizer_run"))

    # Direct single optimizer run shape
    if "run_id" in payload and "candidates" in payload:
        rows.extend(_extract_from_optimizer_run(payload, source_path, "optimizer_run"))

    return rows


def _source_summary(path: str, rows: Sequence[ExtractedRow]) -> Dict[str, Any]:
    return {
        "path": str(path),
        "records_extracted": len(rows),
        "source_run_ids": sorted({r.source_run_id for r in rows}),
        "source_kinds": sorted({r.source_kind for r in rows}),
    }


def load_rows_from_inputs(input_paths: Sequence[str]) -> Tuple[List[ExtractedRow], List[Dict[str, Any]]]:
    files = discover_json_inputs(input_paths)
    all_rows: List[ExtractedRow] = []
    source_summaries: List[Dict[str, Any]] = []

    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        rows = extract_rows_from_payload(payload, str(path))
        all_rows.extend(rows)
        source_summaries.append(_source_summary(str(path), rows))

    return all_rows, source_summaries


def load_rows_from_payloads(payloads: Sequence[Tuple[str, Any]]) -> Tuple[List[ExtractedRow], List[Dict[str, Any]]]:
    all_rows: List[ExtractedRow] = []
    source_summaries: List[Dict[str, Any]] = []

    for source_label, payload in payloads:
        rows = extract_rows_from_payload(payload, source_label)
        all_rows.extend(rows)
        source_summaries.append(_source_summary(source_label, rows))

    return all_rows, source_summaries


def choose_target_objective(rows: Sequence[ExtractedRow], explicit_target: Optional[str]) -> str:
    objective_names = sorted({k for r in rows for k in r.objectives.keys()})

    if explicit_target:
        if explicit_target not in objective_names:
            raise ValueError(
                f"Requested target objective '{explicit_target}' was not found in extracted objectives: {objective_names}"
            )
        return explicit_target

    suggested = [r.suggested_target_objective for r in rows if r.suggested_target_objective]
    for name in suggested:
        if name in objective_names:
            return name

    if objective_names:
        counts: Dict[str, int] = {name: 0 for name in objective_names}
        for r in rows:
            for key in r.objectives.keys():
                counts[key] = counts.get(key, 0) + 1
        return max(counts.keys(), key=lambda k: counts[k])

    raise ValueError("No objective values found. Cannot choose a training target.")


def assign_train_val_split(rows: List[ExtractedRow], val_ratio: float, split_seed: int) -> None:
    if not rows:
        return

    ratio = max(0.0, min(float(val_ratio), 1.0))
    rng = random.Random(int(split_seed))
    indices = list(range(len(rows)))
    rng.shuffle(indices)

    n_total = len(rows)
    n_val = int(round(n_total * ratio))

    if ratio > 0.0 and n_total > 1:
        n_val = max(1, min(n_total - 1, n_val))
    else:
        n_val = 0

    val_indices = set(indices[:n_val])
    for idx, row in enumerate(rows):
        row.split = "val" if idx in val_indices else "train"


def _to_number_or_none(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def flatten_rows(rows: Sequence[ExtractedRow], target_objective: str) -> Tuple[List[Dict[str, Any]], List[str], List[str], List[str]]:
    parameter_names = sorted({k for r in rows for k in r.params.keys()})
    objective_names = sorted({k for r in rows for k in r.objectives.keys()})

    metadata_fields = [
        "split",
        "source_kind",
        "source_path",
        "source_run_id",
        "study_name",
        "method",
        "seed",
        "timestamp",
        "run_index",
        "success",
        "failed",
        "error",
        "target_objective",
        "target_value",
    ]
    parameter_fields = [f"param__{name}" for name in parameter_names]
    objective_fields = [f"objective__{name}" for name in objective_names]
    fieldnames = metadata_fields + parameter_fields + objective_fields

    flattened: List[Dict[str, Any]] = []
    for row in rows:
        out: Dict[str, Any] = {
            "split": row.split,
            "source_kind": row.source_kind,
            "source_path": row.source_path,
            "source_run_id": row.source_run_id,
            "study_name": row.study_name,
            "method": row.method,
            "seed": row.seed,
            "timestamp": row.timestamp,
            "run_index": row.run_index,
            "success": bool(row.success),
            "failed": not bool(row.success),
            "error": row.error,
            "target_objective": target_objective,
            "target_value": _to_number_or_none(row.objectives.get(target_objective)),
        }

        for p in parameter_names:
            out[f"param__{p}"] = _to_number_or_none(row.params.get(p))

        for o in objective_names:
            out[f"objective__{o}"] = _to_number_or_none(row.objectives.get(o))

        flattened.append(out)

    return flattened, parameter_names, objective_names, fieldnames


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _materialize_dataset(
    *,
    rows: List[ExtractedRow],
    source_summaries: Sequence[Dict[str, Any]],
    output_root: str,
    dataset_name: Optional[str],
    target_objective: Optional[str],
    val_ratio: float,
    split_seed: int,
    only_success: bool,
) -> Dict[str, Any]:
    if not rows:
        raise ValueError("No usable study/optimizer runs found in provided sources.")

    if only_success:
        rows = [r for r in rows if r.success]
    if not rows:
        raise ValueError("No rows remaining after filtering.")

    chosen_target = choose_target_objective(rows, explicit_target=target_objective)
    assign_train_val_split(rows, val_ratio=val_ratio, split_seed=split_seed)

    flat_rows, parameter_names, objective_names, fieldnames = flatten_rows(rows, target_objective=chosen_target)

    output_base = Path(output_root).expanduser().resolve()
    if not dataset_name:
        dataset_name = datetime.now(timezone.utc).strftime("dataset_%Y%m%dT%H%M%SZ")
    dataset_dir = output_base / dataset_name

    all_csv = dataset_dir / "dataset.csv"
    all_jsonl = dataset_dir / "dataset.jsonl"
    train_csv = dataset_dir / "train.csv"
    val_csv = dataset_dir / "val.csv"
    train_jsonl = dataset_dir / "train.jsonl"
    val_jsonl = dataset_dir / "val.jsonl"
    manifest_path = dataset_dir / "manifest.json"

    train_rows = [r for r in flat_rows if r.get("split") == "train"]
    val_rows = [r for r in flat_rows if r.get("split") == "val"]

    _write_csv(all_csv, flat_rows, fieldnames)
    _write_jsonl(all_jsonl, flat_rows)
    _write_csv(train_csv, train_rows, fieldnames)
    _write_csv(val_csv, val_rows, fieldnames)
    _write_jsonl(train_jsonl, train_rows)
    _write_jsonl(val_jsonl, val_rows)

    manifest: Dict[str, Any] = {
        "dataset_name": dataset_name,
        "created_at": _utc_now_iso(),
        "target_objective": chosen_target,
        "split": {
            "val_ratio": max(0.0, min(float(val_ratio), 1.0)),
            "seed": int(split_seed),
        },
        "filters": {
            "only_success": bool(only_success),
        },
        "counts": {
            "rows_total": len(flat_rows),
            "rows_train": len(train_rows),
            "rows_val": len(val_rows),
            "rows_success": sum(1 for r in flat_rows if r.get("success")),
            "rows_failed": sum(1 for r in flat_rows if not r.get("success")),
            "rows_missing_target": sum(1 for r in flat_rows if r.get("target_value") is None),
        },
        "schema": {
            "metadata_fields": [
                "split",
                "source_kind",
                "source_path",
                "source_run_id",
                "study_name",
                "method",
                "seed",
                "timestamp",
                "run_index",
                "success",
                "failed",
                "error",
                "target_objective",
                "target_value",
            ],
            "parameter_fields": parameter_names,
            "objective_fields": objective_names,
            "csv_columns": list(fieldnames),
        },
        "source_run_ids": sorted({r.source_run_id for r in rows}),
        "sources": list(source_summaries),
        "outputs": {
            "dataset_csv": str(all_csv),
            "dataset_jsonl": str(all_jsonl),
            "train_csv": str(train_csv),
            "val_csv": str(val_csv),
            "train_jsonl": str(train_jsonl),
            "val_jsonl": str(val_jsonl),
            "manifest": str(manifest_path),
        },
    }

    _write_json(manifest_path, manifest)
    return manifest


def build_surrogate_dataset(
    *,
    input_paths: Sequence[str],
    output_root: str,
    dataset_name: Optional[str] = None,
    target_objective: Optional[str] = None,
    val_ratio: float = 0.2,
    split_seed: int = 42,
    only_success: bool = False,
) -> Dict[str, Any]:
    rows, source_summaries = load_rows_from_inputs(input_paths)
    return _materialize_dataset(
        rows=rows,
        source_summaries=source_summaries,
        output_root=output_root,
        dataset_name=dataset_name,
        target_objective=target_objective,
        val_ratio=val_ratio,
        split_seed=split_seed,
        only_success=only_success,
    )


def build_surrogate_dataset_from_payloads(
    *,
    payloads: Sequence[Tuple[str, Any]],
    output_root: str,
    dataset_name: Optional[str] = None,
    target_objective: Optional[str] = None,
    val_ratio: float = 0.2,
    split_seed: int = 42,
    only_success: bool = False,
) -> Dict[str, Any]:
    rows, source_summaries = load_rows_from_payloads(payloads)
    return _materialize_dataset(
        rows=rows,
        source_summaries=source_summaries,
        output_root=output_root,
        dataset_name=dataset_name,
        target_objective=target_objective,
        val_ratio=val_ratio,
        split_seed=split_seed,
        only_success=only_success,
    )


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export AIRPET study/optimizer runs into surrogate-training dataset files (CSV + JSONL)."
    )
    parser.add_argument(
        "--input",
        action="append",
        required=True,
        help="Input JSON file or directory (repeatable). Directories are scanned for version.json and *.json.",
    )
    parser.add_argument(
        "--output-root",
        default="surrogate/datasets",
        help="Root directory where the dataset folder is created.",
    )
    parser.add_argument(
        "--dataset-name",
        default=None,
        help="Dataset folder name (default: timestamp-based).",
    )
    parser.add_argument(
        "--target-objective",
        default=None,
        help="Objective name to use as training target. Auto-selected if omitted.",
    )
    parser.add_argument(
        "--val-ratio",
        type=float,
        default=0.2,
        help="Validation split ratio in [0, 1]. Default: 0.2",
    )
    parser.add_argument(
        "--split-seed",
        type=int,
        default=42,
        help="Random seed for train/val split. Default: 42",
    )
    parser.add_argument(
        "--only-success",
        action="store_true",
        help="Keep only successful runs before writing dataset files.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    manifest = build_surrogate_dataset(
        input_paths=args.input,
        output_root=args.output_root,
        dataset_name=args.dataset_name,
        target_objective=args.target_objective,
        val_ratio=args.val_ratio,
        split_seed=args.split_seed,
        only_success=args.only_success,
    )

    print(json.dumps({
        "success": True,
        "dataset_name": manifest["dataset_name"],
        "target_objective": manifest["target_objective"],
        "counts": manifest["counts"],
        "manifest": manifest["outputs"]["manifest"],
    }, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
