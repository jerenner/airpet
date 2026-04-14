import hashlib
import json
from unittest.mock import patch

import numpy as np

from src.scoring_artifacts import write_scoring_artifact_bundle


def test_write_scoring_artifact_bundle_records_run_manifest_summary_without_h5py(tmp_path):
    run_dir = tmp_path / "version-summary" / "sim_runs" / "job-summary"
    run_dir.mkdir(parents=True)
    (run_dir / "run.mac").write_text("/run/beamOn 2\n", encoding="utf-8")
    (run_dir / "geometry.gdml").write_text("<gdml />\n", encoding="utf-8")
    (run_dir / "output.hdf5").write_text("stub", encoding="utf-8")
    (run_dir / "tracks").mkdir()

    metadata = {
        "job_id": "job-summary",
        "timestamp": "2026-04-11T12:30:00",
        "sim_options": {
            "physics_list": "FTFP_BERT",
            "optical_physics": True,
        },
        "resolved_run_manifest": {
            "events": 2,
            "threads": 1,
            "save_hits": True,
            "save_particles": False,
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

    fake_hit_arrays = {
        "edep": np.asarray([1.25, 2.75], dtype=float),
        "pos_x": np.asarray([-0.5, 0.5], dtype=float),
        "pos_y": np.asarray([-0.5, 0.5], dtype=float),
        "pos_z": np.asarray([-0.5, 0.5], dtype=float),
    }

    with patch("src.scoring_artifacts._load_hit_arrays", return_value=fake_hit_arrays):
        summary = write_scoring_artifact_bundle(str(run_dir))

    bundle = json.loads((run_dir / "scoring_artifacts.json").read_text(encoding="utf-8"))
    updated_metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
    expected_geometry_sha256 = hashlib.sha256(
        (run_dir / "geometry.gdml").read_bytes()
    ).hexdigest()
    run_manifest_summary = bundle["run_manifest_summary"]
    output_files = {
        entry["role"]: entry for entry in run_manifest_summary["output_files"]
    }

    assert summary["artifact_bundle_path"] == "scoring_artifacts.json"
    assert summary["generated_artifact_count"] == 1
    assert bundle["summary"]["generated_artifact_count"] == 1
    assert bundle["summary"]["total_value"] == 4.0
    assert run_manifest_summary["version_id"] == "version-summary"
    assert run_manifest_summary["execution_settings"] == {
        "physics_list": "FTFP_BERT",
        "optical_physics": True,
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
    assert updated_metadata["run_manifest_summary"] == run_manifest_summary
