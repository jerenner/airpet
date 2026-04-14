import hashlib
import json

import h5py
import numpy as np

from src.scoring_artifacts import write_scoring_artifact_bundle


def test_write_scoring_artifact_bundle_builds_energy_deposit_mesh_and_updates_metadata(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run.mac").write_text("/run/beamOn 3\n", encoding="utf-8")
    (run_dir / "geometry.gdml").write_text("<gdml />\n", encoding="utf-8")
    (run_dir / "tracks").mkdir()

    metadata = {
        "job_id": "mesh-job",
        "timestamp": "2026-04-11T12:15:00",
        "sim_options": {
            "physics_list": "FTFP_BERT",
            "optical_physics": False,
        },
        "resolved_run_manifest": {
            "events": 3,
            "threads": 1,
            "save_hits": True,
        },
        "environment": {
            "schema_version": 1,
            "global_uniform_magnetic_field": {
                "enabled": False,
            },
        },
        "environment_summary": {
            "has_active_controls": False,
            "active_control_count": 0,
            "summary_text": "No environment overrides",
        },
        "scoring": {
            "schema_version": 1,
            "scoring_meshes": [
                {
                    "mesh_id": "mesh_main",
                    "name": "mesh_main",
                    "enabled": True,
                    "mesh_type": "box",
                    "reference_frame": "world",
                    "geometry": {
                        "center_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "size_mm": {"x": 4.0, "y": 4.0, "z": 4.0},
                    },
                    "bins": {"x": 2, "y": 2, "z": 2},
                }
            ],
            "tally_requests": [
                {
                    "tally_id": "tally_main",
                    "name": "tally_main",
                    "enabled": True,
                    "mesh_ref": {"mesh_id": "mesh_main", "name": "mesh_main"},
                    "quantity": "energy_deposit",
                }
            ],
            "run_manifest_defaults": {},
        },
        "scoring_summary": {
            "enabled_mesh_count": 1,
            "enabled_tally_count": 1,
            "summary_text": "1 scoring mesh; 1 tally",
        },
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with h5py.File(run_dir / "output.hdf5", "w") as handle:
        hits = handle.create_group("default_ntuples/Hits")
        hits.create_dataset("entries", data=3)
        hits.create_dataset("Edep", data=np.array([1.5, 2.0, 5.0], dtype=float))
        hits.create_dataset("PosX", data=np.array([-0.9, 0.1, 3.1], dtype=float))
        hits.create_dataset("PosY", data=np.array([-0.9, 0.1, 0.0], dtype=float))
        hits.create_dataset("PosZ", data=np.array([-0.9, 0.1, 0.0], dtype=float))

    summary = write_scoring_artifact_bundle(str(run_dir))
    assert summary == {
        "schema_version": 1,
        "artifact_request_count": 1,
        "generated_artifact_count": 1,
        "skipped_tally_count": 0,
        "supported_quantities": ["energy_deposit", "n_of_step"],
        "requires_hits": True,
        "artifact_bundle_path": "scoring_artifacts.json",
        "skipped_tallies": [],
        "summary": {
            "supported_quantities": ["energy_deposit", "n_of_step"],
            "hit_count_total": 3,
            "enabled_mesh_count": 1,
            "enabled_tally_count": 1,
            "generated_artifact_count": 1,
            "skipped_tally_count": 0,
            "quantity_summaries": [
                {
                    "quantity": "energy_deposit",
                    "unit": "MeV",
                    "generated_artifact_count": 1,
                    "total_value": 3.5,
                }
            ],
            "total_value": 3.5,
            "value_unit": "MeV",
        },
    }

    bundle = json.loads((run_dir / "scoring_artifacts.json").read_text(encoding="utf-8"))
    run_manifest_summary = bundle["run_manifest_summary"]
    output_files = {
        entry["role"]: entry for entry in run_manifest_summary["output_files"]
    }
    expected_geometry_sha256 = hashlib.sha256(
        (run_dir / "geometry.gdml").read_bytes()
    ).hexdigest()

    assert bundle["summary"]["total_value"] == 3.5
    assert bundle["summary"]["value_unit"] == "MeV"
    assert bundle["summary"]["quantity_summaries"] == [
        {
            "quantity": "energy_deposit",
            "unit": "MeV",
            "generated_artifact_count": 1,
            "total_value": 3.5,
        }
    ]
    assert bundle["summary"]["generated_artifact_count"] == 1
    assert bundle["artifacts"][0]["summary"] == {
        "hit_count_total": 3,
        "hit_count_in_mesh": 2,
        "total_value": 3.5,
        "nonzero_voxel_count": 2,
    }
    assert bundle["artifacts"][0]["voxel_values"] == [
        [[1.5, 0.0], [0.0, 0.0]],
        [[0.0, 0.0], [0.0, 2.0]],
    ]
    assert bundle["artifacts"][0]["nonzero_voxels"] == [
        {
            "index": {"x": 0, "y": 0, "z": 0},
            "center_mm": {"x": -1.0, "y": -1.0, "z": -1.0},
            "value": 1.5,
        },
        {
            "index": {"x": 1, "y": 1, "z": 1},
            "center_mm": {"x": 1.0, "y": 1.0, "z": 1.0},
            "value": 2.0,
        },
    ]
    assert run_manifest_summary["job_id"] == "mesh-job"
    assert run_manifest_summary["execution_settings"] == {
        "physics_list": "FTFP_BERT",
        "optical_physics": False,
    }
    assert run_manifest_summary["geometry"] == {
        "path": "geometry.gdml",
        "exists": True,
        "sha256": expected_geometry_sha256,
    }
    assert run_manifest_summary["artifact_bundle"] == {
        "path": "scoring_artifacts.json",
        "exists": True,
        "generated_artifact_count": 1,
        "skipped_tally_count": 0,
        "quantity_summaries": bundle["summary"]["quantity_summaries"],
        "source_output": {
            "path": "output.hdf5",
            "exists": True,
        },
    }
    assert output_files["hits"]["exists"] is True
    assert output_files["scoring_bundle"]["exists"] is True
    assert output_files["tracks"]["exists"] is True
    assert output_files["geometry"]["sha256"] == expected_geometry_sha256

    updated_metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    assert updated_metadata["scoring_artifacts"]["artifact_bundle_path"] == "scoring_artifacts.json"
    assert updated_metadata["run_manifest_summary"] == run_manifest_summary


def test_write_scoring_artifact_bundle_tracks_quantity_summaries_for_mixed_supported_tallies(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    metadata = {
        "job_id": "mixed-job",
        "scoring": {
            "schema_version": 1,
            "scoring_meshes": [
                {
                    "mesh_id": "mesh_main",
                    "name": "mesh_main",
                    "enabled": True,
                    "mesh_type": "box",
                    "reference_frame": "world",
                    "geometry": {
                        "center_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "size_mm": {"x": 4.0, "y": 4.0, "z": 4.0},
                    },
                    "bins": {"x": 2, "y": 2, "z": 2},
                }
            ],
            "tally_requests": [
                {
                    "tally_id": "tally_energy",
                    "name": "tally_energy",
                    "enabled": True,
                    "mesh_ref": {"mesh_id": "mesh_main", "name": "mesh_main"},
                    "quantity": "energy_deposit",
                },
                {
                    "tally_id": "tally_steps",
                    "name": "tally_steps",
                    "enabled": True,
                    "mesh_ref": {"mesh_id": "mesh_main", "name": "mesh_main"},
                    "quantity": "n_of_step",
                },
            ],
            "run_manifest_defaults": {},
        },
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    with h5py.File(run_dir / "output.hdf5", "w") as handle:
        hits = handle.create_group("default_ntuples/Hits")
        hits.create_dataset("entries", data=3)
        hits.create_dataset("Edep", data=np.array([1.5, 2.0, 5.0], dtype=float))
        hits.create_dataset("PosX", data=np.array([-0.9, 0.1, 3.1], dtype=float))
        hits.create_dataset("PosY", data=np.array([-0.9, 0.1, 0.0], dtype=float))
        hits.create_dataset("PosZ", data=np.array([-0.9, 0.1, 0.0], dtype=float))

    summary = write_scoring_artifact_bundle(str(run_dir))
    assert summary == {
        "schema_version": 1,
        "artifact_request_count": 2,
        "generated_artifact_count": 2,
        "skipped_tally_count": 0,
        "supported_quantities": ["energy_deposit", "n_of_step"],
        "requires_hits": True,
        "artifact_bundle_path": "scoring_artifacts.json",
        "skipped_tallies": [],
        "summary": {
            "supported_quantities": ["energy_deposit", "n_of_step"],
            "hit_count_total": 3,
            "enabled_mesh_count": 1,
            "enabled_tally_count": 2,
            "generated_artifact_count": 2,
            "skipped_tally_count": 0,
            "quantity_summaries": [
                {
                    "quantity": "energy_deposit",
                    "unit": "MeV",
                    "generated_artifact_count": 1,
                    "total_value": 3.5,
                },
                {
                    "quantity": "n_of_step",
                    "unit": "steps",
                    "generated_artifact_count": 1,
                    "total_value": 2.0,
                },
            ],
        },
    }

    bundle = json.loads((run_dir / "scoring_artifacts.json").read_text(encoding="utf-8"))
    assert "total_value" not in bundle["summary"]
    assert bundle["summary"]["quantity_summaries"] == [
        {
            "quantity": "energy_deposit",
            "unit": "MeV",
            "generated_artifact_count": 1,
            "total_value": 3.5,
        },
        {
            "quantity": "n_of_step",
            "unit": "steps",
            "generated_artifact_count": 1,
            "total_value": 2.0,
        },
    ]
    assert bundle["artifacts"][1]["quantity"] == "n_of_step"
    assert bundle["artifacts"][1]["units"] == {"position": "mm", "value": "steps"}
    assert bundle["artifacts"][1]["summary"] == {
        "hit_count_total": 3,
        "hit_count_in_mesh": 2,
        "total_value": 2.0,
        "nonzero_voxel_count": 2,
    }
    assert bundle["artifacts"][1]["voxel_values"] == [
        [[1.0, 0.0], [0.0, 0.0]],
        [[0.0, 0.0], [0.0, 1.0]],
    ]


def test_write_scoring_artifact_bundle_records_unsupported_tallies_without_bundle(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    metadata = {
        "job_id": "unsupported-job",
        "scoring": {
            "schema_version": 1,
            "scoring_meshes": [
                {
                    "mesh_id": "mesh_main",
                    "name": "mesh_main",
                    "enabled": True,
                    "mesh_type": "box",
                    "reference_frame": "world",
                    "geometry": {
                        "center_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
                        "size_mm": {"x": 4.0, "y": 4.0, "z": 4.0},
                    },
                    "bins": {"x": 2, "y": 2, "z": 2},
                }
            ],
            "tally_requests": [
                {
                    "tally_id": "dose_main",
                    "name": "dose_main",
                    "enabled": True,
                    "mesh_ref": {"mesh_id": "mesh_main", "name": "mesh_main"},
                    "quantity": "dose_deposit",
                }
            ],
            "run_manifest_defaults": {},
        },
    }
    (run_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    summary = write_scoring_artifact_bundle(str(run_dir))
    assert summary == {
        "schema_version": 1,
        "artifact_request_count": 0,
        "generated_artifact_count": 0,
        "skipped_tally_count": 1,
        "supported_quantities": ["energy_deposit", "n_of_step"],
        "requires_hits": False,
        "artifact_bundle_path": None,
        "skipped_tallies": [
            {
                "tally_id": "dose_main",
                "name": "dose_main",
                "mesh_id": "mesh_main",
                "mesh_name": "mesh_main",
                "quantity": "dose_deposit",
                "reason": "quantity_not_supported_in_scoring_mesh_mvp",
            }
        ],
    }
    assert not (run_dir / "scoring_artifacts.json").exists()
