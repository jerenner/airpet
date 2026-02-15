import pytest
from src.geometry_types import GeometryState, LogicalVolume, PhysicalVolumePlacement
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
