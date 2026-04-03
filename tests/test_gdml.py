import pytest
from src.geometry_types import GeometryState, LogicalVolume, PhysicalVolumePlacement, Material
from src.expression_evaluator import ExpressionEvaluator
from src.gdml_parser import GDMLParser
from src.gdml_writer import GDMLWriter

def test_topological_sort():
    state = GeometryState()
    
    # Create a hierarchy: World -> Box1 -> Box2
    lv_world = LogicalVolume("World", "solid_world", "mat_air")
    lv_box1 = LogicalVolume("Box1", "solid_box1", "mat_lead")
    lv_box2 = LogicalVolume("Box2", "solid_box2", "mat_lead")
    
    state.add_logical_volume(lv_world)
    state.add_logical_volume(lv_box1)
    state.add_logical_volume(lv_box2)
    state.world_volume_ref = "World"
    
    # Place Box2 inside Box1
    pv2 = PhysicalVolumePlacement("PV2", "Box2")
    lv_box1.add_child(pv2)
    
    # Place Box1 inside World
    pv1 = PhysicalVolumePlacement("PV1", "Box1")
    lv_world.add_child(pv1)
    
    writer = GDMLWriter(state)
    sorted_structures = writer._topological_sort_structures()
    
    # Expected order: Box2, then Box1, then World
    names = [s.name for s in sorted_structures]
    assert names.index("Box2") < names.index("Box1")
    assert names.index("Box1") < names.index("World")

def test_tessellated_solid_deduplication():
    from src.geometry_types import Solid
    state = GeometryState()
    
    # Solid with two identical facets (absolute vertices)
    v1 = {'x': 0, 'y': 0, 'z': 0}
    v2 = {'x': 1, 'y': 0, 'z': 0}
    v3 = {'x': 0, 'y': 1, 'z': 0}
    
    facets = [
        {'type': 'triangular', 'vertices': [v1, v2, v3]},
        {'type': 'triangular', 'vertices': [v1, v2, v3]}
    ]
    solid = Solid("Tess", "tessellated", {"facets": facets})
    state.add_solid(solid)
    
    writer = GDMLWriter(state)
    gdml_str = writer.get_gdml_string()
    
    # Verify that only 3 unique positions are defined in the output
    # Each position tag looks like: <position name="Tess_v0" unit="mm" x="0" y="0" z="0"/>
    assert gdml_str.count("<position") == 3


def test_material_density_is_written_with_explicit_gdml_unit():
    state = GeometryState()

    mat = Material(
        "G4_Si",
        Z_expr="14",
        A_expr="28.085",
        density_expr="2.33*g/cm3",
        state="solid",
    )
    mat._evaluated_density = 0.00233  # internal g/mm^3
    state.add_material(mat)

    writer = GDMLWriter(state)
    writer._add_materials()
    gdml_str = writer.get_gdml_string()

    assert '<D value="2.33" unit="g/cm3"/>' in gdml_str


def test_plain_numeric_density_is_preserved_as_gdml_g_per_cm3():
    state = GeometryState()

    mat = Material(
        "G4_Galactic",
        Z_expr="1",
        A_expr="1.01",
        density_expr="1.0e-25",
        state="gas",
    )
    mat._evaluated_density = 1.0e-25
    state.add_material(mat)

    writer = GDMLWriter(state)
    writer._add_materials()
    gdml_str = writer.get_gdml_string()

    assert '<D value="1e-25" unit="g/cm3"/>' in gdml_str or '<D value="1.0e-25" unit="g/cm3"/>' in gdml_str


@pytest.mark.parametrize(
    "value,unit,expected_density_expr,expected_internal_density,expected_export_value",
    [
        ("2.33", "g/cm3", "2.33*g/cm3", 0.00233, "2.33"),
        ("2.33", "mg/cm3", "2.33*mg/cm3", 2.33e-06, "0.00233"),
        ("2330", "kg/m3", "2330*kg/m3", 0.00233, "2.33"),
    ],
)
def test_gdml_material_density_units_round_trip(value, unit, expected_density_expr, expected_internal_density, expected_export_value):
    gdml = f"""<?xml version="1.0" encoding="UTF-8"?>
<gdml>
  <materials>
    <material name="Silicon" state="solid" Z="14">
      <D value="{value}" unit="{unit}"/>
      <atom value="28.085"/>
    </material>
  </materials>
</gdml>
"""

    parser = GDMLParser()
    state = parser.parse_gdml_string(gdml)
    material = state.materials["Silicon"]

    assert material.density_expr == expected_density_expr

    evaluator = ExpressionEvaluator()
    success, evaluated_density = evaluator.evaluate(material.density_expr, verbose=False)
    assert success
    assert evaluated_density == pytest.approx(expected_internal_density)

    material._evaluated_density = evaluated_density

    writer = GDMLWriter(state)
    gdml_str = writer.get_gdml_string()

    assert f'<D value="{expected_export_value}" unit="g/cm3"/>' in gdml_str
