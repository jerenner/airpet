# src/templates.py
from typing import Dict, Any, List
from .geometry_types import Solid, LogicalVolume, PhysicalVolumePlacement, Material

def create_sipm_array(rows: int, cols: int, pitch: float, size: float = 3.0, thickness: float = 1.0):
    """
    Generates a recipe for a SiPM array.
    Returns a dict with solids, lvs, and placements.
    """
    results = {
        "solids": [],
        "logical_volumes": [],
        "placements": []
    }
    
    # 1. SiPM Solid
    sipm_solid_name = f"SiPM_Solid_{size}mm"
    results["solids"].append(Solid(sipm_solid_name, "box", {"x": str(size), "y": str(size), "z": str(thickness)}))
    
    # 2. SiPM LV
    sipm_lv_name = f"SiPM_LV_{size}mm"
    results["logical_volumes"].append(LogicalVolume(sipm_lv_name, sipm_solid_name, "G4_SILICON", is_sensitive=True))
    
    # 3. Placements in a local grid
    start_x = -(cols - 1) * pitch / 2.0
    start_y = -(rows - 1) * pitch / 2.0
    
    for r in range(rows):
        for c in range(cols):
            name = f"SiPM_PV_{r}_{c}"
            pos = {
                "x": str(start_x + c * pitch),
                "y": str(start_y + r * pitch),
                "z": "0"
            }
            results["placements"].append({
                "name": name,
                "volume_ref": sipm_lv_name,
                "position": pos,
                "rotation": {"x": "0", "y": "0", "z": "0"}
            })
            
    return results

def create_cryostat(inner_radius: float, thickness: float, length: float, material: str = "G4_Al"):
    """Creates a simple cylindrical cryostat/vessel."""
    results = {"solids": [], "logical_volumes": [], "placements": []}
    
    outer_radius = inner_radius + thickness
    solid_name = f"Cryostat_Solid_{inner_radius}mm"
    results["solids"].append(Solid(solid_name, "tube", {
        "rmin": str(inner_radius),
        "rmax": str(outer_radius),
        "z": str(length),
        "startphi": "0",
        "deltaphi": "2*pi"
    }))
    
    lv_name = f"Cryostat_LV_{inner_radius}mm"
    results["logical_volumes"].append(LogicalVolume(lv_name, solid_name, material))
    
    return results

def create_phantom(radius: float, length: float, material: str = "G4_WATER"):
    """Creates a simple water phantom."""
    results = {"solids": [], "logical_volumes": [], "placements": []}
    
    solid_name = f"Phantom_Solid_{radius}mm"
    results["solids"].append(Solid(solid_name, "tube", {
        "rmin": "0",
        "rmax": str(radius),
        "z": str(length),
        "startphi": "0",
        "deltaphi": "2*pi"
    }))
    
    lv_name = f"Phantom_LV_{radius}mm"
    results["logical_volumes"].append(LogicalVolume(lv_name, solid_name, material))
    
    return results

PHYSICS_TEMPLATES = {
    "sipm_array": {
        "func": create_sipm_array,
        "description": "Create a rectangular grid of SiPM sensors (Silicon Photomultipliers).",
        "parameters": {
            "rows": {"type": "integer"},
            "cols": {"type": "integer"},
            "pitch": {"type": "number", "description": "Center-to-center distance (mm)"},
            "size": {"type": "number", "description": "Side length of one SiPM (mm)"},
            "thickness": {"type": "number", "description": "Thickness (mm)"}
        }
    },
    "cryostat": {
        "func": create_cryostat,
        "description": "Create a cylindrical vessel or shield.",
        "parameters": {
            "inner_radius": {"type": "number"},
            "thickness": {"type": "number"},
            "length": {"type": "number"},
            "material": {"type": "string", "default": "G4_Al"}
        }
    },
    "phantom": {
        "func": create_phantom,
        "description": "Create a cylindrical phantom (usually water).",
        "parameters": {
            "radius": {"type": "number"},
            "length": {"type": "number"},
            "material": {"type": "string", "default": "G4_WATER"}
        }
    }
}
