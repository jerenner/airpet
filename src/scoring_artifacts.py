from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


SCORING_ARTIFACT_SCHEMA_VERSION = 1
RUN_MANIFEST_SUMMARY_SCHEMA_VERSION = 1
SCORING_RUN_SUMMARY_SCHEMA_VERSION = 1
_SCORING_RUNTIME_VALUE_UNITS = {
    "energy_deposit": "MeV",
    "n_of_step": "steps",
}
SUPPORTED_SCORING_RUNTIME_QUANTITIES = tuple(_SCORING_RUNTIME_VALUE_UNITS.keys())


def _round_scalar(value: Any, digits: int = 12) -> float:
    numeric = float(value)
    if abs(numeric) < 1e-15:
        numeric = 0.0
    return round(numeric, digits)


def _round_vector(mapping: Dict[str, Any]) -> Dict[str, float]:
    return {
        "x": _round_scalar(mapping.get("x", 0.0)),
        "y": _round_scalar(mapping.get("y", 0.0)),
        "z": _round_scalar(mapping.get("z", 0.0)),
    }


def _coerce_non_negative_int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized >= 0 else default


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return bool(value)


def _normalize_string(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _pluralize(count: int, singular: str, plural: Optional[str] = None) -> str:
    normalized_count = _coerce_non_negative_int(count, 0)
    normalized_plural = plural or f"{singular}s"
    noun = singular if normalized_count == 1 else normalized_plural
    return f"{normalized_count} {noun}"


def _format_summary_number(value: Any, digits: int = 6) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    if not np.isfinite(numeric):
        numeric = 0.0
    rounded = round(numeric, digits)
    if abs(rounded) < 1e-12:
        rounded = 0.0
    text = f"{rounded:.{digits}f}".rstrip("0").rstrip(".")
    return text or "0"


def _format_scoring_quantity_label(quantity: Any) -> str:
    normalized = _normalize_string(quantity)
    if not normalized:
        normalized = "energy_deposit"
    return normalized.replace("_", " ")


def _format_scoring_result_value(value: Any, unit: Any = "") -> str:
    unit_text = _normalize_string(unit)
    value_text = _format_summary_number(value)
    return f"{value_text} {unit_text}".strip()


def _normalize_artifact_quantity_summary(entry: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(entry, dict):
        return None

    quantity = _normalize_string(entry.get("quantity"))
    if not quantity:
        return None

    total_value = entry.get("total_value", 0.0)
    try:
        total_value = float(total_value)
    except (TypeError, ValueError):
        total_value = 0.0
    if not np.isfinite(total_value):
        total_value = 0.0

    unit = _normalize_string(entry.get("unit"))
    generated_artifact_count = _coerce_non_negative_int(
        entry.get("generated_artifact_count"),
        0,
    )

    return {
        "quantity": quantity,
        "label": _format_scoring_quantity_label(quantity),
        "unit": unit,
        "generated_artifact_count": generated_artifact_count,
        "total_value": round(total_value, 6),
        "total_value_text": _format_scoring_result_value(total_value, unit),
    }


def _stable_json_sha256(payload: Any) -> str:
    serialized = json.dumps(
        payload if payload is not None else {},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _file_sha256(path: Path) -> Optional[str]:
    if not path.exists() or not path.is_file():
        return None

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _summarize_run_output(
    run_path: Path,
    role: str,
    relative_path: str,
    *,
    include_sha256: bool = False,
) -> Dict[str, Any]:
    candidate_path = run_path / relative_path
    entry = {
        "role": role,
        "path": relative_path,
        "exists": candidate_path.exists(),
    }
    if not candidate_path.exists():
        return entry

    entry["is_directory"] = candidate_path.is_dir()
    if candidate_path.is_file():
        entry["size_bytes"] = int(candidate_path.stat().st_size)
        if include_sha256:
            digest = _file_sha256(candidate_path)
            if digest:
                entry["sha256"] = digest
    return entry


def _infer_version_id_from_run_dir(run_path: Path) -> Optional[str]:
    if run_path.parent.name != "sim_runs":
        return None

    version_id = str(run_path.parent.parent.name or "").strip()
    return version_id or None


def _mesh_lookup(scoring_payload: Dict[str, Any]) -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]]]:
    meshes_by_id: Dict[str, Dict[str, Any]] = {}
    meshes_by_name: Dict[str, Dict[str, Any]] = {}

    for mesh in scoring_payload.get("scoring_meshes", []) or []:
        if not isinstance(mesh, dict) or not mesh.get("enabled", True):
            continue

        mesh_id = str(mesh.get("mesh_id") or "").strip()
        mesh_name = str(mesh.get("name") or "").strip()
        if mesh_id:
            meshes_by_id[mesh_id] = mesh
        if mesh_name and mesh_name not in meshes_by_name:
            meshes_by_name[mesh_name] = mesh

    return meshes_by_id, meshes_by_name


def build_scoring_runtime_plan(scoring_payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    scoring = scoring_payload if isinstance(scoring_payload, dict) else {}
    meshes_by_id, meshes_by_name = _mesh_lookup(scoring)
    supported_requests: List[Dict[str, Any]] = []
    skipped_tallies: List[Dict[str, Any]] = []
    enabled_tally_count = 0

    for tally in scoring.get("tally_requests", []) or []:
        if not isinstance(tally, dict) or not tally.get("enabled", True):
            continue

        enabled_tally_count += 1
        mesh_ref = tally.get("mesh_ref") if isinstance(tally.get("mesh_ref"), dict) else {}
        mesh_id = str(mesh_ref.get("mesh_id") or "").strip()
        mesh_name = str(mesh_ref.get("name") or "").strip()
        mesh = meshes_by_id.get(mesh_id) or meshes_by_name.get(mesh_name)
        quantity = str(tally.get("quantity") or "").strip()

        if mesh is None:
            skipped_tallies.append(
                {
                    "tally_id": str(tally.get("tally_id") or "").strip(),
                    "name": str(tally.get("name") or "").strip(),
                    "quantity": quantity,
                    "reason": "mesh_not_found_or_disabled",
                }
            )
            continue

        if quantity not in SUPPORTED_SCORING_RUNTIME_QUANTITIES:
            skipped_tallies.append(
                {
                    "tally_id": str(tally.get("tally_id") or "").strip(),
                    "name": str(tally.get("name") or "").strip(),
                    "mesh_id": str(mesh.get("mesh_id") or "").strip(),
                    "mesh_name": str(mesh.get("name") or "").strip(),
                    "quantity": quantity,
                    "reason": "quantity_not_supported_in_scoring_mesh_mvp",
                }
            )
            continue

        supported_requests.append(
            {
                "artifact_id": str(tally.get("tally_id") or "").strip()
                or f"artifact_{len(supported_requests) + 1}",
                "tally_id": str(tally.get("tally_id") or "").strip(),
                "tally_name": str(tally.get("name") or "").strip(),
                "quantity": quantity,
                "mesh": deepcopy(mesh),
            }
        )

    return {
        "schema_version": SCORING_ARTIFACT_SCHEMA_VERSION,
        "supported_quantities": list(SUPPORTED_SCORING_RUNTIME_QUANTITIES),
        "enabled_mesh_count": len(meshes_by_id),
        "enabled_tally_count": enabled_tally_count,
        "artifact_request_count": len(supported_requests),
        "requires_hits": bool(supported_requests),
        "artifact_requests": supported_requests,
        "skipped_tallies": skipped_tallies,
        "skipped_tally_count": len(skipped_tallies),
    }


def scoring_runtime_requires_hits(scoring_payload: Optional[Dict[str, Any]]) -> bool:
    return bool(build_scoring_runtime_plan(scoring_payload).get("requires_hits"))


def build_run_manifest_summary(
    metadata: Optional[Dict[str, Any]],
    run_dir: str,
    *,
    version_id: Optional[str] = None,
) -> Dict[str, Any]:
    metadata_payload = metadata if isinstance(metadata, dict) else {}
    run_path = Path(run_dir)

    resolved_run_manifest = deepcopy(
        metadata_payload.get("resolved_run_manifest")
        if isinstance(metadata_payload.get("resolved_run_manifest"), dict)
        else {}
    )
    environment_payload = (
        metadata_payload.get("environment")
        if isinstance(metadata_payload.get("environment"), dict)
        else {}
    )
    environment_summary = deepcopy(
        metadata_payload.get("environment_summary")
        if isinstance(metadata_payload.get("environment_summary"), dict)
        else {}
    )
    scoring_payload = (
        metadata_payload.get("scoring")
        if isinstance(metadata_payload.get("scoring"), dict)
        else {}
    )
    scoring_runtime = (
        metadata_payload.get("scoring_runtime")
        if isinstance(metadata_payload.get("scoring_runtime"), dict)
        else build_scoring_runtime_plan(scoring_payload)
    )
    scoring_summary = deepcopy(
        metadata_payload.get("scoring_summary")
        if isinstance(metadata_payload.get("scoring_summary"), dict)
        else {
            "enabled_mesh_count": int(scoring_runtime.get("enabled_mesh_count", 0) or 0),
            "enabled_tally_count": int(scoring_runtime.get("enabled_tally_count", 0) or 0),
            "artifact_request_count": int(scoring_runtime.get("artifact_request_count", 0) or 0),
            "skipped_tally_count": int(scoring_runtime.get("skipped_tally_count", 0) or 0),
        }
    )
    sim_options = (
        metadata_payload.get("sim_options")
        if isinstance(metadata_payload.get("sim_options"), dict)
        else {}
    )
    execution_settings = {
        "physics_list": sim_options.get("physics_list"),
        "optical_physics": bool(sim_options.get("optical_physics", False)),
    }

    output_files = [
        _summarize_run_output(run_path, "metadata", "metadata.json"),
        _summarize_run_output(run_path, "macro", "run.mac"),
        _summarize_run_output(run_path, "geometry", "geometry.gdml", include_sha256=True),
        _summarize_run_output(run_path, "hits", "output.hdf5"),
        _summarize_run_output(run_path, "scoring_bundle", "scoring_artifacts.json"),
        _summarize_run_output(run_path, "tracks", "tracks"),
    ]

    geometry_output = next(
        (entry for entry in output_files if entry.get("role") == "geometry"),
        {"path": "geometry.gdml", "exists": False},
    )
    source_output = next(
        (entry for entry in output_files if entry.get("role") == "hits"),
        {"path": "output.hdf5", "exists": False},
    )
    scoring_bundle_output = next(
        (entry for entry in output_files if entry.get("role") == "scoring_bundle"),
        {"path": "scoring_artifacts.json", "exists": False},
    )

    scoring_artifacts = (
        metadata_payload.get("scoring_artifacts")
        if isinstance(metadata_payload.get("scoring_artifacts"), dict)
        else {}
    )
    scoring_artifacts_summary = (
        scoring_artifacts.get("summary")
        if isinstance(scoring_artifacts.get("summary"), dict)
        else {}
    )

    scoring_runtime_summary = {
        "supported_quantities": list(scoring_runtime.get("supported_quantities", [])),
        "artifact_request_count": int(scoring_runtime.get("artifact_request_count", 0) or 0),
        "skipped_tally_count": int(scoring_runtime.get("skipped_tally_count", 0) or 0),
        "requires_hits": bool(scoring_runtime.get("requires_hits")),
    }
    forced_run_manifest_overrides = scoring_runtime.get("forced_run_manifest_overrides")
    if isinstance(forced_run_manifest_overrides, dict) and forced_run_manifest_overrides:
        scoring_runtime_summary["forced_run_manifest_overrides"] = deepcopy(
            forced_run_manifest_overrides
        )

    environment_signature = _stable_json_sha256(environment_payload)
    scoring_signature = _stable_json_sha256(scoring_payload)
    run_manifest_signature = _stable_json_sha256(resolved_run_manifest)
    execution_signature = _stable_json_sha256(execution_settings)

    return {
        "schema_version": RUN_MANIFEST_SUMMARY_SCHEMA_VERSION,
        "job_id": str(metadata_payload.get("job_id") or "").strip() or None,
        "timestamp": metadata_payload.get("timestamp"),
        "version_id": str(
            version_id
            or metadata_payload.get("version_id")
            or _infer_version_id_from_run_dir(run_path)
            or ""
        ).strip()
        or None,
        "resolved_run_manifest": resolved_run_manifest,
        "execution_settings": execution_settings,
        "geometry": {
            "path": geometry_output.get("path"),
            "exists": bool(geometry_output.get("exists")),
            "sha256": geometry_output.get("sha256"),
        },
        "environment": {
            "summary": environment_summary,
            "signature": environment_signature,
        },
        "scoring": {
            "summary": scoring_summary,
            "runtime": scoring_runtime_summary,
            "signature": scoring_signature,
        },
        "artifact_bundle": {
            "path": str(
                scoring_artifacts.get("artifact_bundle_path")
                or scoring_bundle_output.get("path")
                or "scoring_artifacts.json"
            ).strip()
            or "scoring_artifacts.json",
            "exists": bool(scoring_bundle_output.get("exists")),
            "generated_artifact_count": int(
                scoring_artifacts.get("generated_artifact_count", 0) or 0
            ),
            "skipped_tally_count": int(
                scoring_artifacts.get("skipped_tally_count", 0) or 0
            ),
            "quantity_summaries": deepcopy(
                scoring_artifacts_summary.get("quantity_summaries", [])
            ),
            "source_output": {
                "path": source_output.get("path"),
                "exists": bool(source_output.get("exists")),
            },
        },
        "output_files": output_files,
        "comparison_keys": {
            "geometry_sha256": geometry_output.get("sha256"),
            "environment_signature": environment_signature,
            "scoring_signature": scoring_signature,
            "run_manifest_signature": run_manifest_signature,
            "execution_signature": execution_signature,
        },
    }


def build_scoring_run_summary(
    metadata: Optional[Dict[str, Any]],
    *,
    scoring_bundle: Optional[Dict[str, Any]] = None,
    run_manifest_summary: Optional[Dict[str, Any]] = None,
    version_id: Optional[str] = None,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    metadata_payload = metadata if isinstance(metadata, dict) else {}
    manifest_summary = (
        run_manifest_summary if isinstance(run_manifest_summary, dict) else {}
    )
    bundle_payload = scoring_bundle if isinstance(scoring_bundle, dict) else {}

    manifest_scoring = (
        manifest_summary.get("scoring")
        if isinstance(manifest_summary.get("scoring"), dict)
        else {}
    )
    scoring_summary = (
        metadata_payload.get("scoring_summary")
        if isinstance(metadata_payload.get("scoring_summary"), dict)
        else manifest_scoring.get("summary")
        if isinstance(manifest_scoring.get("summary"), dict)
        else {}
    )
    scoring_runtime = (
        metadata_payload.get("scoring_runtime")
        if isinstance(metadata_payload.get("scoring_runtime"), dict)
        else manifest_scoring.get("runtime")
        if isinstance(manifest_scoring.get("runtime"), dict)
        else {}
    )
    scoring_artifacts = (
        metadata_payload.get("scoring_artifacts")
        if isinstance(metadata_payload.get("scoring_artifacts"), dict)
        else {}
    )
    artifact_bundle = (
        manifest_summary.get("artifact_bundle")
        if isinstance(manifest_summary.get("artifact_bundle"), dict)
        else {}
    )
    bundle_summary = (
        bundle_payload.get("summary")
        if isinstance(bundle_payload.get("summary"), dict)
        else scoring_artifacts.get("summary")
        if isinstance(scoring_artifacts.get("summary"), dict)
        else {}
    )
    resolved_run_manifest = (
        manifest_summary.get("resolved_run_manifest")
        if isinstance(manifest_summary.get("resolved_run_manifest"), dict)
        else {}
    )
    execution_settings = (
        manifest_summary.get("execution_settings")
        if isinstance(manifest_summary.get("execution_settings"), dict)
        else {}
    )

    raw_quantity_summaries = bundle_summary.get("quantity_summaries")
    if not isinstance(raw_quantity_summaries, list):
        raw_quantity_summaries = artifact_bundle.get("quantity_summaries")

    quantity_summaries = sorted(
        [
            normalized
            for normalized in (
                _normalize_artifact_quantity_summary(entry)
                for entry in (raw_quantity_summaries or [])
            )
            if normalized is not None
        ],
        key=lambda entry: entry["quantity"],
    )

    enabled_mesh_count = _coerce_non_negative_int(
        scoring_summary.get(
            "enabled_scoring_mesh_count",
            scoring_summary.get("enabled_mesh_count"),
        ),
        0,
    )
    enabled_tally_count = _coerce_non_negative_int(
        scoring_summary.get(
            "enabled_tally_request_count",
            scoring_summary.get("enabled_tally_count"),
        ),
        0,
    )
    artifact_request_count = _coerce_non_negative_int(
        scoring_runtime.get("artifact_request_count"),
        0,
    )
    generated_artifact_count = _coerce_non_negative_int(
        scoring_artifacts.get(
            "generated_artifact_count",
            bundle_summary.get(
                "generated_artifact_count",
                artifact_bundle.get("generated_artifact_count"),
            ),
        ),
        0,
    )
    skipped_tally_count = _coerce_non_negative_int(
        scoring_artifacts.get(
            "skipped_tally_count",
            scoring_runtime.get("skipped_tally_count"),
        ),
        0,
    )
    has_configured_scoring = _coerce_bool(
        scoring_summary.get(
            "has_configured_scoring",
            enabled_mesh_count > 0 or enabled_tally_count > 0,
        )
    )
    has_scoring_outputs = bool(quantity_summaries) or generated_artifact_count > 0

    setup_summary_text = _normalize_string(scoring_summary.get("summary_text"))
    if not setup_summary_text:
        setup_summary_text = (
            f"{_pluralize(enabled_mesh_count, 'enabled scoring mesh')} across "
            f"{_pluralize(enabled_tally_count, 'enabled tally request')}."
        )

    bundle_path = _normalize_string(
        scoring_artifacts.get("artifact_bundle_path")
        or artifact_bundle.get("path")
        or "scoring_artifacts.json"
    )
    bundle_exists = _coerce_bool(
        artifact_bundle.get("exists")
        if artifact_bundle.get("exists") is not None
        else bool(bundle_payload)
    )
    source_output = (
        artifact_bundle.get("source_output")
        if isinstance(artifact_bundle.get("source_output"), dict)
        else {}
    )
    source_output_exists = _coerce_bool(source_output.get("exists"))

    if quantity_summaries:
        summary_text = " · ".join(
            f"{entry['label']} {entry['total_value_text']}"
            for entry in quantity_summaries
        )
        status = "artifacts_ready"
    elif generated_artifact_count > 0:
        summary_text = f"{_pluralize(generated_artifact_count, 'scoring artifact')} recorded for this run."
        status = "artifacts_ready"
    elif artifact_request_count > 0:
        summary_text = (
            f"Requested {_pluralize(artifact_request_count, 'scoring artifact')}, "
            "but no scoring bundle was recorded."
        )
        status = "bundle_missing"
    elif has_configured_scoring:
        summary_text = "Scoring is configured for this run, but no runtime scoring artifacts were recorded."
        status = "configured_no_outputs"
    else:
        summary_text = "No scoring artifacts recorded for this run."
        status = "no_scoring"

    detail_lines = [
        (
            f"{_pluralize(enabled_mesh_count, 'enabled mesh')} · "
            f"{_pluralize(enabled_tally_count, 'enabled tally request')}"
        ),
        f"Bundle: {bundle_path}" if bundle_exists else "Bundle: not recorded",
    ]
    if skipped_tally_count > 0:
        detail_lines.append(
            f"Skipped {_pluralize(skipped_tally_count, 'unsupported tally request')}."
        )

    return {
        "schema_version": SCORING_RUN_SUMMARY_SCHEMA_VERSION,
        "version_id": _normalize_string(
            version_id
            or metadata_payload.get("version_id")
            or manifest_summary.get("version_id")
        )
        or None,
        "job_id": _normalize_string(
            job_id
            or metadata_payload.get("job_id")
            or manifest_summary.get("job_id")
            or bundle_payload.get("job_id")
        )
        or None,
        "timestamp": metadata_payload.get("timestamp") or manifest_summary.get("timestamp"),
        "status": status,
        "summary_text": summary_text,
        "setup_summary_text": setup_summary_text,
        "has_configured_scoring": has_configured_scoring,
        "has_scoring_outputs": has_scoring_outputs,
        "total_events": _coerce_non_negative_int(
            metadata_payload.get("total_events", resolved_run_manifest.get("events")),
            0,
        ),
        "threads": _coerce_non_negative_int(resolved_run_manifest.get("threads"), 0),
        "physics_list": execution_settings.get("physics_list"),
        "optical_physics": _coerce_bool(execution_settings.get("optical_physics")),
        "enabled_mesh_count": enabled_mesh_count,
        "enabled_tally_count": enabled_tally_count,
        "artifact_request_count": artifact_request_count,
        "generated_artifact_count": generated_artifact_count,
        "skipped_tally_count": skipped_tally_count,
        "bundle_path": bundle_path,
        "bundle_exists": bundle_exists,
        "source_output_exists": source_output_exists,
        "quantity_summaries": quantity_summaries,
        "detail_lines": detail_lines,
        "comparison_keys": deepcopy(
            manifest_summary.get("comparison_keys")
            if isinstance(manifest_summary.get("comparison_keys"), dict)
            else {}
        ),
        "scoring_setup": {
            "summary": deepcopy(scoring_summary),
            "runtime": deepcopy(scoring_runtime),
        },
    }


def _load_hit_arrays(output_path: str) -> Dict[str, np.ndarray]:
    import h5py

    def _get_entries_count(group: Any) -> Optional[int]:
        if "entries" not in group:
            return None
        try:
            dataset = group["entries"]
            if dataset.shape == ():
                return int(dataset[()])
            return int(dataset[0])
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

    def _resolve_hdf5_path_array(handle: Any, dataset_path: str) -> np.ndarray:
        path = str(dataset_path or "").strip().strip("/")
        if not path or path not in handle:
            return np.array([])

        node = handle[path]
        parent_path = "/".join(path.split("/")[:-1])
        entries_count = None
        if parent_path and parent_path in handle and isinstance(handle[parent_path], h5py.Group):
            entries_count = _get_entries_count(handle[parent_path])

        return _read_hdf5_node_array(node, entries_count=entries_count)

    with h5py.File(output_path, "r") as handle:
        return {
            "edep": np.asarray(
                _resolve_hdf5_path_array(handle, "default_ntuples/Hits/Edep"),
                dtype=float,
            ),
            "pos_x": np.asarray(
                _resolve_hdf5_path_array(handle, "default_ntuples/Hits/PosX"),
                dtype=float,
            ),
            "pos_y": np.asarray(
                _resolve_hdf5_path_array(handle, "default_ntuples/Hits/PosY"),
                dtype=float,
            ),
            "pos_z": np.asarray(
                _resolve_hdf5_path_array(handle, "default_ntuples/Hits/PosZ"),
                dtype=float,
            ),
        }


def _build_artifact_quantity_summaries(artifacts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    summaries_by_quantity: Dict[str, Dict[str, Any]] = {}

    for artifact in artifacts:
        quantity = str(artifact.get("quantity") or "").strip()
        if not quantity:
            continue

        units = artifact.get("units") if isinstance(artifact.get("units"), dict) else {}
        value_unit = str(units.get("value") or "").strip() or None
        total_value = float(artifact.get("summary", {}).get("total_value", 0.0) or 0.0)

        if quantity not in summaries_by_quantity:
            summaries_by_quantity[quantity] = {
                "quantity": quantity,
                "unit": value_unit,
                "generated_artifact_count": 0,
                "total_value": 0.0,
            }

        summaries_by_quantity[quantity]["generated_artifact_count"] += 1
        summaries_by_quantity[quantity]["total_value"] += total_value

    return [
        {
            **summary,
            "total_value": _round_scalar(summary["total_value"]),
        }
        for summary in summaries_by_quantity.values()
    ]


def _build_scoring_mesh_artifact(request: Dict[str, Any], hit_arrays: Dict[str, np.ndarray]) -> Dict[str, Any]:
    mesh = request["mesh"]
    quantity = str(request.get("quantity") or "").strip()
    if quantity not in _SCORING_RUNTIME_VALUE_UNITS:
        raise ValueError(f"Unsupported runtime scoring quantity '{quantity}'.")

    mesh_geometry = mesh.get("geometry", {}) if isinstance(mesh.get("geometry"), dict) else {}
    center_mm = mesh_geometry.get("center_mm", {}) if isinstance(mesh_geometry.get("center_mm"), dict) else {}
    size_mm = mesh_geometry.get("size_mm", {}) if isinstance(mesh_geometry.get("size_mm"), dict) else {}
    bins = mesh.get("bins", {}) if isinstance(mesh.get("bins"), dict) else {}

    size_x = float(size_mm.get("x", 0.0))
    size_y = float(size_mm.get("y", 0.0))
    size_z = float(size_mm.get("z", 0.0))
    bins_x = int(bins.get("x", 1))
    bins_y = int(bins.get("y", 1))
    bins_z = int(bins.get("z", 1))

    min_corner = {
        "x": float(center_mm.get("x", 0.0)) - (size_x / 2.0),
        "y": float(center_mm.get("y", 0.0)) - (size_y / 2.0),
        "z": float(center_mm.get("z", 0.0)) - (size_z / 2.0),
    }
    max_corner = {
        "x": min_corner["x"] + size_x,
        "y": min_corner["y"] + size_y,
        "z": min_corner["z"] + size_z,
    }
    voxel_size = {
        "x": size_x / bins_x,
        "y": size_y / bins_y,
        "z": size_z / bins_z,
    }

    voxel_values = np.zeros((bins_x, bins_y, bins_z), dtype=float)
    edep = hit_arrays["edep"]
    pos_x = hit_arrays["pos_x"]
    pos_y = hit_arrays["pos_y"]
    pos_z = hit_arrays["pos_z"]
    sample_arrays = [pos_x, pos_y, pos_z]
    if quantity == "energy_deposit":
        sample_arrays.append(edep)
    sample_size = min((len(array) for array in sample_arrays), default=0)

    hit_count_total = int(sample_size)
    hit_count_in_mesh = 0
    if sample_size > 0:
        pos_x = pos_x[:sample_size]
        pos_y = pos_y[:sample_size]
        pos_z = pos_z[:sample_size]

        position_finite_mask = (
            np.isfinite(pos_x)
            & np.isfinite(pos_y)
            & np.isfinite(pos_z)
        )
        value_finite_mask = np.ones(sample_size, dtype=bool)
        if quantity == "energy_deposit":
            edep = edep[:sample_size]
            value_finite_mask = np.isfinite(edep)

        in_mesh_mask = (
            position_finite_mask
            & value_finite_mask
            & (pos_x >= min_corner["x"])
            & (pos_x <= max_corner["x"])
            & (pos_y >= min_corner["y"])
            & (pos_y <= max_corner["y"])
            & (pos_z >= min_corner["z"])
            & (pos_z <= max_corner["z"])
        )

        if np.any(in_mesh_mask):
            x_hits = pos_x[in_mesh_mask]
            y_hits = pos_y[in_mesh_mask]
            z_hits = pos_z[in_mesh_mask]
            if quantity == "energy_deposit":
                voxel_samples = np.asarray(edep[in_mesh_mask], dtype=float)
            else:
                voxel_samples = np.ones(int(np.count_nonzero(in_mesh_mask)), dtype=float)

            ix = np.floor((x_hits - min_corner["x"]) / voxel_size["x"]).astype(int)
            iy = np.floor((y_hits - min_corner["y"]) / voxel_size["y"]).astype(int)
            iz = np.floor((z_hits - min_corner["z"]) / voxel_size["z"]).astype(int)

            ix = np.clip(ix, 0, bins_x - 1)
            iy = np.clip(iy, 0, bins_y - 1)
            iz = np.clip(iz, 0, bins_z - 1)

            np.add.at(voxel_values, (ix, iy, iz), voxel_samples)
            hit_count_in_mesh = int(np.count_nonzero(in_mesh_mask))

    nonzero_voxels = []
    for ix, iy, iz in np.argwhere(voxel_values != 0.0):
        nonzero_voxels.append(
            {
                "index": {"x": int(ix), "y": int(iy), "z": int(iz)},
                "center_mm": {
                    "x": _round_scalar(min_corner["x"] + ((ix + 0.5) * voxel_size["x"])),
                    "y": _round_scalar(min_corner["y"] + ((iy + 0.5) * voxel_size["y"])),
                    "z": _round_scalar(min_corner["z"] + ((iz + 0.5) * voxel_size["z"])),
                },
                "value": _round_scalar(voxel_values[ix, iy, iz]),
            }
        )

    nested_values = np.vectorize(_round_scalar)(voxel_values).tolist()
    total_value = _round_scalar(np.sum(voxel_values))

    return {
        "artifact_id": request["artifact_id"],
        "tally_id": request["tally_id"],
        "tally_name": request["tally_name"],
        "quantity": quantity,
        "mesh_id": str(mesh.get("mesh_id") or "").strip(),
        "mesh_name": str(mesh.get("name") or "").strip(),
        "mesh_type": str(mesh.get("mesh_type") or "").strip(),
        "reference_frame": str(mesh.get("reference_frame") or "").strip(),
        "units": {"position": "mm", "value": _SCORING_RUNTIME_VALUE_UNITS[quantity]},
        "geometry": {
            "center_mm": _round_vector(center_mm),
            "size_mm": _round_vector(size_mm),
            "min_corner_mm": _round_vector(min_corner),
            "max_corner_mm": _round_vector(max_corner),
            "voxel_size_mm": _round_vector(voxel_size),
            "bins": {
                "x": bins_x,
                "y": bins_y,
                "z": bins_z,
            },
        },
        "summary": {
            "hit_count_total": hit_count_total,
            "hit_count_in_mesh": hit_count_in_mesh,
            "total_value": total_value,
            "nonzero_voxel_count": len(nonzero_voxels),
        },
        "voxel_values": nested_values,
        "nonzero_voxels": nonzero_voxels,
    }


def build_scoring_artifact_bundle(
    output_path: str,
    scoring_payload: Optional[Dict[str, Any]],
    *,
    job_id: Optional[str] = None,
) -> Dict[str, Any]:
    runtime_plan = build_scoring_runtime_plan(scoring_payload)
    hit_arrays = _load_hit_arrays(output_path)
    artifacts = [
        _build_scoring_mesh_artifact(request, hit_arrays)
        for request in runtime_plan["artifact_requests"]
    ]

    hit_count_total = min(
        len(hit_arrays["edep"]),
        len(hit_arrays["pos_x"]),
        len(hit_arrays["pos_y"]),
        len(hit_arrays["pos_z"]),
    )
    total_value = _round_scalar(
        sum(
            artifact.get("summary", {}).get("total_value", 0.0)
            for artifact in artifacts
        )
    )
    quantity_summaries = _build_artifact_quantity_summaries(artifacts)

    summary = {
        "schema_version": SCORING_ARTIFACT_SCHEMA_VERSION,
        "supported_quantities": list(runtime_plan["supported_quantities"]),
        "hit_count_total": int(hit_count_total),
        "enabled_mesh_count": int(runtime_plan["enabled_mesh_count"]),
        "enabled_tally_count": int(runtime_plan["enabled_tally_count"]),
        "generated_artifact_count": len(artifacts),
        "skipped_tally_count": int(runtime_plan["skipped_tally_count"]),
        "quantity_summaries": quantity_summaries,
    }
    if len(quantity_summaries) == 1:
        summary["total_value"] = total_value
        summary["value_unit"] = quantity_summaries[0].get("unit")

    return {
        "schema_version": SCORING_ARTIFACT_SCHEMA_VERSION,
        "job_id": str(job_id or "").strip() or None,
        "source_output": Path(output_path).name,
        "summary": summary,
        "artifacts": artifacts,
        "skipped_tallies": deepcopy(runtime_plan["skipped_tallies"]),
    }


def write_scoring_artifact_bundle(
    run_dir: str,
    *,
    metadata_filename: str = "metadata.json",
    output_filename: str = "output.hdf5",
    bundle_filename: str = "scoring_artifacts.json",
) -> Optional[Dict[str, Any]]:
    run_path = Path(run_dir)
    metadata_path = run_path / metadata_filename
    output_path = run_path / output_filename

    if not metadata_path.exists():
        return None

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    scoring_payload = metadata.get("scoring")
    runtime_plan = build_scoring_runtime_plan(scoring_payload)

    artifact_summary = {
        "schema_version": SCORING_ARTIFACT_SCHEMA_VERSION,
        "artifact_request_count": int(runtime_plan["artifact_request_count"]),
        "generated_artifact_count": 0,
        "skipped_tally_count": int(runtime_plan["skipped_tally_count"]),
        "supported_quantities": list(runtime_plan["supported_quantities"]),
        "requires_hits": bool(runtime_plan["requires_hits"]),
        "artifact_bundle_path": None,
        "skipped_tallies": deepcopy(runtime_plan["skipped_tallies"]),
    }

    bundle = None
    bundle_path = run_path / bundle_filename

    if runtime_plan["artifact_request_count"] > 0:
        if not output_path.exists():
            raise FileNotFoundError(f"Missing scoring source output '{output_path.name}'.")

        bundle = build_scoring_artifact_bundle(
            str(output_path),
            scoring_payload,
            job_id=metadata.get("job_id"),
        )
        bundle_path.write_text(
            json.dumps(bundle, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        artifact_summary["artifact_bundle_path"] = bundle_path.name
        artifact_summary["generated_artifact_count"] = len(bundle.get("artifacts", []))
        artifact_summary["summary"] = deepcopy(bundle.get("summary", {}))

    metadata["scoring_artifacts"] = artifact_summary
    metadata["run_manifest_summary"] = build_run_manifest_summary(metadata, str(run_path))
    if bundle is not None:
        bundle["run_manifest_summary"] = deepcopy(metadata["run_manifest_summary"])
        bundle_path.write_text(
            json.dumps(bundle, indent=2, sort_keys=True),
            encoding="utf-8",
        )
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return artifact_summary
