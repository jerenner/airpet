#!/usr/bin/env python3
"""
Create a simple test project for optimization tool testing.
Sets up a basic parameterized geometry for end-to-end AI tool testing.
"""

import sys
import os

# Add parent directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

from src.expression_evaluator import ExpressionEvaluator
from src.project_manager import ProjectManager

def create_test_project(output_path="projects/test_optimization"):
    """Create a simple test project for optimization."""
    
    pm = ProjectManager(ExpressionEvaluator())
    pm.create_empty_project()
    
    print("Creating test project for optimization tools...")
    print("="*60)
    
    # Step 1: Create parameterized defines
    print("\n1. Creating parameterized defines...")
    obj, err = pm.add_define("silicon_thickness", "constant", "0.5", "mm", "geometry")
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: silicon_thickness = 0.5 mm")
    
    obj, err = pm.add_define("detector_width", "constant", "10.0", "mm", "geometry")
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: detector_width = 10.0 mm")
    
    obj, err = pm.add_define("detector_height", "constant", "10.0", "mm", "geometry")
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: detector_height = 10.0 mm")
    
    obj, err = pm.add_define("world_size", "constant", "100.0", "mm", "geometry")
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: world_size = 100.0 mm")
    
    # Step 2: Create materials
    print("\n2. Creating materials...")
    mat, err = pm.add_material("Silicon", {"mat_type": "standard", "Z_expr": "14", "A_expr": "28.0855", "density_expr": "2.329"})
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: Silicon material")
    
    # Create Air material (not in default project)
    mat, err = pm.add_material("Air", {"mat_type": "standard", "Z_expr": "7.2", "A_expr": "14.399", "density_expr": "0.001205"})
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: Air material")
    
    # Step 3: Create solids
    print("\n3. Creating solids...")
    solid, err = pm.add_solid("DetectorBox", "box", {"x": "detector_width/2", "y": "detector_height/2", "z": "silicon_thickness/2"})
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: DetectorBox solid")
    
    solid, err = pm.add_solid("WorldBox", "box", {"x": "world_size/2", "y": "world_size/2", "z": "world_size/2"})
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: WorldBox solid")
    
    # Step 4: Create logical volumes
    print("\n4. Creating logical volumes...")
    lv, err = pm.add_logical_volume("Detector", "DetectorBox", "Silicon", {"color": {"r": 0.0, "g": 0.5, "b": 1.0, "a": 0.8}})
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: Detector logical volume")
    
    lv, err = pm.add_logical_volume("World", "WorldBox", "Air", {"color": {"r": 0.8, "g": 0.8, "b": 0.8, "a": 1.0}})
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: World logical volume")
    
    # Step 5: Create position and rotation defines
    print("\n5. Creating transform defines...")
    pos, err = pm.add_define("detector_position", "position", {"x": "0", "y": "0", "z": "0"}, "mm", "geometry")
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: detector_position = (0, 0, 0) mm")
    
    rot, err = pm.add_define("detector_rotation", "rotation", {"x": "0", "y": "0", "z": "0"}, "degree", "angle")
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: detector_rotation = (0, 0, 0) degree")
    
    # Step 6: Place detector in world
    print("\n6. Placing detector in world...")
    pv, err = pm.add_physical_volume("World", "DetectorPV", "Detector", {'x': '0', 'y': '0', 'z': '0'}, {'x': '0', 'y': '0', 'z': '0'}, {'x': '1', 'y': '1', 'z': '1'})
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Placed: Detector in World")
    
    # Step 7: Create source (simplified)
    print("\n7. Creating particle source...")
    # GPS commands for electron source at z=-20mm, pointing in +z direction
    gps_commands = [
        "particle electron",
        "pos 0 0 -20 mm",
        "dist 0 0 0 mm",
        "direction 0 0 1",
        "energy 300 keV mono",
        "num 1"
    ]
    source, err = pm.add_particle_source("ElectronSource", gps_commands, "detector_position", "detector_rotation", 1.0, None)
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: ElectronSource (300 keV, at z=-20mm)")
    
    # Step 8: Activate source
    print("\n8. Activating source...")
    # Get the source ID
    source_id = None
    for sid, sdata in pm.current_geometry_state.sources.items():
        if sdata.name == "ElectronSource":
            source_id = sid
            break
    
    if source_id:
        pm.set_active_source(source_id)
        print(f"   Activated: ElectronSource")
    else:
        print(f"   Warning: Could not find source ID for ElectronSource")
    
    # Step 9: Register parameter for optimization
    print("\n9. Registering parameter for optimization...")
    entry, err = pm.upsert_parameter_registry_entry("silicon_thickness_param", {
        'target_type': 'define',
        'target_ref': {'name': 'silicon_thickness'},
        'bounds': {'min': 0.1, 'max': 2.0},
        'default': 0.5,
        'units': 'mm',
        'enabled': True
    })
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Registered: silicon_thickness_param (0.1-2.0 mm)")
    
    # Step 10: Create parameter study
    print("\n10. Creating parameter study...")
    config = {
        'mode': 'random',
        'parameters': ['silicon_thickness_param'],
        'objectives': [
            {
                'metric': 'success_flag',
                'name': 'detection_efficiency',
                'direction': 'maximize'
            }
        ],
        'random': {
            'samples': 20,
            'seed': 42
        }
    }
    study, err = pm.upsert_param_study("silicon_thickness_study", config)
    if err:
        print(f"   Error: {err}")
        return
    print(f"   Created: silicon_thickness_study (random, 20 samples)")
    
    # Step 11: Save project
    print("\n11. Saving project...")
    pm.save_project_version("Initial test project for optimization")
    print(f"   Saved: project state")
    
    print("\n" + "="*60)
    print("Test project created successfully!")
    print("="*60)
    print("\nProject contains:")
    print("  - Silicon detector (parameterized thickness: 0.1-2.0 mm)")
    print("  - Electron source (300 keV, normal incidence)")
    print("  - Parameter study for thickness optimization")
    print("\nYou can now test AI optimization tools with this project.")
    print("Try asking: 'Optimize the silicon thickness for maximum efficiency'")

if __name__ == "__main__":
    create_test_project()
