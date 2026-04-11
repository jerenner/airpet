from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np


SCORING_ARTIFACT_SCHEMA_VERSION = 1
SUPPORTED_SCORING_RUNTIME_QUANTITIES = ("energy_deposit",)


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


def _build_scoring_mesh_artifact(request: Dict[str, Any], hit_arrays: Dict[str, np.ndarray]) -> Dict[str, Any]:
    mesh = request["mesh"]
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
    sample_size = min(len(edep), len(pos_x), len(pos_y), len(pos_z))

    hit_count_total = int(sample_size)
    hit_count_in_mesh = 0
    if sample_size > 0:
        edep = edep[:sample_size]
        pos_x = pos_x[:sample_size]
        pos_y = pos_y[:sample_size]
        pos_z = pos_z[:sample_size]

        finite_mask = (
            np.isfinite(edep)
            & np.isfinite(pos_x)
            & np.isfinite(pos_y)
            & np.isfinite(pos_z)
        )
        in_mesh_mask = (
            finite_mask
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
            edep_hits = edep[in_mesh_mask]

            ix = np.floor((x_hits - min_corner["x"]) / voxel_size["x"]).astype(int)
            iy = np.floor((y_hits - min_corner["y"]) / voxel_size["y"]).astype(int)
            iz = np.floor((z_hits - min_corner["z"]) / voxel_size["z"]).astype(int)

            ix = np.clip(ix, 0, bins_x - 1)
            iy = np.clip(iy, 0, bins_y - 1)
            iz = np.clip(iz, 0, bins_z - 1)

            np.add.at(voxel_values, (ix, iy, iz), edep_hits)
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
        "quantity": request["quantity"],
        "mesh_id": str(mesh.get("mesh_id") or "").strip(),
        "mesh_name": str(mesh.get("name") or "").strip(),
        "mesh_type": str(mesh.get("mesh_type") or "").strip(),
        "reference_frame": str(mesh.get("reference_frame") or "").strip(),
        "units": {"position": "mm", "value": "MeV"},
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

    return {
        "schema_version": SCORING_ARTIFACT_SCHEMA_VERSION,
        "job_id": str(job_id or "").strip() or None,
        "source_output": Path(output_path).name,
        "summary": {
            "supported_quantities": list(runtime_plan["supported_quantities"]),
            "hit_count_total": int(hit_count_total),
            "enabled_mesh_count": int(runtime_plan["enabled_mesh_count"]),
            "enabled_tally_count": int(runtime_plan["enabled_tally_count"]),
            "generated_artifact_count": len(artifacts),
            "skipped_tally_count": int(runtime_plan["skipped_tally_count"]),
            "total_value": total_value,
        },
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

    if runtime_plan["artifact_request_count"] > 0:
        if not output_path.exists():
            raise FileNotFoundError(f"Missing scoring source output '{output_path.name}'.")

        bundle = build_scoring_artifact_bundle(
            str(output_path),
            scoring_payload,
            job_id=metadata.get("job_id"),
        )
        bundle_path = run_path / bundle_filename
        bundle_path.write_text(
            json.dumps(bundle, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        artifact_summary["artifact_bundle_path"] = bundle_path.name
        artifact_summary["generated_artifact_count"] = len(bundle.get("artifacts", []))
        artifact_summary["summary"] = deepcopy(bundle.get("summary", {}))

    metadata["scoring_artifacts"] = artifact_summary
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return artifact_summary
