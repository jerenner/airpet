from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import h5py
import numpy as np

from .objective_formula import evaluate_objective_formula


def _get_entries_count(group: h5py.Group) -> Optional[int]:
    if "entries" not in group:
        return None
    try:
        dset = group["entries"]
        if dset.shape == ():
            return int(dset[()])
        return int(dset[0])
    except Exception:
        return None


def _read_hdf5_node_array(node: Any, entries_count: Optional[int] = None) -> np.ndarray:
    if isinstance(node, h5py.Group):
        if "pages" in node and isinstance(node["pages"], h5py.Dataset):
            arr = node["pages"][:]
        else:
            return np.array([])
    elif isinstance(node, h5py.Dataset):
        arr = node[:]
    else:
        return np.array([])

    if entries_count is not None and len(arr) >= entries_count:
        return arr[:entries_count]
    return arr


def _resolve_hdf5_path_array(f: h5py.File, dataset_path: str) -> np.ndarray:
    p = str(dataset_path or "").strip().strip("/")
    if not p:
        return np.array([])

    if p not in f:
        return np.array([])

    node = f[p]
    parent_path = "/".join(p.split("/")[:-1])
    entries_count = None
    if parent_path and parent_path in f and isinstance(f[parent_path], h5py.Group):
        entries_count = _get_entries_count(f[parent_path])

    return _read_hdf5_node_array(node, entries_count=entries_count)


def _decode_particle_names(arr: np.ndarray) -> np.ndarray:
    out: List[str] = []
    for x in arr:
        if isinstance(x, bytes):
            out.append(x.decode("utf-8"))
        else:
            out.append(str(x))
    return np.array(out, dtype=object)


def _reduce_array(arr: np.ndarray, reduce: str, q: Optional[float] = None) -> float:
    op = (reduce or "sum").strip().lower()

    if op == "count":
        return float(len(arr))
    if len(arr) == 0:
        return 0.0

    arr_num = np.asarray(arr)

    if op == "sum":
        return float(np.sum(arr_num))
    if op == "mean":
        return float(np.mean(arr_num))
    if op == "max":
        return float(np.max(arr_num))
    if op == "min":
        return float(np.min(arr_num))
    if op == "std":
        return float(np.std(arr_num))
    if op == "count_nonzero":
        return float(np.count_nonzero(arr_num))
    if op == "fraction_nonzero":
        return float(np.count_nonzero(arr_num) / max(1, len(arr_num)))
    if op == "quantile":
        qq = 0.5 if q is None else float(q)
        qq = max(0.0, min(1.0, qq))
        return float(np.quantile(arr_num, qq))

    raise ValueError(f"Unsupported reduce operation '{reduce}'.")


def extract_objective_values_from_hdf5(
    output_path: str,
    objectives: List[Dict[str, Any]],
    context: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, float], List[str], List[str]]:
    objective_values: Dict[str, float] = {}
    warnings: List[str] = []
    context = dict(context or {})

    available_metrics = [
        "total_hits",
        "edep_sum",
        "edep_mean",
        "edep_max",
        "unique_copyno_count",
        "particle_unique_count",
        "particle_fraction",
        "hdf5_reduce",
        "context_value",
        "constant",
        "formula",
    ]

    with h5py.File(output_path, "r") as f:
        edep = _resolve_hdf5_path_array(f, "default_ntuples/Hits/Edep")
        copy_no = _resolve_hdf5_path_array(f, "default_ntuples/Hits/CopyNo")
        particle_name_ds = _resolve_hdf5_path_array(f, "default_ntuples/Hits/ParticleName")

        for i, obj in enumerate(objectives or []):
            if not isinstance(obj, dict):
                warnings.append(f"Objective at index {i} is not an object; skipped.")
                continue

            metric = obj.get("metric")
            name = obj.get("name", metric or f"objective_{i}")

            try:
                if metric == "total_hits":
                    objective_values[name] = float(len(edep))
                elif metric == "edep_sum":
                    objective_values[name] = float(np.sum(edep)) if len(edep) > 0 else 0.0
                elif metric == "edep_mean":
                    objective_values[name] = float(np.mean(edep)) if len(edep) > 0 else 0.0
                elif metric == "edep_max":
                    objective_values[name] = float(np.max(edep)) if len(edep) > 0 else 0.0
                elif metric == "unique_copyno_count":
                    objective_values[name] = float(len(np.unique(copy_no))) if len(copy_no) > 0 else 0.0
                elif metric == "particle_unique_count":
                    if len(particle_name_ds) == 0:
                        objective_values[name] = 0.0
                    else:
                        p_names = _decode_particle_names(particle_name_ds)
                        objective_values[name] = float(len(set(p_names.tolist())))
                elif metric == "particle_fraction":
                    target_particle = (obj.get("particle") or "").strip()
                    if not target_particle or len(particle_name_ds) == 0:
                        objective_values[name] = 0.0
                    else:
                        p_names = _decode_particle_names(particle_name_ds)
                        objective_values[name] = float(np.mean(p_names == target_particle))
                elif metric == "hdf5_reduce":
                    dataset_path = obj.get("dataset_path")
                    if not dataset_path:
                        raise ValueError("hdf5_reduce requires field 'dataset_path'.")
                    arr = _resolve_hdf5_path_array(f, str(dataset_path))
                    objective_values[name] = _reduce_array(arr, reduce=obj.get("reduce", "sum"), q=obj.get("q"))
                elif metric == "context_value":
                    key = obj.get("key")
                    if not key:
                        raise ValueError("context_value requires field 'key'.")
                    objective_values[name] = float(context.get(key, obj.get("default", 0.0)))
                elif metric == "constant":
                    objective_values[name] = float(obj.get("value", 0.0))
                elif metric == "formula":
                    expr = obj.get("expression") or obj.get("expr")
                    if not expr:
                        raise ValueError("formula metric requires 'expression'.")
                    env = {}
                    env.update(context)
                    env.update(objective_values)
                    objective_values[name] = float(evaluate_objective_formula(expr, env))
                else:
                    warnings.append(f"Unsupported objective metric '{metric}' for '{name}'; skipped.")
            except Exception as e:
                warnings.append(f"Objective '{name}' failed: {e}")

    return objective_values, warnings, available_metrics
