import json
from pathlib import Path
import sys
import types

import pytest

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


def _make_pm():
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    return pm


def _normalize_detector_feature_generators(raw_generators):
    return GeometryState.from_dict(
        {"detector_feature_generators": raw_generators}
    ).detector_feature_generators


def _load_patterned_hole_starter_pm():
    pm = ProjectManager(ExpressionEvaluator())
    starter_path = (
        Path(__file__).resolve().parents[1]
        / "examples"
        / "detector_feature_generators"
        / "patterned_hole_starter.project.json"
    )
    with starter_path.open("r", encoding="utf-8") as handle:
        pm.load_project_from_json_string(handle.read())
    return pm


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
                    "generator_type": "spiral_drilled_hole_array",
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


def test_circular_detector_feature_generator_contract_defaults():
    loaded = GeometryState.from_dict(
        {
            "detector_feature_generators": [
                {
                    "generator_type": "circular_drilled_hole_array",
                    "target": {
                        "solid_ref": {"name": "circular_collimator_block"},
                    },
                    "pattern": {
                        "hole_count": "6",
                        "radius_mm": "12.5",
                        "orientation_deg": "15",
                        "origin_offset_mm": {"x": "1.5", "y": -2},
                    },
                    "hole": {
                        "diameter_mm": "2.5",
                        "depth_mm": 7,
                    },
                },
            ]
        }
    )

    assert len(loaded.detector_feature_generators) == 1
    entry = loaded.detector_feature_generators[0]
    assert entry["generator_id"].startswith("detector_feature_generator_")
    assert entry["name"].startswith("circular_drilled_hole_array_")
    assert entry["generator_type"] == "circular_drilled_hole_array"
    assert entry["target"] == {
        "solid_ref": {"name": "circular_collimator_block"},
        "logical_volume_refs": [],
    }
    assert entry["pattern"] == {
        "count": 6,
        "radius_mm": 12.5,
        "orientation_deg": 15.0,
        "origin_offset_mm": {"x": 1.5, "y": -2.0},
        "anchor": "target_center",
    }
    assert entry["hole"] == {
        "shape": "cylindrical",
        "diameter_mm": 2.5,
        "depth_mm": 7.0,
        "axis": "z",
        "drill_from": "positive_z_face",
    }


def test_layered_detector_stack_contract_defaults():
    loaded = GeometryState.from_dict(
        {
            "detector_feature_generators": [
                {
                    "generator_type": "layered_detector_stack",
                    "target": {
                        "parent_logical_volume_ref": {"name": "World"},
                    },
                    "stack": {
                        "module_size_mm": {"x": "24", "y": 18},
                        "module_count": "3",
                    },
                    "layers": {
                        "absorber": {
                            "material": "G4_Pb",
                            "thickness_mm": "4.5",
                        },
                        "sensor": {
                            "material_ref": "G4_Si",
                            "thickness_mm": 1,
                        },
                        "support": {
                            "material_ref": "G4_Al",
                            "thickness_mm": 2.5,
                        },
                    },
                },
            ]
        }
    )

    assert len(loaded.detector_feature_generators) == 1
    entry = loaded.detector_feature_generators[0]
    assert entry["generator_id"].startswith("detector_feature_generator_")
    assert entry["name"].startswith("layered_detector_stack_")
    assert entry["generator_type"] == "layered_detector_stack"
    assert entry["target"] == {
        "parent_logical_volume_ref": {"name": "World"},
    }
    assert entry["stack"] == {
        "module_size_mm": {"x": 24.0, "y": 18.0},
        "module_count": 3,
        "module_pitch_mm": 8.0,
        "origin_offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
        "anchor": "target_center",
    }
    assert entry["layers"] == {
        "absorber": {
            "material_ref": "G4_Pb",
            "thickness_mm": 4.5,
            "is_sensitive": False,
        },
        "sensor": {
            "material_ref": "G4_Si",
            "thickness_mm": 1.0,
            "is_sensitive": True,
        },
        "support": {
            "material_ref": "G4_Al",
            "thickness_mm": 2.5,
            "is_sensitive": False,
        },
    }
    assert entry["realization"] == {
        "mode": "layered_stack",
        "status": "spec_only",
        "result_solid_ref": None,
        "generated_object_refs": {
            "solid_refs": [],
            "logical_volume_refs": [],
            "placement_refs": [],
        },
    }


def test_tiled_sensor_array_contract_defaults():
    loaded = GeometryState.from_dict(
        {
            "detector_feature_generators": [
                {
                    "generator_type": "tiled_sensor_array",
                    "target": {
                        "parent_logical_volume_ref": {"name": "World"},
                    },
                    "array": {
                        "count_x": "4",
                        "count_y": 3,
                        "origin_offset_mm": {"x": "1.5", "y": -2, "z": "3.25"},
                    },
                    "sensor": {
                        "size_mm": {"x": "6.0", "y": 4.5},
                        "thickness_mm": "1.2",
                        "material": "G4_Si",
                    },
                },
            ]
        }
    )

    assert len(loaded.detector_feature_generators) == 1
    entry = loaded.detector_feature_generators[0]
    assert entry["generator_id"].startswith("detector_feature_generator_")
    assert entry["name"].startswith("tiled_sensor_array_")
    assert entry["generator_type"] == "tiled_sensor_array"
    assert entry["target"] == {
        "parent_logical_volume_ref": {"name": "World"},
    }
    assert entry["array"] == {
        "count_x": 4,
        "count_y": 3,
        "pitch_mm": {"x": 6.0, "y": 4.5},
        "origin_offset_mm": {"x": 1.5, "y": -2.0, "z": 3.25},
        "anchor": "target_center",
    }
    assert entry["sensor"] == {
        "size_mm": {"x": 6.0, "y": 4.5},
        "thickness_mm": 1.2,
        "material_ref": "G4_Si",
        "is_sensitive": True,
    }
    assert entry["realization"] == {
        "mode": "placement_array",
        "status": "spec_only",
        "result_solid_ref": None,
        "generated_object_refs": {
            "solid_refs": [],
            "logical_volume_refs": [],
            "placement_refs": [],
        },
    }


def test_support_rib_array_contract_defaults():
    loaded = GeometryState.from_dict(
        {
            "detector_feature_generators": [
                {
                    "generator_type": "support_rib_array",
                    "target": {
                        "parent_logical_volume_ref": {"name": "World"},
                    },
                    "array": {
                        "count": "4",
                        "linear_pitch_mm": "8.5",
                        "axis": "y",
                        "origin_offset_mm": {"x": "1.5", "y": -2, "z": "3.25"},
                    },
                    "rib": {
                        "width_mm": "1.2",
                        "height_mm": 4,
                        "material": "G4_Al",
                    },
                },
            ]
        }
    )

    assert len(loaded.detector_feature_generators) == 1
    entry = loaded.detector_feature_generators[0]
    assert entry["generator_id"].startswith("detector_feature_generator_")
    assert entry["name"].startswith("support_rib_array_")
    assert entry["generator_type"] == "support_rib_array"
    assert entry["target"] == {
        "parent_logical_volume_ref": {"name": "World"},
    }
    assert entry["array"] == {
        "count": 4,
        "linear_pitch_mm": 8.5,
        "axis": "y",
        "origin_offset_mm": {"x": 1.5, "y": -2.0, "z": 3.25},
        "anchor": "target_center",
    }
    assert entry["rib"] == {
        "width_mm": 1.2,
        "height_mm": 4.0,
        "material_ref": "G4_Al",
        "is_sensitive": False,
    }
    assert entry["realization"] == {
        "mode": "placement_array",
        "status": "spec_only",
        "result_solid_ref": None,
        "generated_object_refs": {
            "solid_refs": [],
            "logical_volume_refs": [],
            "placement_refs": [],
        },
    }


def test_annular_shield_sleeve_contract_defaults():
    loaded = GeometryState.from_dict(
        {
            "detector_feature_generators": [
                {
                    "generator_type": "annular_shield_sleeve",
                    "target": {
                        "parent_logical_volume_ref": {"name": "World"},
                    },
                    "shield": {
                        "inner_radius_mm": "9.5",
                        "outer_radius_mm": 14,
                        "length_mm": "42",
                        "material": "G4_Pb",
                        "origin_offset_mm": {"x": "1.5", "y": -2, "z": "3.25"},
                    },
                },
            ]
        }
    )

    assert len(loaded.detector_feature_generators) == 1
    entry = loaded.detector_feature_generators[0]
    assert entry["generator_id"].startswith("detector_feature_generator_")
    assert entry["name"].startswith("annular_shield_sleeve_")
    assert entry["generator_type"] == "annular_shield_sleeve"
    assert entry["target"] == {
        "parent_logical_volume_ref": {"name": "World"},
    }
    assert entry["shield"] == {
        "inner_radius_mm": 9.5,
        "outer_radius_mm": 14.0,
        "length_mm": 42.0,
        "material_ref": "G4_Pb",
        "origin_offset_mm": {"x": 1.5, "y": -2.0, "z": 3.25},
        "anchor": "target_center",
    }
    assert entry["realization"] == {
        "mode": "placement_array",
        "status": "spec_only",
        "result_solid_ref": None,
        "generated_object_refs": {
            "solid_refs": [],
            "logical_volume_refs": [],
            "placement_refs": [],
        },
    }


def test_channel_cut_array_contract_defaults():
    loaded = GeometryState.from_dict(
        {
            "detector_feature_generators": [
                {
                    "generator_type": "channel_cut_array",
                    "target": {
                        "solid_ref": {"name": "channel_block"},
                    },
                    "array": {
                        "count": "3",
                        "linear_pitch_mm": "7.5",
                        "axis": "x",
                        "origin_offset_mm": {"x": "1.0", "y": -1.5},
                    },
                    "channel": {
                        "width_mm": "1.25",
                        "depth_mm": 6,
                    },
                },
            ]
        }
    )

    assert len(loaded.detector_feature_generators) == 1
    entry = loaded.detector_feature_generators[0]
    assert entry["generator_id"].startswith("detector_feature_generator_")
    assert entry["name"].startswith("channel_cut_array_")
    assert entry["generator_type"] == "channel_cut_array"
    assert entry["target"] == {
        "solid_ref": {"name": "channel_block"},
        "logical_volume_refs": [],
    }
    assert entry["array"] == {
        "count": 3,
        "linear_pitch_mm": 7.5,
        "axis": "x",
        "origin_offset_mm": {"x": 1.0, "y": -1.5},
        "anchor": "target_center",
    }
    assert entry["channel"] == {
        "width_mm": 1.25,
        "depth_mm": 6.0,
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


def test_layered_detector_stack_roundtrips_through_project_manager():
    valid_payload = {
        "generator_id": "dfg_layered_fixture",
        "name": "fixture_layered_stack",
        "schema_version": 1,
        "generator_type": "layered_detector_stack",
        "enabled": True,
        "target": {
            "parent_logical_volume_ref": {"id": "lv-world-1", "name": "World"},
        },
        "stack": {
            "module_size_mm": {"x": 28.0, "y": 16.0},
            "module_count": 2,
            "module_pitch_mm": 9.5,
            "origin_offset_mm": {"x": 1.5, "y": -2.0, "z": 3.0},
            "anchor": "target_center",
        },
        "layers": {
            "absorber": {"material_ref": "G4_Pb", "thickness_mm": 4.0, "is_sensitive": False},
            "sensor": {"material_ref": "G4_Si", "thickness_mm": 1.0, "is_sensitive": True},
            "support": {"material_ref": "G4_Al", "thickness_mm": 2.0, "is_sensitive": False},
        },
        "realization": {
            "mode": "layered_stack",
            "status": "generated",
            "result_solid_ref": {"id": "solid-module-1", "name": "fixture_layered_stack__module_solid"},
            "generated_object_refs": {
                "solid_refs": [
                    {"id": "solid-module-1", "name": "fixture_layered_stack__module_solid"},
                    {"id": "solid-abs-1", "name": "fixture_layered_stack__absorber_solid"},
                    {"id": "solid-sensor-1", "name": "fixture_layered_stack__sensor_solid"},
                    {"id": "solid-support-1", "name": "fixture_layered_stack__support_solid"},
                ],
                "logical_volume_refs": [
                    {"id": "lv-module-1", "name": "fixture_layered_stack__module_lv"},
                    {"id": "lv-abs-1", "name": "fixture_layered_stack__absorber_lv"},
                    {"id": "lv-sensor-1", "name": "fixture_layered_stack__sensor_lv"},
                    {"id": "lv-support-1", "name": "fixture_layered_stack__support_lv"},
                ],
                "placement_refs": [
                    {"id": "pv-module-1", "name": "fixture_layered_stack__module_1_pv"},
                    {"id": "pv-layer-1", "name": "fixture_layered_stack__absorber_pv"},
                ],
            },
        },
    }

    state = GeometryState.from_dict({"detector_feature_generators": [valid_payload]})
    assert state.detector_feature_generators == [valid_payload]

    pm = ProjectManager(ExpressionEvaluator())
    pm.current_geometry_state.detector_feature_generators = [valid_payload]

    json_string = pm.save_project_to_json_string()
    saved_payload = json.loads(json_string)
    assert saved_payload["detector_feature_generators"] == [valid_payload]

    pm_round_tripped = ProjectManager(ExpressionEvaluator())
    pm_round_tripped.load_project_from_json_string(json_string)
    assert pm_round_tripped.current_geometry_state.detector_feature_generators == [valid_payload]


def test_annular_shield_sleeve_roundtrips_through_project_manager():
    valid_payload = {
        "generator_id": "dfg_shield_fixture",
        "name": "fixture_shield_sleeve",
        "schema_version": 1,
        "generator_type": "annular_shield_sleeve",
        "enabled": True,
        "target": {
            "parent_logical_volume_ref": {"id": "lv-world-1", "name": "World"},
        },
        "shield": {
            "inner_radius_mm": 9.5,
            "outer_radius_mm": 14.0,
            "length_mm": 42.0,
            "material_ref": "G4_Pb",
            "origin_offset_mm": {"x": 1.5, "y": -2.0, "z": 3.0},
            "anchor": "target_center",
        },
        "realization": {
            "mode": "placement_array",
            "status": "generated",
            "result_solid_ref": {"id": "solid-shield-1", "name": "fixture_shield_sleeve__shield_solid"},
            "generated_object_refs": {
                "solid_refs": [
                    {"id": "solid-shield-1", "name": "fixture_shield_sleeve__shield_solid"},
                ],
                "logical_volume_refs": [
                    {"id": "lv-shield-1", "name": "fixture_shield_sleeve__shield_lv"},
                ],
                "placement_refs": [
                    {"id": "pv-shield-1", "name": "fixture_shield_sleeve__shield_pv"},
                ],
            },
        },
    }

    state = GeometryState.from_dict({"detector_feature_generators": [valid_payload]})
    assert state.detector_feature_generators == [valid_payload]

    pm = ProjectManager(ExpressionEvaluator())
    pm.current_geometry_state.detector_feature_generators = [valid_payload]

    json_string = pm.save_project_to_json_string()
    saved_payload = json.loads(json_string)
    assert saved_payload["detector_feature_generators"] == [valid_payload]

    pm_round_tripped = ProjectManager(ExpressionEvaluator())
    pm_round_tripped.load_project_from_json_string(json_string)
    assert pm_round_tripped.current_geometry_state.detector_feature_generators == [valid_payload]


def test_rectangular_drilled_hole_generator_realization_creates_boolean_geometry_and_updates_targets():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "collimator_block",
        "box",
        {"x": "20", "y": "12", "z": "10"},
    )
    assert error_msg is None
    assert solid_dict["name"] == "collimator_block"

    lv_a, error_msg = pm.add_logical_volume("collimator_lv", "collimator_block", "G4_Galactic")
    assert error_msg is None
    lv_b, error_msg = pm.add_logical_volume("collimator_lv_copy", "collimator_block", "G4_Galactic")
    assert error_msg is None

    pv_a, error_msg = pm.add_physical_volume(
        "World",
        "collimator_pv",
        "collimator_lv",
        {"x": "0", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    assert error_msg is None
    pv_b, error_msg = pm.add_physical_volume(
        "World",
        "collimator_pv_copy",
        "collimator_lv_copy",
        {"x": "40", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    assert error_msg is None

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_rect_holes_runtime",
            "name": "fixture_collimator_holes",
            "generator_type": "rectangular_drilled_hole_array",
            "target": {
                "solid_ref": {
                    "id": solid_dict["id"],
                    "name": solid_dict["name"],
                },
            },
            "pattern": {
                "count_x": 2,
                "count_y": 2,
                "pitch_mm": {"x": 4, "y": 5},
                "origin_offset_mm": {"x": 1, "y": -1},
            },
            "hole": {
                "diameter_mm": 2,
                "depth_mm": 6,
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_rect_holes_runtime")
    assert error_msg is None
    assert result["hole_count"] == 4
    assert result["updated_logical_volume_names"] == ["collimator_lv", "collimator_lv_copy"]

    cutter_name = result["cutter_solid_name"]
    result_name = result["result_solid_name"]
    cutter_solid = pm.current_geometry_state.solids[cutter_name]
    result_solid = pm.current_geometry_state.solids[result_name]

    assert cutter_solid.type == "tube"
    assert float(cutter_solid.raw_parameters["rmax"]) == pytest.approx(1.0)
    assert float(cutter_solid.raw_parameters["z"]) == pytest.approx(6.0)

    assert result_solid.type == "boolean"
    recipe = result_solid.raw_parameters["recipe"]
    assert recipe[0] == {"op": "base", "solid_ref": "collimator_block"}
    assert len(recipe) == 5

    positions = [
        (
            float(item["transform"]["position"]["x"]),
            float(item["transform"]["position"]["y"]),
            float(item["transform"]["position"]["z"]),
        )
        for item in recipe[1:]
    ]
    assert positions == pytest.approx(
        [
            (-1.0, -3.5, 2.0),
            (3.0, -3.5, 2.0),
            (-1.0, 1.5, 2.0),
            (3.0, 1.5, 2.0),
        ]
    )

    assert pm.current_geometry_state.logical_volumes["collimator_lv"].solid_ref == result_name
    assert pm.current_geometry_state.logical_volumes["collimator_lv_copy"].solid_ref == result_name

    entry = pm.current_geometry_state.detector_feature_generators[0]
    assert entry["realization"]["status"] == "generated"
    assert entry["realization"]["result_solid_ref"] == {
        "id": result_solid.id,
        "name": result_name,
    }
    assert entry["realization"]["generated_object_refs"]["solid_refs"] == [
        {"id": result_solid.id, "name": result_name},
        {"id": cutter_solid.id, "name": cutter_name},
    ]
    assert entry["realization"]["generated_object_refs"]["logical_volume_refs"] == [
        {"id": lv_a["id"], "name": "collimator_lv"},
        {"id": lv_b["id"], "name": "collimator_lv_copy"},
    ]
    assert entry["realization"]["generated_object_refs"]["placement_refs"] == [
        {"id": pv_a["id"], "name": "collimator_pv"},
        {"id": pv_b["id"], "name": "collimator_pv_copy"},
    ]


def test_rectangular_drilled_hole_generator_realization_reuses_generated_solids_on_revision():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "revision_block",
        "box",
        {"x": "30", "y": "20", "z": "10"},
    )
    assert error_msg is None

    _, error_msg = pm.add_logical_volume("revision_lv", "revision_block", "G4_Galactic")
    assert error_msg is None

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_rect_holes_refresh",
            "name": "refresh_collimator_holes",
            "generator_type": "rectangular_drilled_hole_array",
            "target": {
                "solid_ref": {
                    "id": solid_dict["id"],
                    "name": solid_dict["name"],
                },
            },
            "pattern": {
                "count_x": 1,
                "count_y": 1,
                "pitch_mm": {"x": 4, "y": 4},
                "origin_offset_mm": {"x": 0, "y": 0},
            },
            "hole": {
                "diameter_mm": 1.5,
                "depth_mm": 4,
            },
        }
    ])

    first_result, error_msg = pm.realize_detector_feature_generator("dfg_rect_holes_refresh")
    assert error_msg is None

    first_result_name = first_result["result_solid_name"]
    first_cutter_name = first_result["cutter_solid_name"]
    first_entry = pm.current_geometry_state.detector_feature_generators[0]
    first_solid_refs = {
        item["name"]: item["id"]
        for item in first_entry["realization"]["generated_object_refs"]["solid_refs"]
    }

    entry = pm.current_geometry_state.detector_feature_generators[0]
    entry["pattern"]["count_x"] = 3
    entry["pattern"]["pitch_mm"]["x"] = 5.0
    entry["hole"]["depth_mm"] = 10.0

    second_result, error_msg = pm.realize_detector_feature_generator("dfg_rect_holes_refresh")
    assert error_msg is None
    assert second_result["result_solid_name"] == first_result_name
    assert second_result["cutter_solid_name"] == first_cutter_name
    assert pm.current_geometry_state.logical_volumes["revision_lv"].solid_ref == first_result_name

    second_entry = pm.current_geometry_state.detector_feature_generators[0]
    second_solid_refs = {
        item["name"]: item["id"]
        for item in second_entry["realization"]["generated_object_refs"]["solid_refs"]
    }
    assert second_solid_refs == first_solid_refs

    refreshed_result_solid = pm.current_geometry_state.solids[first_result_name]
    refreshed_recipe = refreshed_result_solid.raw_parameters["recipe"]
    assert len(refreshed_recipe) == 4
    assert [
        (
            float(item["transform"]["position"]["x"]),
            float(item["transform"]["position"]["y"]),
            float(item["transform"]["position"]["z"]),
        )
        for item in refreshed_recipe[1:]
    ] == pytest.approx(
        [
            (-5.0, 0.0, 0.0),
            (0.0, 0.0, 0.0),
            (5.0, 0.0, 0.0),
        ]
    )

    generated_prefix_names = sorted(
        name
        for name in pm.current_geometry_state.solids
        if name.startswith("refresh_collimator_holes__")
    )
    assert generated_prefix_names == [first_cutter_name, first_result_name]


def test_circular_drilled_hole_generator_realization_creates_bolt_circle_geometry():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "circular_block",
        "box",
        {"x": "24", "y": "24", "z": "10"},
    )
    assert error_msg is None

    logical_volume, error_msg = pm.add_logical_volume("circular_lv", "circular_block", "G4_Galactic")
    assert error_msg is None

    placement, error_msg = pm.add_physical_volume(
        "World",
        "circular_pv",
        "circular_lv",
        {"x": "0", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    assert error_msg is None

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_circular_holes_runtime",
            "name": "fixture_circular_holes",
            "generator_type": "circular_drilled_hole_array",
            "target": {
                "solid_ref": {
                    "id": solid_dict["id"],
                    "name": solid_dict["name"],
                },
            },
            "pattern": {
                "count": 4,
                "radius_mm": 4,
                "orientation_deg": 45,
                "origin_offset_mm": {"x": 1, "y": -2},
            },
            "hole": {
                "diameter_mm": 2,
                "depth_mm": 6,
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_circular_holes_runtime")
    assert error_msg is None
    assert result["hole_count"] == 4
    assert result["updated_logical_volume_names"] == ["circular_lv"]

    result_solid = pm.current_geometry_state.solids[result["result_solid_name"]]
    recipe = result_solid.raw_parameters["recipe"]
    assert recipe[0] == {"op": "base", "solid_ref": "circular_block"}
    assert len(recipe) == 5
    positions = [
        (
            float(item["transform"]["position"]["x"]),
            float(item["transform"]["position"]["y"]),
            float(item["transform"]["position"]["z"]),
        )
        for item in recipe[1:]
    ]
    expected_positions = [
        (3.82842712474619, 0.8284271247461903, 2.0),
        (-1.8284271247461898, 0.8284271247461903, 2.0),
        (-1.8284271247461907, -4.82842712474619, 2.0),
        (3.8284271247461894, -4.82842712474619, 2.0),
    ]
    for position, expected_position in zip(positions, expected_positions):
        assert position == pytest.approx(expected_position)

    entry = pm.current_geometry_state.detector_feature_generators[0]
    assert entry["realization"]["status"] == "generated"
    assert entry["realization"]["generated_object_refs"]["logical_volume_refs"] == [
        {"id": logical_volume["id"], "name": "circular_lv"},
    ]
    assert entry["realization"]["generated_object_refs"]["placement_refs"] == [
        {"id": placement["id"], "name": "circular_pv"},
    ]
    assert pm.current_geometry_state.logical_volumes["circular_lv"].solid_ref == result["result_solid_name"]


def test_upsert_detector_feature_generator_saves_and_regenerates_in_place():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "ui_collimator_block",
        "box",
        {"x": "24", "y": "18", "z": "12"},
    )
    assert error_msg is None

    _, error_msg = pm.add_logical_volume("ui_collimator_lv", "ui_collimator_block", "G4_Galactic")
    assert error_msg is None

    created_entry, first_result, error_msg = pm.upsert_detector_feature_generator(
        {
            "generator_id": "dfg_ui_modal_fixture",
            "generator_type": "rectangular_drilled_hole_array",
            "name": "ui_collimator_holes",
            "target": {
                "solid_ref": {
                    "id": solid_dict["id"],
                    "name": solid_dict["name"],
                },
            },
            "pattern": {
                "count_x": 2,
                "count_y": 3,
                "pitch_mm": {"x": 4.5, "y": 6.0},
                "origin_offset_mm": {"x": 0.5, "y": -1.0},
            },
            "hole": {
                "diameter_mm": 1.5,
                "depth_mm": 8.0,
            },
        },
        realize_now=True,
    )

    assert error_msg is None
    assert first_result["hole_count"] == 6
    assert created_entry["realization"]["status"] == "generated"
    first_result_name = first_result["result_solid_name"]
    first_cutter_name = first_result["cutter_solid_name"]

    updated_entry, second_result, error_msg = pm.upsert_detector_feature_generator(
        {
            "generator_id": "dfg_ui_modal_fixture",
            "generator_type": "rectangular_drilled_hole_array",
            "name": "ui_collimator_holes",
            "target": {
                "solid_ref": {
                    "id": solid_dict["id"],
                    "name": solid_dict["name"],
                },
            },
            "pattern": {
                "count_x": 4,
                "count_y": 1,
                "pitch_mm": {"x": 3.0, "y": 6.0},
                "origin_offset_mm": {"x": -1.5, "y": 0.0},
            },
            "hole": {
                "diameter_mm": 2.0,
                "depth_mm": 10.0,
            },
        },
        realize_now=True,
    )

    assert error_msg is None
    assert second_result["hole_count"] == 4
    assert second_result["result_solid_name"] == first_result_name
    assert second_result["cutter_solid_name"] == first_cutter_name
    assert updated_entry["realization"]["result_solid_ref"]["name"] == first_result_name
    assert pm.current_geometry_state.logical_volumes["ui_collimator_lv"].solid_ref == first_result_name

    refreshed_recipe = pm.current_geometry_state.solids[first_result_name].raw_parameters["recipe"]
    assert len(refreshed_recipe) == 5
    assert [
        (
            float(item["transform"]["position"]["x"]),
            float(item["transform"]["position"]["y"]),
            float(item["transform"]["position"]["z"]),
        )
        for item in refreshed_recipe[1:]
    ] == pytest.approx(
        [
            (-6.0, 0.0, 1.0),
            (-3.0, 0.0, 1.0),
            (0.0, 0.0, 1.0),
            (3.0, 0.0, 1.0),
        ]
    )


def test_layered_detector_stack_realization_creates_module_geometry_and_repeated_placements():
    pm = _make_pm()
    world_lv = pm.current_geometry_state.logical_volumes["World"]

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_layered_runtime",
            "name": "fixture_layered_stack",
            "generator_type": "layered_detector_stack",
            "target": {
                "parent_logical_volume_ref": {
                    "id": world_lv.id,
                    "name": "World",
                },
            },
            "stack": {
                "module_size_mm": {"x": 24, "y": 18},
                "module_count": 3,
                "module_pitch_mm": 8.5,
                "origin_offset_mm": {"x": 1.5, "y": -2.0, "z": 3.0},
            },
            "layers": {
                "absorber": {"material_ref": "G4_Pb", "thickness_mm": 4.0},
                "sensor": {"material_ref": "G4_Si", "thickness_mm": 1.2, "is_sensitive": True},
                "support": {"material_ref": "G4_Al", "thickness_mm": 2.3},
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_layered_runtime")
    assert error_msg is None
    assert result["module_count"] == 3
    assert result["layer_count"] == 3
    assert result["parent_logical_volume_name"] == "World"
    assert result["module_logical_volume_name"] == "fixture_layered_stack__module_lv"
    assert result["total_thickness_mm"] == pytest.approx(7.5)

    module_solid = pm.current_geometry_state.solids[result["result_solid_name"]]
    absorber_solid = pm.current_geometry_state.solids["fixture_layered_stack__absorber_solid"]
    sensor_solid = pm.current_geometry_state.solids["fixture_layered_stack__sensor_solid"]
    support_solid = pm.current_geometry_state.solids["fixture_layered_stack__support_solid"]
    assert module_solid.type == "box"
    assert float(module_solid.raw_parameters["x"]) == pytest.approx(24.0)
    assert float(module_solid.raw_parameters["y"]) == pytest.approx(18.0)
    assert float(module_solid.raw_parameters["z"]) == pytest.approx(7.5)
    assert float(absorber_solid.raw_parameters["z"]) == pytest.approx(4.0)
    assert float(sensor_solid.raw_parameters["z"]) == pytest.approx(1.2)
    assert float(support_solid.raw_parameters["z"]) == pytest.approx(2.3)

    module_lv = pm.current_geometry_state.logical_volumes["fixture_layered_stack__module_lv"]
    absorber_lv = pm.current_geometry_state.logical_volumes["fixture_layered_stack__absorber_lv"]
    sensor_lv = pm.current_geometry_state.logical_volumes["fixture_layered_stack__sensor_lv"]
    support_lv = pm.current_geometry_state.logical_volumes["fixture_layered_stack__support_lv"]
    assert module_lv.material_ref == "G4_Galactic"
    assert absorber_lv.material_ref == "G4_Pb"
    assert sensor_lv.material_ref == "G4_Si"
    assert support_lv.material_ref == "G4_Al"
    assert absorber_lv.is_sensitive is False
    assert sensor_lv.is_sensitive is True
    assert support_lv.is_sensitive is False

    assert [pv.name for pv in module_lv.content] == [
        "fixture_layered_stack__absorber_pv",
        "fixture_layered_stack__sensor_pv",
        "fixture_layered_stack__support_pv",
    ]
    assert [
        float(pv.position["z"])
        for pv in module_lv.content
    ] == pytest.approx([-1.75, 0.85, 2.6])

    world_module_pvs = [
        pv for pv in pm.current_geometry_state.logical_volumes["World"].content
        if pv.name.startswith("fixture_layered_stack__module_")
    ]
    assert len(world_module_pvs) == 3
    assert [
        (float(pv.position["x"]), float(pv.position["y"]), float(pv.position["z"]))
        for pv in world_module_pvs
    ] == pytest.approx([
        (1.5, -2.0, -5.5),
        (1.5, -2.0, 3.0),
        (1.5, -2.0, 11.5),
    ])

    entry = pm.current_geometry_state.detector_feature_generators[0]
    assert entry["realization"]["status"] == "generated"
    assert entry["realization"]["mode"] == "layered_stack"
    assert entry["realization"]["result_solid_ref"] == {
        "id": module_solid.id,
        "name": "fixture_layered_stack__module_solid",
    }
    assert entry["realization"]["generated_object_refs"]["solid_refs"] == [
        {"id": module_solid.id, "name": "fixture_layered_stack__module_solid"},
        {"id": absorber_solid.id, "name": "fixture_layered_stack__absorber_solid"},
        {"id": sensor_solid.id, "name": "fixture_layered_stack__sensor_solid"},
        {"id": support_solid.id, "name": "fixture_layered_stack__support_solid"},
    ]
    assert entry["realization"]["generated_object_refs"]["logical_volume_refs"] == [
        {"id": module_lv.id, "name": "fixture_layered_stack__module_lv"},
        {"id": absorber_lv.id, "name": "fixture_layered_stack__absorber_lv"},
        {"id": sensor_lv.id, "name": "fixture_layered_stack__sensor_lv"},
        {"id": support_lv.id, "name": "fixture_layered_stack__support_lv"},
    ]
    assert len(entry["realization"]["generated_object_refs"]["placement_refs"]) == 6

    scene_names = {
        item["name"]
        for item in pm.get_threejs_description()
        if item.get("name", "").startswith("fixture_layered_stack__module_")
    }
    assert scene_names == {
        "fixture_layered_stack__module_1_pv",
        "fixture_layered_stack__module_2_pv",
        "fixture_layered_stack__module_3_pv",
    }


def test_layered_detector_stack_realization_replaces_old_module_placements_on_revision():
    pm = _make_pm()
    world_lv = pm.current_geometry_state.logical_volumes["World"]

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_layered_refresh",
            "name": "refresh_layered_stack",
            "generator_type": "layered_detector_stack",
            "target": {
                "parent_logical_volume_ref": {
                    "id": world_lv.id,
                    "name": "World",
                },
            },
            "stack": {
                "module_size_mm": {"x": 20, "y": 12},
                "module_count": 2,
                "module_pitch_mm": 7.0,
                "origin_offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
            "layers": {
                "absorber": {"material_ref": "G4_Pb", "thickness_mm": 3.0},
                "sensor": {"material_ref": "G4_Si", "thickness_mm": 1.0, "is_sensitive": True},
                "support": {"material_ref": "G4_Al", "thickness_mm": 1.0},
            },
        }
    ])

    first_result, error_msg = pm.realize_detector_feature_generator("dfg_layered_refresh")
    assert error_msg is None

    entry = pm.current_geometry_state.detector_feature_generators[0]
    entry["stack"]["module_count"] = 4
    entry["stack"]["module_pitch_mm"] = 9.0
    entry["layers"]["sensor"]["thickness_mm"] = 1.5

    second_result, error_msg = pm.realize_detector_feature_generator("dfg_layered_refresh")
    assert error_msg is None
    assert second_result["result_solid_name"] == first_result["result_solid_name"]
    assert second_result["module_logical_volume_name"] == first_result["module_logical_volume_name"]
    assert second_result["total_thickness_mm"] == pytest.approx(5.5)

    module_solid = pm.current_geometry_state.solids[first_result["result_solid_name"]]
    assert float(module_solid.raw_parameters["z"]) == pytest.approx(5.5)

    module_lv = pm.current_geometry_state.logical_volumes[first_result["module_logical_volume_name"]]
    assert [
        float(pv.position["z"])
        for pv in module_lv.content
    ] == pytest.approx([-1.25, 1.0, 2.25])

    world_module_pvs = [
        pv for pv in pm.current_geometry_state.logical_volumes["World"].content
        if pv.name.startswith("refresh_layered_stack__module_")
    ]
    assert len(world_module_pvs) == 4
    assert [
        float(pv.position["z"])
        for pv in world_module_pvs
    ] == pytest.approx([-13.5, -4.5, 4.5, 13.5])

    placement_names = [
        ref["name"]
        for ref in pm.current_geometry_state.detector_feature_generators[0]["realization"]["generated_object_refs"]["placement_refs"]
    ]
    assert placement_names == [
        "refresh_layered_stack__module_1_pv",
        "refresh_layered_stack__module_2_pv",
        "refresh_layered_stack__module_3_pv",
        "refresh_layered_stack__module_4_pv",
        "refresh_layered_stack__absorber_pv",
        "refresh_layered_stack__sensor_pv",
        "refresh_layered_stack__support_pv",
    ]

    scene_names = {
        item["name"]
        for item in pm.get_threejs_description()
        if item.get("name", "").startswith("refresh_layered_stack__module_")
    }
    assert scene_names == {
        "refresh_layered_stack__module_1_pv",
        "refresh_layered_stack__module_2_pv",
        "refresh_layered_stack__module_3_pv",
        "refresh_layered_stack__module_4_pv",
    }


def test_layered_detector_stack_realization_requires_instantiated_parent_lv():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "detached_layered_parent_box",
        "box",
        {"x": "30", "y": "20", "z": "10"},
    )
    assert error_msg is None

    parent_lv, error_msg = pm.add_logical_volume(
        "detached_layered_parent_lv",
        solid_dict["name"],
        "G4_Galactic",
    )
    assert error_msg is None

    parent_lv_state = pm.current_geometry_state.logical_volumes[parent_lv["name"]]
    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_layered_detached_parent",
            "name": "detached_layered_stack",
            "generator_type": "layered_detector_stack",
            "target": {
                "parent_logical_volume_ref": {
                    "id": parent_lv_state.id,
                    "name": parent_lv_state.name,
                },
            },
            "stack": {
                "module_size_mm": {"x": 20, "y": 12},
                "module_count": 2,
                "module_pitch_mm": 7.0,
                "origin_offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
            "layers": {
                "absorber": {"material_ref": "G4_Pb", "thickness_mm": 3.0},
                "sensor": {"material_ref": "G4_Si", "thickness_mm": 1.0, "is_sensitive": True},
                "support": {"material_ref": "G4_Al", "thickness_mm": 1.0},
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_layered_detached_parent")

    assert result is None
    assert error_msg == (
        "Layered detector-stack generators require parent logical volume "
        "'detached_layered_parent_lv' to already be placed in the live scene so generated modules are visible."
    )
    assert parent_lv_state.content == []


def test_tiled_sensor_array_realization_creates_sensor_grid_and_generated_refs():
    pm = _make_pm()
    world_lv = pm.current_geometry_state.logical_volumes["World"]

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_sensor_array_runtime",
            "name": "fixture_sensor_array",
            "generator_type": "tiled_sensor_array",
            "target": {
                "parent_logical_volume_ref": {
                    "id": world_lv.id,
                    "name": "World",
                },
            },
            "array": {
                "count_x": 2,
                "count_y": 3,
                "pitch_mm": {"x": 7.0, "y": 5.5},
                "origin_offset_mm": {"x": 1.5, "y": -2.0, "z": 3.0},
            },
            "sensor": {
                "size_mm": {"x": 6.0, "y": 4.0},
                "thickness_mm": 1.2,
                "material_ref": "G4_Si",
                "is_sensitive": True,
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_sensor_array_runtime")
    assert error_msg is None
    assert result["sensor_count"] == 6
    assert result["parent_logical_volume_name"] == "World"
    assert result["sensor_logical_volume_name"] == "fixture_sensor_array__sensor_lv"

    sensor_solid = pm.current_geometry_state.solids[result["result_solid_name"]]
    sensor_lv = pm.current_geometry_state.logical_volumes[result["sensor_logical_volume_name"]]
    assert sensor_solid.type == "box"
    assert float(sensor_solid.raw_parameters["x"]) == pytest.approx(6.0)
    assert float(sensor_solid.raw_parameters["y"]) == pytest.approx(4.0)
    assert float(sensor_solid.raw_parameters["z"]) == pytest.approx(1.2)
    assert sensor_lv.material_ref == "G4_Si"
    assert sensor_lv.is_sensitive is True

    world_sensor_pvs = [
        pv for pv in pm.current_geometry_state.logical_volumes["World"].content
        if pv.name.startswith("fixture_sensor_array__sensor_")
    ]
    assert len(world_sensor_pvs) == 6
    assert [pv.name for pv in world_sensor_pvs] == [
        "fixture_sensor_array__sensor_r1_c1_pv",
        "fixture_sensor_array__sensor_r1_c2_pv",
        "fixture_sensor_array__sensor_r2_c1_pv",
        "fixture_sensor_array__sensor_r2_c2_pv",
        "fixture_sensor_array__sensor_r3_c1_pv",
        "fixture_sensor_array__sensor_r3_c2_pv",
    ]
    assert [
        (float(pv.position["x"]), float(pv.position["y"]), float(pv.position["z"]))
        for pv in world_sensor_pvs
    ] == pytest.approx([
        (-2.0, -7.5, 3.0),
        (5.0, -7.5, 3.0),
        (-2.0, -2.0, 3.0),
        (5.0, -2.0, 3.0),
        (-2.0, 3.5, 3.0),
        (5.0, 3.5, 3.0),
    ])

    entry = pm.current_geometry_state.detector_feature_generators[0]
    assert entry["realization"]["status"] == "generated"
    assert entry["realization"]["mode"] == "placement_array"
    assert entry["realization"]["result_solid_ref"] == {
        "id": sensor_solid.id,
        "name": "fixture_sensor_array__sensor_solid",
    }
    assert entry["realization"]["generated_object_refs"]["solid_refs"] == [
        {"id": sensor_solid.id, "name": "fixture_sensor_array__sensor_solid"},
    ]
    assert entry["realization"]["generated_object_refs"]["logical_volume_refs"] == [
        {"id": sensor_lv.id, "name": "fixture_sensor_array__sensor_lv"},
    ]
    assert len(entry["realization"]["generated_object_refs"]["placement_refs"]) == 6

    scene_names = {
        item["name"]
        for item in pm.get_threejs_description()
        if item.get("name", "").startswith("fixture_sensor_array__sensor_")
    }
    assert scene_names == {
        "fixture_sensor_array__sensor_r1_c1_pv",
        "fixture_sensor_array__sensor_r1_c2_pv",
        "fixture_sensor_array__sensor_r2_c1_pv",
        "fixture_sensor_array__sensor_r2_c2_pv",
        "fixture_sensor_array__sensor_r3_c1_pv",
        "fixture_sensor_array__sensor_r3_c2_pv",
    }


def test_tiled_sensor_array_realization_requires_instantiated_parent_lv():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "detached_sensor_parent_box",
        "box",
        {"x": "30", "y": "20", "z": "10"},
    )
    assert error_msg is None

    parent_lv, error_msg = pm.add_logical_volume(
        "detached_sensor_parent_lv",
        solid_dict["name"],
        pm.current_geometry_state.logical_volumes["World"].material_ref,
    )
    assert error_msg is None

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_detached_sensor_array",
            "name": "detached_sensor_array",
            "generator_type": "tiled_sensor_array",
            "target": {
                "parent_logical_volume_ref": {
                    "id": parent_lv["id"],
                    "name": "detached_sensor_parent_lv",
                },
            },
            "array": {
                "count_x": 2,
                "count_y": 2,
                "pitch_mm": {"x": 6.0, "y": 6.0},
                "origin_offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
            "sensor": {
                "size_mm": {"x": 6.0, "y": 6.0},
                "thickness_mm": 1.0,
                "material_ref": "G4_Si",
                "is_sensitive": True,
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_detached_sensor_array")
    assert result is None
    assert error_msg == (
        "Tiled sensor-array generators require parent logical volume "
        "'detached_sensor_parent_lv' to already be placed in the live scene so generated sensors are visible."
    )


def test_tiled_sensor_array_realization_reuses_generated_sensor_objects_and_replaces_old_placements():
    pm = _make_pm()
    world_lv = pm.current_geometry_state.logical_volumes["World"]

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_sensor_array_refresh",
            "name": "refresh_sensor_array",
            "generator_type": "tiled_sensor_array",
            "target": {
                "parent_logical_volume_ref": {
                    "id": world_lv.id,
                    "name": "World",
                },
            },
            "array": {
                "count_x": 1,
                "count_y": 2,
                "pitch_mm": {"x": 6.0, "y": 5.0},
                "origin_offset_mm": {"x": 0.0, "y": 0.0, "z": 1.0},
            },
            "sensor": {
                "size_mm": {"x": 5.0, "y": 4.0},
                "thickness_mm": 1.0,
                "material_ref": "G4_Si",
                "is_sensitive": True,
            },
        }
    ])

    first_result, error_msg = pm.realize_detector_feature_generator("dfg_sensor_array_refresh")
    assert error_msg is None

    entry = pm.current_geometry_state.detector_feature_generators[0]
    entry["array"]["count_x"] = 3
    entry["array"]["pitch_mm"]["x"] = 8.0
    entry["array"]["origin_offset_mm"]["z"] = 4.0
    entry["sensor"]["size_mm"]["y"] = 4.5
    entry["sensor"]["thickness_mm"] = 1.4

    second_result, error_msg = pm.realize_detector_feature_generator("dfg_sensor_array_refresh")
    assert error_msg is None
    assert second_result["result_solid_name"] == first_result["result_solid_name"]
    assert second_result["sensor_logical_volume_name"] == first_result["sensor_logical_volume_name"]
    assert second_result["sensor_count"] == 6

    sensor_solid = pm.current_geometry_state.solids[first_result["result_solid_name"]]
    assert float(sensor_solid.raw_parameters["x"]) == pytest.approx(5.0)
    assert float(sensor_solid.raw_parameters["y"]) == pytest.approx(4.5)
    assert float(sensor_solid.raw_parameters["z"]) == pytest.approx(1.4)

    world_sensor_pvs = [
        pv for pv in pm.current_geometry_state.logical_volumes["World"].content
        if pv.name.startswith("refresh_sensor_array__sensor_")
    ]
    assert len(world_sensor_pvs) == 6
    assert [
        (float(pv.position["x"]), float(pv.position["y"]), float(pv.position["z"]))
        for pv in world_sensor_pvs
    ] == pytest.approx([
        (-8.0, -2.5, 4.0),
        (0.0, -2.5, 4.0),
        (8.0, -2.5, 4.0),
        (-8.0, 2.5, 4.0),
        (0.0, 2.5, 4.0),
        (8.0, 2.5, 4.0),
    ])

    placement_names = [
        ref["name"]
        for ref in pm.current_geometry_state.detector_feature_generators[0]["realization"]["generated_object_refs"]["placement_refs"]
    ]
    assert placement_names == [
        "refresh_sensor_array__sensor_r1_c1_pv",
        "refresh_sensor_array__sensor_r1_c2_pv",
        "refresh_sensor_array__sensor_r1_c3_pv",
        "refresh_sensor_array__sensor_r2_c1_pv",
        "refresh_sensor_array__sensor_r2_c2_pv",
        "refresh_sensor_array__sensor_r2_c3_pv",
    ]


def test_support_rib_array_realization_creates_repeated_rib_geometry_and_generated_refs():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "support_parent_box",
        "box",
        {"x": "40", "y": "30", "z": "20"},
    )
    assert error_msg is None

    parent_lv, error_msg = pm.add_logical_volume("support_parent_lv", "support_parent_box", "G4_Galactic")
    assert error_msg is None
    _, error_msg = pm.add_physical_volume(
        "World",
        "support_parent_pv",
        "support_parent_lv",
        {"x": "0", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    assert error_msg is None

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_support_ribs_runtime",
            "name": "fixture_support_ribs",
            "generator_type": "support_rib_array",
            "target": {
                "parent_logical_volume_ref": {
                    "id": parent_lv["id"],
                    "name": "support_parent_lv",
                },
            },
            "array": {
                "count": 3,
                "linear_pitch_mm": 10,
                "axis": "x",
                "origin_offset_mm": {"x": 1, "y": -2, "z": 3},
            },
            "rib": {
                "width_mm": 1.5,
                "height_mm": 4,
                "material_ref": "G4_Al",
                "is_sensitive": False,
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_support_ribs_runtime")
    assert error_msg is None
    assert result["rib_count"] == 3
    assert result["parent_logical_volume_name"] == "support_parent_lv"
    assert result["rib_logical_volume_name"] == "fixture_support_ribs__rib_lv"

    rib_solid = pm.current_geometry_state.solids[result["result_solid_name"]]
    rib_lv = pm.current_geometry_state.logical_volumes[result["rib_logical_volume_name"]]
    assert rib_solid.type == "box"
    assert float(rib_solid.raw_parameters["x"]) == pytest.approx(1.5)
    assert float(rib_solid.raw_parameters["y"]) == pytest.approx(30.0)
    assert float(rib_solid.raw_parameters["z"]) == pytest.approx(4.0)
    assert rib_lv.material_ref == "G4_Al"
    assert rib_lv.is_sensitive is False

    rib_pvs = [
        pv for pv in pm.current_geometry_state.logical_volumes["support_parent_lv"].content
        if pv.name.startswith("fixture_support_ribs__rib_")
    ]
    assert len(rib_pvs) == 3
    assert [pv.name for pv in rib_pvs] == [
        "fixture_support_ribs__rib_1_pv",
        "fixture_support_ribs__rib_2_pv",
        "fixture_support_ribs__rib_3_pv",
    ]
    assert [
        (float(pv.position["x"]), float(pv.position["y"]), float(pv.position["z"]))
        for pv in rib_pvs
    ] == pytest.approx([
        (-9.0, -2.0, 3.0),
        (1.0, -2.0, 3.0),
        (11.0, -2.0, 3.0),
    ])

    entry = pm.current_geometry_state.detector_feature_generators[0]
    assert entry["realization"]["status"] == "generated"
    assert entry["realization"]["mode"] == "placement_array"
    assert entry["realization"]["result_solid_ref"] == {
        "id": rib_solid.id,
        "name": "fixture_support_ribs__rib_solid",
    }
    assert entry["realization"]["generated_object_refs"]["solid_refs"] == [
        {"id": rib_solid.id, "name": "fixture_support_ribs__rib_solid"},
    ]
    assert entry["realization"]["generated_object_refs"]["logical_volume_refs"] == [
        {"id": rib_lv.id, "name": "fixture_support_ribs__rib_lv"},
    ]
    assert len(entry["realization"]["generated_object_refs"]["placement_refs"]) == 3

    scene_names = {
        item["name"]
        for item in pm.get_threejs_description()
        if item.get("name", "").startswith("fixture_support_ribs__rib_")
    }
    assert scene_names == {
        "fixture_support_ribs__rib_1_pv",
        "fixture_support_ribs__rib_2_pv",
        "fixture_support_ribs__rib_3_pv",
    }


def test_support_rib_array_realization_requires_instantiated_parent_lv():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "detached_support_parent_box",
        "box",
        {"x": "30", "y": "20", "z": "10"},
    )
    assert error_msg is None

    parent_lv, error_msg = pm.add_logical_volume(
        "detached_support_parent_lv",
        solid_dict["name"],
        "G4_Galactic",
    )
    assert error_msg is None

    parent_lv_state = pm.current_geometry_state.logical_volumes[parent_lv["name"]]
    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_support_ribs_detached_parent",
            "name": "detached_support_ribs",
            "generator_type": "support_rib_array",
            "target": {
                "parent_logical_volume_ref": {
                    "id": parent_lv_state.id,
                    "name": parent_lv_state.name,
                },
            },
            "array": {
                "count": 3,
                "linear_pitch_mm": 8.0,
                "axis": "x",
                "origin_offset_mm": {"x": 0.0, "y": 0.0, "z": 0.0},
            },
            "rib": {
                "width_mm": 1.0,
                "height_mm": 2.0,
                "material_ref": "G4_Al",
                "is_sensitive": False,
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_support_ribs_detached_parent")

    assert result is None
    assert error_msg == (
        "Support-rib generators require parent logical volume "
        "'detached_support_parent_lv' to already be placed in the live scene so generated ribs are visible."
    )
    assert parent_lv_state.content == []


def test_support_rib_array_realization_reuses_generated_objects_and_replaces_old_placements():
    pm = _make_pm()

    world_lv = pm.current_geometry_state.logical_volumes["World"]

    _, error_msg = pm.add_solid(
        "refresh_support_parent_box",
        "box",
        {"x": "36", "y": "24", "z": "18"},
    )
    assert error_msg is None

    parent_lv, error_msg = pm.add_logical_volume("refresh_support_parent_lv", "refresh_support_parent_box", "G4_Galactic")
    assert error_msg is None
    _, error_msg = pm.add_physical_volume(
        world_lv.name,
        "refresh_support_parent_pv",
        parent_lv["name"],
        {"x": "0", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    assert error_msg is None

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_support_ribs_refresh",
            "name": "refresh_support_ribs",
            "generator_type": "support_rib_array",
            "target": {
                "parent_logical_volume_ref": {
                    "id": parent_lv["id"],
                    "name": "refresh_support_parent_lv",
                },
            },
            "array": {
                "count": 2,
                "linear_pitch_mm": 12,
                "axis": "y",
                "origin_offset_mm": {"x": 0, "y": 1, "z": 2},
            },
            "rib": {
                "width_mm": 2,
                "height_mm": 3,
                "material_ref": "G4_Al",
                "is_sensitive": False,
            },
        }
    ])

    first_result, error_msg = pm.realize_detector_feature_generator("dfg_support_ribs_refresh")
    assert error_msg is None

    entry = pm.current_geometry_state.detector_feature_generators[0]
    entry["array"]["count"] = 4
    entry["array"]["linear_pitch_mm"] = 6.0
    entry["array"]["axis"] = "x"
    entry["rib"]["height_mm"] = 4.5

    second_result, error_msg = pm.realize_detector_feature_generator("dfg_support_ribs_refresh")
    assert error_msg is None
    assert second_result["result_solid_name"] == first_result["result_solid_name"]
    assert second_result["rib_logical_volume_name"] == first_result["rib_logical_volume_name"]
    assert second_result["rib_count"] == 4

    rib_solid = pm.current_geometry_state.solids[first_result["result_solid_name"]]
    assert float(rib_solid.raw_parameters["x"]) == pytest.approx(2.0)
    assert float(rib_solid.raw_parameters["y"]) == pytest.approx(24.0)
    assert float(rib_solid.raw_parameters["z"]) == pytest.approx(4.5)

    rib_pvs = [
        pv for pv in pm.current_geometry_state.logical_volumes["refresh_support_parent_lv"].content
        if pv.name.startswith("refresh_support_ribs__rib_")
    ]
    assert len(rib_pvs) == 4
    assert [
        (float(pv.position["x"]), float(pv.position["y"]), float(pv.position["z"]))
        for pv in rib_pvs
    ] == pytest.approx([
        (-9.0, 1.0, 2.0),
        (-3.0, 1.0, 2.0),
        (3.0, 1.0, 2.0),
        (9.0, 1.0, 2.0),
    ])

    placement_names = [
        ref["name"]
        for ref in pm.current_geometry_state.detector_feature_generators[0]["realization"]["generated_object_refs"]["placement_refs"]
    ]
    assert placement_names == [
        "refresh_support_ribs__rib_1_pv",
        "refresh_support_ribs__rib_2_pv",
        "refresh_support_ribs__rib_3_pv",
        "refresh_support_ribs__rib_4_pv",
    ]

    scene_names = {
        item["name"]
        for item in pm.get_threejs_description()
        if item.get("name", "").startswith("refresh_support_ribs__rib_")
    }
    assert scene_names == {
        "refresh_support_ribs__rib_1_pv",
        "refresh_support_ribs__rib_2_pv",
        "refresh_support_ribs__rib_3_pv",
        "refresh_support_ribs__rib_4_pv",
    }


def test_annular_shield_sleeve_realization_creates_tube_geometry_and_generated_refs():
    pm = _make_pm()
    world_lv = pm.current_geometry_state.logical_volumes["World"]

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_shield_runtime",
            "name": "fixture_shield_sleeve",
            "generator_type": "annular_shield_sleeve",
            "target": {
                "parent_logical_volume_ref": {
                    "id": world_lv.id,
                    "name": "World",
                },
            },
            "shield": {
                "inner_radius_mm": 10.0,
                "outer_radius_mm": 14.5,
                "length_mm": 36.0,
                "material_ref": "G4_Pb",
                "origin_offset_mm": {"x": 1.0, "y": -2.0, "z": 3.5},
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_shield_runtime")
    assert error_msg is None
    assert result["parent_logical_volume_name"] == "World"
    assert result["shield_logical_volume_name"] == "fixture_shield_sleeve__shield_lv"

    shield_solid = pm.current_geometry_state.solids[result["result_solid_name"]]
    shield_lv = pm.current_geometry_state.logical_volumes[result["shield_logical_volume_name"]]
    assert shield_solid.type == "tube"
    assert float(shield_solid.raw_parameters["rmin"]) == pytest.approx(10.0)
    assert float(shield_solid.raw_parameters["rmax"]) == pytest.approx(14.5)
    assert float(shield_solid.raw_parameters["z"]) == pytest.approx(36.0)
    assert shield_solid.raw_parameters["startphi"] == "0"
    assert shield_solid.raw_parameters["deltaphi"] == "360"
    assert shield_lv.material_ref == "G4_Pb"
    assert shield_lv.is_sensitive is False

    shield_pvs = [
        pv for pv in pm.current_geometry_state.logical_volumes["World"].content
        if pv.name.startswith("fixture_shield_sleeve__shield")
    ]
    assert len(shield_pvs) == 1
    assert (
        float(shield_pvs[0].position["x"]),
        float(shield_pvs[0].position["y"]),
        float(shield_pvs[0].position["z"]),
    ) == pytest.approx((1.0, -2.0, 3.5))

    entry = pm.current_geometry_state.detector_feature_generators[0]
    assert entry["realization"]["status"] == "generated"
    assert entry["realization"]["mode"] == "placement_array"
    assert entry["realization"]["result_solid_ref"] == {
        "id": shield_solid.id,
        "name": "fixture_shield_sleeve__shield_solid",
    }
    assert entry["realization"]["generated_object_refs"]["solid_refs"] == [
        {"id": shield_solid.id, "name": "fixture_shield_sleeve__shield_solid"},
    ]
    assert entry["realization"]["generated_object_refs"]["logical_volume_refs"] == [
        {"id": shield_lv.id, "name": "fixture_shield_sleeve__shield_lv"},
    ]
    assert entry["realization"]["generated_object_refs"]["placement_refs"] == [
        {"id": shield_pvs[0].id, "name": "fixture_shield_sleeve__shield_pv"},
    ]

    scene_names = {
        item["name"]
        for item in pm.get_threejs_description()
        if item.get("name", "").startswith("fixture_shield_sleeve__shield")
    }
    assert scene_names == {
        "fixture_shield_sleeve__shield_pv",
    }


def test_annular_shield_sleeve_realization_requires_instantiated_parent_lv():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "detached_shield_parent_box",
        "box",
        {"x": "30", "y": "20", "z": "10"},
    )
    assert error_msg is None

    parent_lv, error_msg = pm.add_logical_volume(
        "detached_shield_parent_lv",
        solid_dict["name"],
        "G4_Galactic",
    )
    assert error_msg is None

    parent_lv_state = pm.current_geometry_state.logical_volumes[parent_lv["name"]]
    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_detached_shield_sleeve",
            "name": "detached_shield_sleeve",
            "generator_type": "annular_shield_sleeve",
            "target": {
                "parent_logical_volume_ref": {
                    "id": parent_lv_state.id,
                    "name": parent_lv_state.name,
                },
            },
            "shield": {
                "inner_radius_mm": 8.0,
                "outer_radius_mm": 12.0,
                "length_mm": 30.0,
                "material_ref": "G4_Pb",
                "origin_offset_mm": {"x": 0.0, "y": 0.0, "z": 1.0},
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_detached_shield_sleeve")

    assert result is None
    assert error_msg == (
        "Annular shield-sleeve generators require parent logical volume "
        "'detached_shield_parent_lv' to already be placed in the live scene so generated shields are visible."
    )
    assert parent_lv_state.content == []


def test_annular_shield_sleeve_realization_reuses_generated_objects_and_replaces_old_placements():
    pm = _make_pm()
    world_lv = pm.current_geometry_state.logical_volumes["World"]

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_shield_refresh",
            "name": "refresh_shield_sleeve",
            "generator_type": "annular_shield_sleeve",
            "target": {
                "parent_logical_volume_ref": {
                    "id": world_lv.id,
                    "name": "World",
                },
            },
            "shield": {
                "inner_radius_mm": 8.0,
                "outer_radius_mm": 12.0,
                "length_mm": 30.0,
                "material_ref": "G4_Pb",
                "origin_offset_mm": {"x": 0.0, "y": 0.0, "z": 1.0},
            },
        }
    ])

    first_result, error_msg = pm.realize_detector_feature_generator("dfg_shield_refresh")
    assert error_msg is None

    entry = pm.current_geometry_state.detector_feature_generators[0]
    entry["shield"]["inner_radius_mm"] = 9.0
    entry["shield"]["outer_radius_mm"] = 15.0
    entry["shield"]["length_mm"] = 42.0
    entry["shield"]["origin_offset_mm"]["x"] = 2.0
    entry["shield"]["origin_offset_mm"]["z"] = 5.0

    second_result, error_msg = pm.realize_detector_feature_generator("dfg_shield_refresh")
    assert error_msg is None
    assert second_result["result_solid_name"] == first_result["result_solid_name"]
    assert second_result["shield_logical_volume_name"] == first_result["shield_logical_volume_name"]

    shield_solid = pm.current_geometry_state.solids[first_result["result_solid_name"]]
    assert float(shield_solid.raw_parameters["rmin"]) == pytest.approx(9.0)
    assert float(shield_solid.raw_parameters["rmax"]) == pytest.approx(15.0)
    assert float(shield_solid.raw_parameters["z"]) == pytest.approx(42.0)

    shield_pvs = [
        pv for pv in pm.current_geometry_state.logical_volumes["World"].content
        if pv.name.startswith("refresh_shield_sleeve__shield")
    ]
    assert len(shield_pvs) == 1
    assert (
        float(shield_pvs[0].position["x"]),
        float(shield_pvs[0].position["y"]),
        float(shield_pvs[0].position["z"]),
    ) == pytest.approx((2.0, 0.0, 5.0))

    placement_names = [
        ref["name"]
        for ref in pm.current_geometry_state.detector_feature_generators[0]["realization"]["generated_object_refs"]["placement_refs"]
    ]
    assert placement_names == [
        "refresh_shield_sleeve__shield_pv",
    ]

    scene_names = {
        item["name"]
        for item in pm.get_threejs_description()
        if item.get("name", "").startswith("refresh_shield_sleeve__shield")
    }
    assert scene_names == {
        "refresh_shield_sleeve__shield_pv",
    }


def test_channel_cut_array_realization_creates_boolean_geometry_and_updates_targets():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "channel_block",
        "box",
        {"x": "24", "y": "18", "z": "12"},
    )
    assert error_msg is None

    lv_a, error_msg = pm.add_logical_volume("channel_lv", "channel_block", "G4_Galactic")
    assert error_msg is None
    lv_b, error_msg = pm.add_logical_volume("channel_lv_copy", "channel_block", "G4_Galactic")
    assert error_msg is None

    pv_a, error_msg = pm.add_physical_volume(
        "World",
        "channel_pv",
        "channel_lv",
        {"x": "0", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    assert error_msg is None
    pv_b, error_msg = pm.add_physical_volume(
        "World",
        "channel_pv_copy",
        "channel_lv_copy",
        {"x": "30", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    assert error_msg is None

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_channel_runtime",
            "name": "fixture_channels",
            "generator_type": "channel_cut_array",
            "target": {
                "solid_ref": {
                    "id": solid_dict["id"],
                    "name": solid_dict["name"],
                },
            },
            "array": {
                "count": 4,
                "linear_pitch_mm": 5,
                "axis": "y",
                "origin_offset_mm": {"x": 1, "y": -1.5},
            },
            "channel": {
                "width_mm": 1.25,
                "depth_mm": 7,
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_channel_runtime")
    assert error_msg is None
    assert result["channel_count"] == 4
    assert result["updated_logical_volume_names"] == ["channel_lv", "channel_lv_copy"]

    cutter_name = result["cutter_solid_name"]
    result_name = result["result_solid_name"]
    cutter_solid = pm.current_geometry_state.solids[cutter_name]
    result_solid = pm.current_geometry_state.solids[result_name]

    assert cutter_solid.type == "box"
    assert float(cutter_solid.raw_parameters["x"]) == pytest.approx(24.0)
    assert float(cutter_solid.raw_parameters["y"]) == pytest.approx(1.25)
    assert float(cutter_solid.raw_parameters["z"]) == pytest.approx(7.0)

    assert result_solid.type == "boolean"
    recipe = result_solid.raw_parameters["recipe"]
    assert recipe[0] == {"op": "base", "solid_ref": "channel_block"}
    assert len(recipe) == 5
    assert [
        (
            float(item["transform"]["position"]["x"]),
            float(item["transform"]["position"]["y"]),
            float(item["transform"]["position"]["z"]),
        )
        for item in recipe[1:]
    ] == pytest.approx([
        (1.0, -9.0, 2.5),
        (1.0, -4.0, 2.5),
        (1.0, 1.0, 2.5),
        (1.0, 6.0, 2.5),
    ])

    assert pm.current_geometry_state.logical_volumes["channel_lv"].solid_ref == result_name
    assert pm.current_geometry_state.logical_volumes["channel_lv_copy"].solid_ref == result_name

    entry = pm.current_geometry_state.detector_feature_generators[0]
    assert entry["realization"]["status"] == "generated"
    assert entry["realization"]["result_solid_ref"] == {
        "id": result_solid.id,
        "name": result_name,
    }
    assert entry["realization"]["generated_object_refs"]["solid_refs"] == [
        {"id": result_solid.id, "name": result_name},
        {"id": cutter_solid.id, "name": cutter_name},
    ]
    assert entry["realization"]["generated_object_refs"]["logical_volume_refs"] == [
        {"id": lv_a["id"], "name": "channel_lv"},
        {"id": lv_b["id"], "name": "channel_lv_copy"},
    ]
    assert entry["realization"]["generated_object_refs"]["placement_refs"] == [
        {"id": pv_a["id"], "name": "channel_pv"},
        {"id": pv_b["id"], "name": "channel_pv_copy"},
    ]


def test_channel_cut_array_realization_requires_instantiated_target_lv():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "detached_channel_block",
        "box",
        {"x": "24", "y": "18", "z": "12"},
    )
    assert error_msg is None

    target_lv, error_msg = pm.add_logical_volume(
        "detached_channel_lv",
        solid_dict["name"],
        "G4_Galactic",
    )
    assert error_msg is None

    target_lv_state = pm.current_geometry_state.logical_volumes[target_lv["name"]]
    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_channel_detached_target",
            "name": "detached_channels",
            "generator_type": "channel_cut_array",
            "target": {
                "solid_ref": {
                    "id": solid_dict["id"],
                    "name": solid_dict["name"],
                },
                "logical_volume_refs": [
                    {
                        "id": target_lv_state.id,
                        "name": target_lv_state.name,
                    },
                ],
            },
            "array": {
                "count": 3,
                "linear_pitch_mm": 5.0,
                "axis": "y",
                "origin_offset_mm": {"x": 0.0, "y": 0.0},
            },
            "channel": {
                "width_mm": 1.25,
                "depth_mm": 6.0,
            },
        }
    ])

    result, error_msg = pm.realize_detector_feature_generator("dfg_channel_detached_target")

    assert result is None
    assert error_msg == (
        "Channel-cut generators require at least one targeted "
        "logical volume 'detached_channel_lv' to already be placed in the live scene "
        "so generated cuts are visible."
    )
    assert target_lv_state.solid_ref == "detached_channel_block"


def test_channel_cut_array_realization_reuses_result_and_keeps_targeted_lv_subset_on_revision():
    pm = _make_pm()

    solid_dict, error_msg = pm.add_solid(
        "refresh_channel_block",
        "box",
        {"x": "24", "y": "18", "z": "12"},
    )
    assert error_msg is None

    lv_a, error_msg = pm.add_logical_volume("refresh_channel_lv", "refresh_channel_block", "G4_Galactic")
    assert error_msg is None
    lv_b, error_msg = pm.add_logical_volume("refresh_channel_lv_copy", "refresh_channel_block", "G4_Galactic")
    assert error_msg is None

    pv_a, error_msg = pm.add_physical_volume(
        "World",
        "refresh_channel_pv",
        "refresh_channel_lv",
        {"x": "0", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    assert error_msg is None
    pv_b, error_msg = pm.add_physical_volume(
        "World",
        "refresh_channel_pv_copy",
        "refresh_channel_lv_copy",
        {"x": "30", "y": "0", "z": "0"},
        {"x": "0", "y": "0", "z": "0"},
        {"x": "1", "y": "1", "z": "1"},
    )
    assert error_msg is None

    pm.current_geometry_state.detector_feature_generators = _normalize_detector_feature_generators([
        {
            "generator_id": "dfg_channel_refresh",
            "name": "refresh_channels",
            "generator_type": "channel_cut_array",
            "target": {
                "solid_ref": {
                    "id": solid_dict["id"],
                    "name": solid_dict["name"],
                },
                "logical_volume_refs": [
                    {
                        "id": lv_a["id"],
                        "name": lv_a["name"],
                    },
                ],
            },
            "array": {
                "count": 3,
                "linear_pitch_mm": 6.0,
                "axis": "x",
                "origin_offset_mm": {"x": 0.0, "y": 1.0},
            },
            "channel": {
                "width_mm": 1.5,
                "depth_mm": 6.0,
            },
        }
    ])

    first_result, error_msg = pm.realize_detector_feature_generator("dfg_channel_refresh")
    assert error_msg is None
    assert first_result["updated_logical_volume_names"] == ["refresh_channel_lv"]

    entry = pm.current_geometry_state.detector_feature_generators[0]
    entry["array"]["count"] = 4
    entry["array"]["linear_pitch_mm"] = 5.0
    entry["array"]["axis"] = "y"
    entry["array"]["origin_offset_mm"]["x"] = 1.0
    entry["array"]["origin_offset_mm"]["y"] = -1.5
    entry["channel"]["width_mm"] = 1.25
    entry["channel"]["depth_mm"] = 7.0

    second_result, error_msg = pm.realize_detector_feature_generator("dfg_channel_refresh")
    assert error_msg is None
    assert second_result["result_solid_name"] == first_result["result_solid_name"]
    assert second_result["cutter_solid_name"] == first_result["cutter_solid_name"]
    assert second_result["updated_logical_volume_names"] == ["refresh_channel_lv"]

    result_solid = pm.current_geometry_state.solids[first_result["result_solid_name"]]
    cutter_solid = pm.current_geometry_state.solids[first_result["cutter_solid_name"]]
    assert float(cutter_solid.raw_parameters["x"]) == pytest.approx(24.0)
    assert float(cutter_solid.raw_parameters["y"]) == pytest.approx(1.25)
    assert float(cutter_solid.raw_parameters["z"]) == pytest.approx(7.0)
    assert [
        (
            float(item["transform"]["position"]["x"]),
            float(item["transform"]["position"]["y"]),
            float(item["transform"]["position"]["z"]),
        )
        for item in result_solid.raw_parameters["recipe"][1:]
    ] == pytest.approx([
        (1.0, -9.0, 2.5),
        (1.0, -4.0, 2.5),
        (1.0, 1.0, 2.5),
        (1.0, 6.0, 2.5),
    ])

    assert pm.current_geometry_state.logical_volumes["refresh_channel_lv"].solid_ref == first_result["result_solid_name"]
    assert pm.current_geometry_state.logical_volumes["refresh_channel_lv_copy"].solid_ref == "refresh_channel_block"

    assert entry["target"]["logical_volume_refs"] == [
        {"id": lv_a["id"], "name": "refresh_channel_lv"},
    ]
    assert entry["realization"]["generated_object_refs"]["logical_volume_refs"] == [
        {"id": lv_a["id"], "name": "refresh_channel_lv"},
    ]
    assert entry["realization"]["generated_object_refs"]["placement_refs"] == [
        {"id": pv_a["id"], "name": "refresh_channel_pv"},
    ]

    scene_names = {
        item["name"]
        for item in pm.get_threejs_description()
        if item.get("name", "").startswith("refresh_channel_pv")
    }
    assert scene_names == {
        "refresh_channel_pv",
        "refresh_channel_pv_copy",
    }


def test_patterned_hole_starter_example_roundtrips_saved_generators():
    pm = _load_patterned_hole_starter_pm()

    generators = {
        entry["generator_id"]: entry
        for entry in pm.current_geometry_state.detector_feature_generators
    }
    assert sorted(generators) == [
        "dfg_example_circular",
        "dfg_example_rectangular",
    ]

    rectangular = generators["dfg_example_rectangular"]
    assert rectangular["generator_type"] == "rectangular_drilled_hole_array"
    assert rectangular["realization"]["status"] == "generated"
    assert rectangular["pattern"] == {
        "count_x": 3,
        "count_y": 2,
        "pitch_mm": {"x": 4.5, "y": 5.0},
        "origin_offset_mm": {"x": 0.75, "y": -0.5},
        "anchor": "target_center",
    }

    circular = generators["dfg_example_circular"]
    assert circular["generator_type"] == "circular_drilled_hole_array"
    assert circular["realization"]["status"] == "generated"
    assert circular["pattern"] == {
        "count": 5,
        "radius_mm": 3.5,
        "orientation_deg": 18.0,
        "origin_offset_mm": {"x": -0.5, "y": 1.0},
        "anchor": "target_center",
    }

    assert pm.current_geometry_state.logical_volumes["starter_rect_lv"].solid_ref == "starter_rectangular_holes__result"
    assert pm.current_geometry_state.logical_volumes["starter_circular_lv"].solid_ref == "starter_circular_holes__result"

    saved_payload = json.loads(pm.save_project_to_json_string())
    saved_generators = {
        entry["generator_id"]: entry
        for entry in saved_payload["detector_feature_generators"]
    }
    assert saved_generators["dfg_example_rectangular"]["target"]["solid_ref"]["name"] == "starter_rect_block"
    assert saved_generators["dfg_example_circular"]["target"]["solid_ref"]["name"] == "starter_circular_block"
    assert saved_generators["dfg_example_rectangular"]["realization"]["result_solid_ref"]["name"] == "starter_rectangular_holes__result"
    assert saved_generators["dfg_example_circular"]["realization"]["result_solid_ref"]["name"] == "starter_circular_holes__result"


def test_patterned_hole_starter_example_rebuilds_hole_recipes_deterministically():
    pm = _load_patterned_hole_starter_pm()

    rectangular_entry = next(
        entry
        for entry in pm.current_geometry_state.detector_feature_generators
        if entry["generator_id"] == "dfg_example_rectangular"
    )
    circular_entry = next(
        entry
        for entry in pm.current_geometry_state.detector_feature_generators
        if entry["generator_id"] == "dfg_example_circular"
    )

    rectangular_result, error_msg = pm.realize_detector_feature_generator("dfg_example_rectangular")
    assert error_msg is None
    assert rectangular_result["hole_count"] == 6
    assert rectangular_result["result_solid_name"] == rectangular_entry["realization"]["result_solid_ref"]["name"]
    assert rectangular_result["cutter_solid_name"] == rectangular_entry["realization"]["generated_object_refs"]["solid_refs"][1]["name"]
    assert sorted(
        name for name in pm.current_geometry_state.solids
        if name.startswith("starter_rectangular_holes__")
    ) == [
        "starter_rectangular_holes__cutter",
        "starter_rectangular_holes__result",
    ]

    rectangular_recipe = pm.current_geometry_state.solids["starter_rectangular_holes__result"].raw_parameters["recipe"]
    assert [
        (
            float(item["transform"]["position"]["x"]),
            float(item["transform"]["position"]["y"]),
            float(item["transform"]["position"]["z"]),
        )
        for item in rectangular_recipe[1:]
    ] == pytest.approx(
        [
            (-3.75, -3.0, 1.0),
            (0.75, -3.0, 1.0),
            (5.25, -3.0, 1.0),
            (-3.75, 2.0, 1.0),
            (0.75, 2.0, 1.0),
            (5.25, 2.0, 1.0),
        ]
    )

    circular_result, error_msg = pm.realize_detector_feature_generator("dfg_example_circular")
    assert error_msg is None
    assert circular_result["hole_count"] == 5
    assert circular_result["result_solid_name"] == circular_entry["realization"]["result_solid_ref"]["name"]
    assert circular_result["cutter_solid_name"] == circular_entry["realization"]["generated_object_refs"]["solid_refs"][1]["name"]
    assert sorted(
        name for name in pm.current_geometry_state.solids
        if name.startswith("starter_circular_holes__")
    ) == [
        "starter_circular_holes__cutter",
        "starter_circular_holes__result",
    ]

    circular_recipe = pm.current_geometry_state.solids["starter_circular_holes__result"].raw_parameters["recipe"]
    assert [
        (
            float(item["transform"]["position"]["x"]),
            float(item["transform"]["position"]["y"]),
            float(item["transform"]["position"]["z"]),
        )
        for item in circular_recipe[1:]
    ] == pytest.approx(
        [
            (2.82869780703, 2.08155948031, 1.5),
            (-0.5, 4.5, 1.5),
            (-3.82869780703, 2.08155948031, 1.5),
            (-2.55724838302, -1.83155948031, 1.5),
            (1.55724838302, -1.83155948031, 1.5),
        ]
    )
