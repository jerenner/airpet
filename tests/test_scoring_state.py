import hashlib
import json
from pathlib import Path
import sys
import types

from src.expression_evaluator import ExpressionEvaluator
from src.geometry_types import GeometryState, ScoringState


class _DummyOccObject:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return self

    def __getattr__(self, name):
        return self


def _install_occ_stubs():
    if "OCC" in sys.modules:
        return

    occ_module = types.ModuleType("OCC")
    occ_module.__path__ = []
    core_module = types.ModuleType("OCC.Core")
    core_module.__path__ = []

    sys.modules["OCC"] = occ_module
    sys.modules["OCC.Core"] = core_module

    module_specs = {
        "OCC.Core.STEPControl": {"STEPControl_Reader": _DummyOccObject},
        "OCC.Core.TopAbs": {
            "TopAbs_SOLID": 0,
            "TopAbs_FACE": 1,
            "TopAbs_REVERSED": 2,
        },
        "OCC.Core.TopExp": {"TopExp_Explorer": _DummyOccObject},
        "OCC.Core.BRep": {
            "BRep_Tool": type(
                "_BRepTool",
                (),
                {"Triangulation": staticmethod(lambda *args, **kwargs: None)},
            )
        },
        "OCC.Core.BRepMesh": {"BRepMesh_IncrementalMesh": _DummyOccObject},
        "OCC.Core.TopLoc": {"TopLoc_Location": _DummyOccObject},
        "OCC.Core.gp": {"gp_Trsf": _DummyOccObject},
        "OCC.Core.TDF": {"TDF_Label": _DummyOccObject, "TDF_LabelSequence": _DummyOccObject},
        "OCC.Core.XCAFDoc": {
            "XCAFDoc_DocumentTool": type(
                "_XCAFDocDocumentTool",
                (),
                {"ShapeTool": staticmethod(lambda *args, **kwargs: _DummyOccObject())},
            )
        },
        "OCC.Core.STEPCAFControl": {"STEPCAFControl_Reader": _DummyOccObject},
        "OCC.Core.TDocStd": {"TDocStd_Document": _DummyOccObject},
    }

    for module_name, attrs in module_specs.items():
        module = types.ModuleType(module_name)
        for attr_name, value in attrs.items():
            setattr(module, attr_name, value)
        sys.modules[module_name] = module


_install_occ_stubs()

from src.project_manager import ProjectManager


def test_scoring_state_defaults_and_roundtrip():
    state = GeometryState()

    assert state.scoring.to_dict() == {
        "schema_version": 1,
        "scoring_meshes": [],
        "tally_requests": [],
        "run_manifest_defaults": {
            "events": 1000,
            "threads": 1,
            "seed1": 0,
            "seed2": 0,
            "print_progress": 0,
            "save_hits": True,
            "save_hit_metadata": True,
            "save_particles": False,
            "production_cut": "1.0 mm",
            "hit_energy_threshold": "1 eV",
        },
    }
    assert state.to_dict()["scoring"] == state.scoring.to_dict()

    valid_payload = {
        "schema_version": 1,
        "scoring_meshes": [
            {
                "name": "dose_mesh",
                "mesh_type": "box",
                "reference_frame": "world",
                "geometry": {
                    "center_mm": {"x": "1.5", "y": -2, "z": 0},
                    "size_mm": {"x": "20", "y": 10, "z": "5.5"},
                },
                "bins": {"x": "12", "y": 6, "z": 3},
            }
        ],
        "tally_requests": [
            {
                "name": "dose_tally",
                "mesh_ref": {"name": "dose_mesh"},
                "quantity": "dose_deposit",
            }
        ],
        "run_manifest_defaults": {
            "events": "2400",
            "threads": 3,
            "seed1": "11",
            "seed2": 22,
            "print_progress": "120",
            "save_hits": False,
            "save_hit_metadata": False,
            "save_particles": True,
            "production_cut": "0.25 mm",
            "hit_energy_threshold": "5 eV",
        },
    }

    ok, err = ScoringState.validate(valid_payload)
    assert ok is True
    assert err is None

    loaded = GeometryState.from_dict({"scoring": valid_payload})
    scoring = loaded.scoring.to_dict()
    mesh = scoring["scoring_meshes"][0]
    tally = scoring["tally_requests"][0]

    assert scoring["schema_version"] == 1
    assert mesh["mesh_id"].startswith("scoring_mesh_")
    assert mesh["name"] == "dose_mesh"
    assert mesh["mesh_type"] == "box"
    assert mesh["reference_frame"] == "world"
    assert mesh["geometry"] == {
        "center_mm": {"x": 1.5, "y": -2.0, "z": 0.0},
        "size_mm": {"x": 20.0, "y": 10.0, "z": 5.5},
    }
    assert mesh["bins"] == {"x": 12, "y": 6, "z": 3}

    assert tally["tally_id"].startswith("scoring_tally_")
    assert tally["name"] == "dose_tally"
    assert tally["quantity"] == "dose_deposit"
    assert tally["mesh_ref"]["mesh_id"] == mesh["mesh_id"]
    assert tally["mesh_ref"]["name"] == "dose_mesh"

    assert scoring["run_manifest_defaults"] == {
        "events": 2400,
        "threads": 3,
        "seed1": 11,
        "seed2": 22,
        "print_progress": 120,
        "save_hits": False,
        "save_hit_metadata": False,
        "save_particles": True,
        "production_cut": "0.25 mm",
        "hit_energy_threshold": "5 eV",
    }
    assert loaded.scoring.to_summary_dict() == {
        "has_configured_scoring": True,
        "scoring_mesh_count": 1,
        "enabled_scoring_mesh_count": 1,
        "tally_request_count": 1,
        "enabled_tally_request_count": 1,
        "has_run_manifest_overrides": True,
        "run_manifest_defaults": scoring["run_manifest_defaults"],
        "summary_text": "1 of 1 scoring mesh(es) enabled; 1 of 1 tally request(s) enabled; Run manifest defaults: 2400 event(s), 3 thread(s)",
    }


def test_scoring_state_validation_and_invalid_entries_default_cleanly():
    invalid_payload = {
        "scoring_meshes": [
            {
                "mesh_id": "valid_mesh",
                "name": "valid_mesh",
                "geometry": {"size_mm": {"x": 12, "y": 8, "z": 4}},
                "bins": {"x": 4, "y": 4, "z": 2},
            },
            {
                "mesh_id": "bad_mesh",
                "name": "bad_mesh",
                "mesh_type": "cylindrical",
            },
        ],
        "tally_requests": [
            {
                "tally_id": "valid_tally",
                "mesh_ref": {"mesh_id": "valid_mesh"},
                "quantity": "track_length",
            },
            {
                "tally_id": "bad_tally",
                "mesh_ref": {"mesh_id": "missing_mesh"},
                "quantity": "dose_deposit",
            },
        ],
        "run_manifest_defaults": {
            "events": "bad",
        },
    }

    ok, err = ScoringState.validate(invalid_payload)
    assert ok is False
    assert err == "scoring.scoring_meshes[].mesh_type must be one of: box."

    loaded = GeometryState.from_dict({"scoring": invalid_payload})
    scoring = loaded.scoring.to_dict()

    assert scoring["scoring_meshes"] == [
        {
            "mesh_id": "valid_mesh",
            "name": "valid_mesh",
            "schema_version": 1,
            "enabled": True,
            "mesh_type": "box",
            "reference_frame": "world",
            "geometry": {
                "center_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
                "size_mm": {"x": 12.0, "y": 8.0, "z": 4.0},
            },
            "bins": {"x": 4, "y": 4, "z": 2},
        }
    ]
    assert scoring["tally_requests"] == [
        {
            "tally_id": "valid_tally",
            "name": "track_length_tally",
            "schema_version": 1,
            "enabled": True,
            "mesh_ref": {"mesh_id": "valid_mesh", "name": "valid_mesh"},
            "quantity": "track_length",
        }
    ]
    assert scoring["run_manifest_defaults"] == ScoringState().to_dict()["run_manifest_defaults"]


def test_update_object_property_replaces_saved_scoring_state_and_syncs_tallies():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()

    scoring_payload = {
        "scoring_meshes": [
            {
                "mesh_id": "mesh_main",
                "name": "mesh_main",
                "geometry": {
                    "center_mm": {"x": 1, "y": 2, "z": 3},
                    "size_mm": {"x": 40, "y": 20, "z": 10},
                },
                "bins": {"x": 8, "y": 4, "z": 2},
            }
        ],
        "tally_requests": [
            {
                "tally_id": "tally_energy",
                "name": "mesh_main_energy_deposit",
                "mesh_ref": {"mesh_id": "mesh_main", "name": "mesh_main"},
                "quantity": "energy_deposit",
            },
            {
                "tally_id": "tally_track_length",
                "name": "mesh_main_track_length",
                "mesh_ref": {"mesh_id": "mesh_main", "name": "mesh_main"},
                "quantity": "track_length",
            },
        ],
        "run_manifest_defaults": {
            "events": 2400,
            "threads": 3,
        },
    }

    success, error = pm.update_object_property("scoring", "scoring_state", "state", scoring_payload)
    assert success is True
    assert error is None
    assert pm.current_geometry_state.scoring.to_dict() == {
        "schema_version": 1,
        "scoring_meshes": [
            {
                "mesh_id": "mesh_main",
                "name": "mesh_main",
                "schema_version": 1,
                "enabled": True,
                "mesh_type": "box",
                "reference_frame": "world",
                "geometry": {
                    "center_mm": {"x": 1.0, "y": 2.0, "z": 3.0},
                    "size_mm": {"x": 40.0, "y": 20.0, "z": 10.0},
                },
                "bins": {"x": 8, "y": 4, "z": 2},
            }
        ],
        "tally_requests": [
            {
                "tally_id": "tally_energy",
                "name": "mesh_main_energy_deposit",
                "schema_version": 1,
                "enabled": True,
                "mesh_ref": {"mesh_id": "mesh_main", "name": "mesh_main"},
                "quantity": "energy_deposit",
            },
            {
                "tally_id": "tally_track_length",
                "name": "mesh_main_track_length",
                "schema_version": 1,
                "enabled": True,
                "mesh_ref": {"mesh_id": "mesh_main", "name": "mesh_main"},
                "quantity": "track_length",
            },
        ],
        "run_manifest_defaults": {
            "events": 2400,
            "threads": 3,
            "seed1": 0,
            "seed2": 0,
            "print_progress": 0,
            "save_hits": True,
            "save_hit_metadata": True,
            "save_particles": False,
            "production_cut": "1.0 mm",
            "hit_energy_threshold": "1 eV",
        },
    }


def test_update_object_property_rejects_invalid_scoring_state_payload():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()

    success, error = pm.update_object_property(
        "scoring",
        "scoring_state",
        "state",
        {
            "scoring_meshes": [
                {
                    "mesh_id": "mesh_main",
                    "name": "mesh_main",
                    "mesh_type": "cylindrical",
                }
            ]
        },
    )

    assert success is False
    assert error == "scoring.scoring_meshes[].mesh_type must be one of: box."
    assert pm.current_geometry_state.scoring.to_dict()["scoring_meshes"] == []


def test_generate_macro_records_scoring_contract_and_resolves_saved_run_manifest_defaults(tmp_path):
    pm = ProjectManager(ExpressionEvaluator())

    scoring_payload = {
        "scoring_meshes": [
            {
                "mesh_id": "mesh_main",
                "name": "mesh_main",
                "geometry": {"size_mm": {"x": 40, "y": 20, "z": 10}},
                "bins": {"x": 8, "y": 4, "z": 2},
            }
        ],
        "tally_requests": [
            {
                "tally_id": "tally_main",
                "name": "tally_main",
                "mesh_ref": {"mesh_id": "mesh_main"},
                "quantity": "energy_deposit",
            }
        ],
        "run_manifest_defaults": {
            "events": 12,
            "threads": 2,
            "seed1": 101,
            "seed2": 202,
            "print_progress": 3,
            "save_hits": True,
            "save_hit_metadata": False,
            "save_particles": True,
            "production_cut": "0.25 mm",
            "hit_energy_threshold": "7 eV",
        },
    }

    state = GeometryState()
    state.scoring = ScoringState.from_dict(scoring_payload)

    version_dir = tmp_path / "version"
    version_dir.mkdir()
    (version_dir / "version.json").write_text(json.dumps(state.to_dict()), encoding="utf-8")

    macro_path = Path(
        pm.generate_macro_file(
            "scoring-job",
            {"save_hits": False},
            str(tmp_path),
            str(tmp_path),
            str(version_dir),
        )
    )

    macro_text = macro_path.read_text(encoding="utf-8")
    metadata = json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))

    assert "/random/setSeeds 101 202" in macro_text
    assert "/run/setCut 0.25 mm" in macro_text
    assert "/g4pet/run/saveParticles true" in macro_text
    assert "/g4pet/run/saveHits true" in macro_text
    assert "/g4pet/run/saveHitMetadata false" in macro_text
    assert "/g4pet/run/hitEnergyThreshold 7 eV" in macro_text
    assert "/run/printProgress 3" in macro_text
    assert "/run/beamOn 12" in macro_text

    assert metadata["sim_options"] == {"save_hits": False}
    assert metadata["total_events"] == 12
    assert metadata["resolved_run_manifest"] == {
        "events": 12,
        "threads": 2,
        "seed1": 101,
        "seed2": 202,
        "print_progress": 3,
        "save_hits": True,
        "save_hit_metadata": False,
        "save_particles": True,
        "production_cut": "0.25 mm",
        "hit_energy_threshold": "7 eV",
    }
    assert metadata["scoring"] == state.scoring.to_dict()
    assert metadata["scoring_summary"] == state.scoring.to_summary_dict()
    assert metadata["scoring_runtime"] == {
        "schema_version": 1,
        "supported_quantities": ["energy_deposit", "n_of_step"],
        "artifact_request_count": 1,
        "skipped_tally_count": 0,
        "requires_hits": True,
        "skipped_tallies": [],
        "forced_run_manifest_overrides": {"save_hits": True},
    }
    run_manifest_summary = metadata["run_manifest_summary"]
    output_files = {
        entry["role"]: entry for entry in run_manifest_summary["output_files"]
    }
    expected_geometry_sha256 = hashlib.sha256(
        (tmp_path / "geometry.gdml").read_bytes()
    ).hexdigest()

    assert run_manifest_summary["schema_version"] == 1
    assert run_manifest_summary["job_id"] == "scoring-job"
    assert run_manifest_summary["version_id"] == "version"
    assert run_manifest_summary["resolved_run_manifest"] == metadata["resolved_run_manifest"]
    assert run_manifest_summary["execution_settings"] == {
        "physics_list": None,
        "optical_physics": False,
    }
    assert run_manifest_summary["geometry"] == {
        "path": "geometry.gdml",
        "exists": True,
        "sha256": expected_geometry_sha256,
    }
    assert run_manifest_summary["environment"]["summary"] == state.environment.to_summary_dict()
    assert run_manifest_summary["scoring"]["summary"] == state.scoring.to_summary_dict()
    assert run_manifest_summary["scoring"]["runtime"] == {
        "supported_quantities": ["energy_deposit", "n_of_step"],
        "artifact_request_count": 1,
        "skipped_tally_count": 0,
        "requires_hits": True,
        "forced_run_manifest_overrides": {"save_hits": True},
    }
    assert run_manifest_summary["artifact_bundle"] == {
        "path": "scoring_artifacts.json",
        "exists": False,
        "generated_artifact_count": 0,
        "skipped_tally_count": 0,
        "quantity_summaries": [],
        "source_output": {
            "path": "output.hdf5",
            "exists": False,
        },
    }
    assert output_files["metadata"]["exists"] is True
    assert output_files["macro"]["path"] == "run.mac"
    assert output_files["macro"]["exists"] is True
    assert output_files["geometry"]["sha256"] == expected_geometry_sha256
    assert output_files["hits"] == {"role": "hits", "path": "output.hdf5", "exists": False}
    assert output_files["scoring_bundle"] == {
        "role": "scoring_bundle",
        "path": "scoring_artifacts.json",
        "exists": False,
    }
    assert output_files["tracks"]["path"] == "tracks"
    assert output_files["tracks"]["exists"] is True
    assert output_files["tracks"]["is_directory"] is True
    assert run_manifest_summary["comparison_keys"]["geometry_sha256"] == expected_geometry_sha256
    assert len(run_manifest_summary["comparison_keys"]["environment_signature"]) == 64
    assert len(run_manifest_summary["comparison_keys"]["scoring_signature"]) == 64
    assert len(run_manifest_summary["comparison_keys"]["run_manifest_signature"]) == 64
    assert len(run_manifest_summary["comparison_keys"]["execution_signature"]) == 64
