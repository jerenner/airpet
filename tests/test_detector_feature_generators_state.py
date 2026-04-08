import json
import sys
import types

from src.expression_evaluator import ExpressionEvaluator
from src.geometry_types import GeometryState


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


def test_detector_feature_generator_contract_defaults_and_invalid_entries():
    state = GeometryState()
    assert state.detector_feature_generators == []
    assert state.to_dict()["detector_feature_generators"] == []

    loaded = GeometryState.from_dict(
        {
            "detector_feature_generators": [
                {
                    "generator_type": "rectangular_drilled_hole_array",
                    "target": {
                        "solid_ref": {"name": "collimator_block"},
                    },
                    "pattern": {
                        "count_x": "4",
                        "count_y": 3,
                        "pitch_mm": {"x": "7.5", "y": 6},
                    },
                    "hole": {
                        "diameter_mm": "1.5",
                        "depth_mm": 8,
                    },
                },
                {
                    "generator_id": "invalid-negative-count",
                    "generator_type": "rectangular_drilled_hole_array",
                    "target": {
                        "solid_ref": {"name": "ignored_block"},
                    },
                    "pattern": {
                        "count_x": 0,
                        "count_y": 1,
                        "pitch_mm": {"x": 5, "y": 5},
                    },
                    "hole": {
                        "diameter_mm": 1.0,
                        "depth_mm": 2.0,
                    },
                },
                {
                    "generator_id": "unsupported-kind",
                    "generator_type": "circular_drilled_hole_array",
                    "target": {
                        "solid_ref": {"name": "ignored_block"},
                    },
                    "pattern": {
                        "count_x": 1,
                        "count_y": 1,
                        "pitch_mm": {"x": 5, "y": 5},
                    },
                    "hole": {
                        "diameter_mm": 1.0,
                        "depth_mm": 2.0,
                    },
                },
            ]
        }
    )

    assert len(loaded.detector_feature_generators) == 1
    entry = loaded.detector_feature_generators[0]
    assert entry["generator_id"].startswith("detector_feature_generator_")
    assert entry["name"].startswith("rectangular_drilled_hole_array_")
    assert entry["schema_version"] == 1
    assert entry["generator_type"] == "rectangular_drilled_hole_array"
    assert entry["enabled"] is True
    assert entry["target"] == {
        "solid_ref": {"name": "collimator_block"},
        "logical_volume_refs": [],
    }
    assert entry["pattern"] == {
        "count_x": 4,
        "count_y": 3,
        "pitch_mm": {"x": 7.5, "y": 6.0},
        "origin_offset_mm": {"x": 0.0, "y": 0.0},
        "anchor": "target_center",
    }
    assert entry["hole"] == {
        "shape": "cylindrical",
        "diameter_mm": 1.5,
        "depth_mm": 8.0,
        "axis": "z",
        "drill_from": "positive_z_face",
    }
    assert entry["realization"] == {
        "mode": "boolean_subtraction",
        "status": "spec_only",
        "result_solid_ref": None,
        "generated_object_refs": {
            "solid_refs": [],
            "logical_volume_refs": [],
            "placement_refs": [],
        },
    }


def test_detector_feature_generator_contract_roundtrips_through_project_manager():
    valid_payload = {
        "generator_id": "dfg_rect_holes_fixture",
        "name": "fixture_collimator_holes",
        "schema_version": 1,
        "generator_type": "rectangular_drilled_hole_array",
        "enabled": True,
        "target": {
            "solid_ref": {"id": "solid-target-1", "name": "collimator_block"},
            "logical_volume_refs": [
                {"id": "lv-target-1", "name": "collimator_lv"},
                {"id": "lv-target-1", "name": "collimator_lv"},
            ],
        },
        "pattern": {
            "count_x": 5,
            "count_y": 4,
            "pitch_mm": {"x": 7.5, "y": 9.25},
            "origin_offset_mm": {"x": 1.25, "y": -2.5},
            "anchor": "target_center",
        },
        "hole": {
            "shape": "cylindrical",
            "diameter_mm": 2.0,
            "depth_mm": 12.5,
            "axis": "z",
            "drill_from": "positive_z_face",
        },
        "realization": {
            "mode": "boolean_subtraction",
            "status": "generated",
            "result_solid_ref": {"id": "solid-result-1", "name": "collimator_block_drilled"},
            "generated_object_refs": {
                "solid_refs": [
                    {"id": "solid-result-1", "name": "collimator_block_drilled"},
                    {"id": "solid-cutter-1", "name": "collimator_hole_cutter"},
                ],
                "logical_volume_refs": [
                    {"id": "lv-target-1", "name": "collimator_lv"},
                ],
                "placement_refs": [
                    {"id": "pv-target-1", "name": "collimator_pv"},
                ],
            },
        },
    }

    expected_payload = {
        "generator_id": "dfg_rect_holes_fixture",
        "name": "fixture_collimator_holes",
        "schema_version": 1,
        "generator_type": "rectangular_drilled_hole_array",
        "enabled": True,
        "target": {
            "solid_ref": {"id": "solid-target-1", "name": "collimator_block"},
            "logical_volume_refs": [
                {"id": "lv-target-1", "name": "collimator_lv"},
            ],
        },
        "pattern": {
            "count_x": 5,
            "count_y": 4,
            "pitch_mm": {"x": 7.5, "y": 9.25},
            "origin_offset_mm": {"x": 1.25, "y": -2.5},
            "anchor": "target_center",
        },
        "hole": {
            "shape": "cylindrical",
            "diameter_mm": 2.0,
            "depth_mm": 12.5,
            "axis": "z",
            "drill_from": "positive_z_face",
        },
        "realization": {
            "mode": "boolean_subtraction",
            "status": "generated",
            "result_solid_ref": {"id": "solid-result-1", "name": "collimator_block_drilled"},
            "generated_object_refs": {
                "solid_refs": [
                    {"id": "solid-result-1", "name": "collimator_block_drilled"},
                    {"id": "solid-cutter-1", "name": "collimator_hole_cutter"},
                ],
                "logical_volume_refs": [
                    {"id": "lv-target-1", "name": "collimator_lv"},
                ],
                "placement_refs": [
                    {"id": "pv-target-1", "name": "collimator_pv"},
                ],
            },
        },
    }

    state = GeometryState.from_dict({"detector_feature_generators": [valid_payload]})
    assert state.detector_feature_generators == [expected_payload]
    assert state.to_dict()["detector_feature_generators"] == [expected_payload]

    pm = ProjectManager(ExpressionEvaluator())
    pm.current_geometry_state.detector_feature_generators = [expected_payload]

    json_string = pm.save_project_to_json_string()
    saved_payload = json.loads(json_string)
    assert saved_payload["detector_feature_generators"] == [expected_payload]

    pm_round_tripped = ProjectManager(ExpressionEvaluator())
    pm_round_tripped.load_project_from_json_string(json_string)
    assert pm_round_tripped.current_geometry_state.detector_feature_generators == [expected_payload]
