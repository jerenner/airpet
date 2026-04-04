from numbers import Real
from pathlib import Path

import pytest

from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "gdml" / "corpus"
AIRPET_EXAMPLE_DIR = Path(__file__).resolve().parents[1] / "geom"


def _normalize(value):
    if isinstance(value, dict):
        return tuple((key, _normalize(val)) for key, val in sorted(value.items()))
    if isinstance(value, list):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, Real) and not isinstance(value, bool):
        return round(float(value), 9)
    return value


def _placement_signature(pv):
    return (
        pv.name,
        pv.volume_ref,
        pv.copy_number,
        _normalize(pv._evaluated_position),
        _normalize(pv._evaluated_rotation),
        _normalize(pv._evaluated_scale),
    )


def _param_signature(param):
    return (
        str(param.number),
        _normalize(param._evaluated_position),
        _normalize(param._evaluated_rotation),
        param.dimensions_type,
        _normalize(param._evaluated_dimensions),
    )


def _param_volume_signature(param_volume):
    return (
        param_volume.name,
        param_volume.volume_ref,
        int(getattr(param_volume, "_evaluated_ncopies", param_volume.ncopies)),
        tuple(_param_signature(param) for param in param_volume.parameters),
    )


def _solid_signature(solid):
    if solid.type == "boolean":
        return (
            solid.name,
            solid.type,
            _normalize(solid.raw_parameters.get("recipe", [])),
        )

    if solid.type == "tessellated":
        return (
            solid.name,
            solid.type,
            _normalize(solid.raw_parameters.get("facets", [])),
        )

    return (
        solid.name,
        solid.type,
        _normalize(solid._evaluated_parameters),
    )


def _logical_volume_signature(lv):
    if lv.content_type == "physvol":
        content_signature = tuple(_placement_signature(pv) for pv in lv.content)
    elif lv.content_type == "parameterised":
        content_signature = _param_volume_signature(lv.content)
    else:
        content_signature = _normalize(lv.content)

    return (
        lv.name,
        lv.solid_ref,
        lv.material_ref,
        lv.content_type,
        content_signature,
    )


def _assembly_signature(assembly):
    return (
        assembly.name,
        tuple(_placement_signature(pv) for pv in assembly.placements),
    )


def _state_signature(state):
    return {
        "world_volume_ref": state.world_volume_ref,
        "defines": tuple(
            sorted(
                (name, define.type, _normalize(define.value))
                for name, define in state.defines.items()
            )
        ),
        "materials": tuple(
            sorted(
                (
                    name,
                    material.mat_type,
                    material.state,
                    _normalize(material._evaluated_Z),
                    _normalize(material._evaluated_A),
                    _normalize(material._evaluated_density),
                    _normalize(material.components),
                )
                for name, material in state.materials.items()
            )
        ),
        "solids": tuple(sorted(_solid_signature(solid) for solid in state.solids.values())),
        "logical_volumes": tuple(
            sorted(_logical_volume_signature(lv) for lv in state.logical_volumes.values())
        ),
        "assemblies": tuple(sorted(_assembly_signature(asm) for asm in state.assemblies.values())),
    }


def _load_state(gdml_text):
    pm = ProjectManager(ExpressionEvaluator())
    state = pm.load_gdml_from_string(gdml_text)
    return pm, state


def _roundtrip_state(fixture_path):
    source_text = fixture_path.read_text(encoding="utf-8")
    pm, original_state = _load_state(source_text)
    roundtrip_pm, roundtrip_state = _load_state(pm.export_to_gdml_string())
    return pm, original_state, roundtrip_pm, roundtrip_state


def _assert_case_expectations(state, expected):
    for material_name, expected_state in expected.get("materials", {}).items():
        assert material_name in state.materials
        assert state.materials[material_name].state == expected_state

    for solid_name, expected_type in expected.get("solids", {}).items():
        assert solid_name in state.solids
        assert state.solids[solid_name].type == expected_type

    for define_name in expected.get("defines", ()):
        assert define_name in state.defines

    world_children = expected.get("world_children")
    if world_children is not None:
        world_lv = state.logical_volumes[state.world_volume_ref]
        assert tuple(pv.name for pv in world_lv.content) == tuple(world_children)

    for assembly_name, expected_child_names in expected.get("assembly_children", {}).items():
        assert assembly_name in state.assemblies
        assembly = state.assemblies[assembly_name]
        assert tuple(pv.name for pv in assembly.placements) == tuple(expected_child_names)

    for solid_name, expected_count in expected.get("tessellated_facets", {}).items():
        facets = state.solids[solid_name].raw_parameters.get("facets", [])
        assert len(facets) == expected_count

    for lv_name, expected_details in expected.get("parameterised_lvs", {}).items():
        lv = state.logical_volumes[lv_name]
        assert lv.content_type == "parameterised"
        param_volume = lv.content
        assert param_volume.volume_ref == expected_details["volume_ref"]
        assert int(param_volume._evaluated_ncopies) == expected_details["ncopies"]
        assert tuple(param.dimensions_type for param in param_volume.parameters) == tuple(
            expected_details["dimensions_types"]
        )
        assert tuple(str(param.number) for param in param_volume.parameters) == tuple(
            expected_details["numbers"]
        )

    for solid_name, expected_ops in expected.get("boolean_ops", {}).items():
        recipe = state.solids[solid_name].raw_parameters.get("recipe", [])
        assert tuple(item.get("op") for item in recipe) == tuple(expected_ops)


CORPUS_CASES = [
    pytest.param(
        "materials_boolean.gdml",
        {
            "materials": {"Air": "gas", "Aluminum": "solid"},
            "solids": {
                "world_box": "box",
                "housing_outer": "box",
                "housing_void": "box",
                "housing_cut": "boolean",
            },
            "world_children": ("housing_pv",),
            "boolean_ops": {"housing_cut": ("base", "subtraction")},
        },
        id="materials-boolean",
    ),
    pytest.param(
        "assembly_tessellated.gdml",
        {
            "materials": {"Air": "gas", "Silicon": "solid", "Aluminum": "solid"},
            "defines": ("mesh_v0", "mesh_v1", "mesh_v2", "mesh_v3"),
            "solids": {
                "roof_mesh": "tessellated",
                "world_box": "box",
                "sensor_box": "box",
                "support_box": "box",
            },
            "world_children": ("assembly_pv", "mesh_pv"),
            "assembly_children": {"detector_assembly": ("sensor_arm_pv", "support_arm_pv")},
            "tessellated_facets": {"roof_mesh": 2},
        },
        id="assembly-tessellated",
    ),
    pytest.param(
        "parameterised_placements.gdml",
        {
            "materials": {"Air": "gas", "Silicon": "solid"},
            "solids": {
                "world_box": "box",
                "array_box": "box",
                "tile_trd": "trd",
            },
            "world_children": ("array_pv",),
            "parameterised_lvs": {
                "array_lv": {
                    "volume_ref": "tile_lv",
                    "ncopies": 3,
                    "dimensions_types": ("trd_dimensions", "trd_dimensions", "trd_dimensions"),
                    "numbers": ("0", "1", "2"),
                }
            },
        },
        id="parameterised-placements",
    ),
    pytest.param(
        "parameterised_polycone_polyhedra.gdml",
        {
            "materials": {"Air": "gas", "Aluminum": "solid", "Silicon": "solid"},
            "solids": {
                "world_box": "box",
                "polycone_host_box": "box",
                "polycone_solid": "polycone",
                "polyhedra_host_box": "box",
                "polyhedra_solid": "polyhedra",
            },
            "world_children": ("polycone_container_pv", "polyhedra_container_pv"),
            "parameterised_lvs": {
                "polycone_container_lv": {
                    "volume_ref": "polycone_lv",
                    "ncopies": 2,
                    "dimensions_types": (
                        "polycone_dimensions",
                        "polycone_dimensions",
                    ),
                    "numbers": ("0", "1"),
                },
                "polyhedra_container_lv": {
                    "volume_ref": "polyhedra_lv",
                    "ncopies": 2,
                    "dimensions_types": (
                        "polyhedra_dimensions",
                        "polyhedra_dimensions",
                    ),
                    "numbers": ("0", "1"),
                },
            },
        },
        id="parameterised-polycone-polyhedra",
    ),
    pytest.param(
        "test_polycones.gdml",
        {
            "materials": {"Vacuum": None, "Lead": None},
            "defines": (
                "pos_solid_cone",
                "pos_hollow_cone",
                "pos_segmented_cone",
                "pos_generic_cone",
                "identity",
            ),
            "solids": {
                "WorldBox": "box",
                "SolidTrafficCone": "polycone",
                "HollowNozzle": "polycone",
                "SegmentedCone": "polycone",
                "VaseShape": "genericPolycone",
            },
            "world_children": (
                "pvSolidCone",
                "pvHollowNozzle",
                "pvSegmentedCone",
                "pvVaseShape",
            ),
            "warning_free": True,
        },
        id="test-polycones",
    ),
]


@pytest.mark.parametrize("fixture_name, expected", CORPUS_CASES)
def test_gdml_corpus_round_trips(fixture_name, expected):
    fixture_path = FIXTURE_DIR / fixture_name
    pm, original_state, roundtrip_pm, roundtrip_state = _roundtrip_state(fixture_path)

    if expected.get("warning_free"):
        assert pm.gdml_parser.import_warnings == []
        assert roundtrip_pm.gdml_parser.import_warnings == []

    assert _state_signature(original_state) == _state_signature(roundtrip_state)
    _assert_case_expectations(original_state, expected)
    _assert_case_expectations(roundtrip_state, expected)


@pytest.mark.parametrize(
    "fixture_name, dimensions_type",
    [
        pytest.param("parameterized.gdml", "box_dimensions", id="airpet-parameterized-box"),
        pytest.param("pTube.gdml", "tube_dimensions", id="airpet-parameterized-tube"),
    ],
)
def test_airpet_parameterized_examples_round_trip_warning_free(fixture_name, dimensions_type):
    fixture_path = AIRPET_EXAMPLE_DIR / fixture_name
    pm, original_state = _load_state(fixture_path.read_text(encoding="utf-8"))

    assert pm.gdml_parser.import_warnings == []

    param_volume = original_state.logical_volumes["Tracker"].content
    assert param_volume.volume_ref == "Chamber"
    assert int(param_volume.ncopies) == 5
    assert len(param_volume.parameters) == 5
    assert tuple(param.number for param in param_volume.parameters) == ("1", "2", "3", "4", "5")
    assert tuple(param.dimensions_type for param in param_volume.parameters) == (
        dimensions_type,
        dimensions_type,
        dimensions_type,
        dimensions_type,
        dimensions_type,
    )

    roundtrip_pm, roundtrip_state = _load_state(pm.export_to_gdml_string())

    roundtrip_param_volume = roundtrip_state.logical_volumes["Tracker"].content
    assert roundtrip_param_volume.volume_ref == "Chamber"
    assert int(roundtrip_param_volume.ncopies) == 5
    assert len(roundtrip_param_volume.parameters) == 5
    assert tuple(param.number for param in roundtrip_param_volume.parameters) == (
        "1",
        "2",
        "3",
        "4",
        "5",
    )
    assert tuple(param.dimensions_type for param in roundtrip_param_volume.parameters) == (
        dimensions_type,
        dimensions_type,
        dimensions_type,
        dimensions_type,
        dimensions_type,
    )

    assert pm.gdml_parser.import_warnings == []
    assert roundtrip_pm.gdml_parser.import_warnings == []
