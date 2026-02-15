import pytest
import numpy as np
from src.geometry_types import (
    GeometryState, LogicalVolume, Solid, PhysicalVolumePlacement,
    ReplicaVolume, DivisionVolume
)

def test_replica_unrolling():
    state = GeometryState()
    
    # 1. Define geometry
    # World -> Container (Replica) -> Crystal
    state.add_material(MagicMock(name="Air"))
    state.add_solid(Solid("world_solid", "box", {"x":100, "y":100, "z":100}))
    state.add_logical_volume(LogicalVolume("World", "world_solid", "Air"))
    state.world_volume_ref = "World"
    
    state.add_solid(Solid("crystal_solid", "box", {"x":10, "y":10, "z":10}))
    state.add_logical_volume(LogicalVolume("Crystal", "crystal_solid", "LSO"))
    
    # Create the container for the replica
    state.add_solid(Solid("container_solid", "box", {"x":100, "y":10, "z":10}))
    container_lv = LogicalVolume("Container", "container_solid", "Air")
    
    # Define the replica rule: 5 crystals along X axis
    replica = ReplicaVolume(
        name="RepRule",
        volume_ref="Crystal",
        number=5,
        direction={'x': '1', 'y': '0', 'z': '0'},
        width=20.0,
        offset=0.0
    )
    # Mock evaluated values (normally done by ProjectManager)
    replica._evaluated_number = 5
    replica._evaluated_width = 20.0
    replica._evaluated_offset = 0.0
    replica._evaluated_start_position = {'x':0, 'y':0, 'z':0}
    replica._evaluated_start_rotation = {'x':0, 'y':0, 'z':0}
    
    container_lv.add_child(replica)
    state.add_logical_volume(container_lv)
    
    # Place container in world
    pv_container = PhysicalVolumePlacement("PV_Container", "Container")
    pv_container._evaluated_position = {'x':0, 'y':0, 'z':0}
    state.get_logical_volume("World").add_child(pv_container)
    
    # 2. Get scene description
    scene = state.get_threejs_scene_description()
    
    # 3. Verify
    # Expect: World(1) + Container(1) + 5 Crystals = 7 objects
    assert len(scene) == 7
    
    # Find crystals
    crystals = [obj for obj in scene if obj['name'].startswith("Container_replica_")]
    assert len(crystals) == 5
    
    # Check spacing (width=20)
    # translation_dist = -width * (number - 1) * 0.5 + i * width
    # i=0 -> -20 * 4 * 0.5 = -40
    # i=1 -> -40 + 20 = -20
    # i=2 -> 0
    # i=3 -> 20
    # i=4 -> 40
    positions = sorted([c['position']['x'] for c in crystals])
    assert positions == [-40.0, -20.0, 0.0, 20.0, 40.0]
    
    # Check parentage
    container_obj = next(obj for obj in scene if obj['name'] == "PV_Container")
    for c in crystals:
        assert c['parent_id'] == container_obj['id']
        assert c['is_procedural_instance'] is True

def test_division_unrolling():
    state = GeometryState()
    
    # World -> Mother(Box) -> Slices
    state.add_solid(Solid("world_s", "box", {"x":100, "y":100, "z":100}))
    state.add_logical_volume(LogicalVolume("World", "world_s", "Air"))
    state.world_volume_ref = "World"
    
    mother_solid = Solid("mother_s", "box", {"x":10, "y":10, "z":100})
    mother_solid._evaluated_parameters = {"x": 10, "y": 10, "z": 100}
    state.add_solid(mother_solid)
    
    mother_lv = LogicalVolume("Mother", "mother_s", "Air")
    
    # Divide into 10 slices along Z
    division = DivisionVolume(
        name="DivRule",
        volume_ref="SliceLV",
        axis="kZAxis",
        number=10,
        offset=0.0
    )
    division._evaluated_number = 10
    division._evaluated_offset = 0.0
    
    state.add_logical_volume(LogicalVolume("SliceLV", "some_solid", "Lead"))
    
    mother_lv.add_child(division)
    state.add_logical_volume(mother_lv)
    
    pv_mother = PhysicalVolumePlacement("PV_Mother", "Mother")
    state.get_logical_volume("World").add_child(pv_mother)
    
    scene = state.get_threejs_scene_description()
    
    # Slices should exist
    slices = [obj for obj in scene if "division" in obj['name']]
    assert len(slices) == 10
    
    # Each slice should have its own temporary solid definition
    for s in slices:
        assert isinstance(s['solid_ref_for_threejs'], dict)
        assert s['solid_ref_for_threejs']['type'] == 'box'
        # width = 100 / 10 = 10
        assert s['solid_ref_for_threejs']['_evaluated_parameters']['z'] == 10.0

from unittest.mock import MagicMock
