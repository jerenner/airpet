# src/ai_tools.py

from typing import List, Dict, Any, Optional
from .geometry_types import GeometryState

def get_project_summary(pm) -> Dict[str, Any]:
    """Returns a high-level summary of the current project structure."""
    state = pm.current_geometry_state
    return {
        "project_name": pm.project_name,
        "world_volume": state.world_volume_ref,
        "counts": {
            "defines": len(state.defines),
            "materials": len(state.materials),
            "elements": len(state.elements),
            "solids": len(state.solids),
            "logical_volumes": len(state.logical_volumes),
            "assemblies": len(state.assemblies),
            "sources": len(state.sources)
        },
        "names": {
            "materials": list(state.materials.keys()),
            "solids": list(state.solids.keys()),
            "logical_volumes": list(state.logical_volumes.keys())
        }
    }

def get_component_details(pm, component_type: str, name: str) -> Optional[Dict[str, Any]]:
    """Returns full details for a specific component (define, material, solid, lv, assembly)."""
    return pm.get_object_details(component_type, name)

# Mapping of AI tools to ProjectManager methods
AI_GEOMETRY_TOOLS = [
    {
        "name": "get_project_summary",
        "description": "Get a high-level overview of the project structure, including names of all volumes and materials.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_component_details",
        "description": "Get the full JSON definition of a specific component to see its current parameters.",
        "parameters": {
            "type": "object",
            "properties": {
                "component_type": {
                    "type": "string", 
                    "enum": ["define", "material", "element", "solid", "logical_volume", "assembly", "particle_source", "physical_volume"]
                },
                "name": {"type": "string", "description": "The name of the component or its unique ID (for physical_volumes)."}
            },
            "required": ["component_type", "name"]
        }
    },
    {
        "name": "search_components",
        "description": "Search for components by name using a regex pattern.",
        "parameters": {
            "type": "object",
            "properties": {
                "component_type": {
                    "type": "string",
                    "enum": ["solid", "logical_volume", "material", "physical_volume"]
                },
                "pattern": {"type": "string", "description": "Regex pattern to match names."}
            },
            "required": ["component_type", "pattern"]
        }
    },
    {
        "name": "manage_define",
        "description": "Create or update a project variable (constant, expression, position, rotation).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "define_type": {"type": "string", "enum": ["constant", "expression", "position", "rotation", "variable"]},
                "value": {"type": "string", "description": "The expression string or a dict for position/rotation."},
                "unit": {"type": "string", "description": "Optional unit (mm, cm, deg, rad, etc.)"}
            },
            "required": ["name", "define_type", "value"]
        }
    },
    {
        "name": "manage_material",
        "description": "Create or update a material or element.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "density": {"type": "string", "description": "Density expression in g/cm3"},
                "Z": {"type": "string", "description": "Atomic number expression"},
                "A": {"type": "string", "description": "Atomic mass expression"},
                "components": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "ref": {"type": "string"},
                            "fraction": {"type": "string"},
                            "natoms": {"type": "string"}
                        }
                    }
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "create_primitive_solid",
        "description": "Create a new primitive shape (box, tube, cone, sphere, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "solid_type": {"type": "string", "enum": ["box", "tube", "cone", "sphere", "orb", "trd", "para", "trap"]},
                "params": {
                    "type": "object",
                    "description": "Dict of parameters. e.g., {'x': '100', 'y': '100', 'z': '100'} for a box."
                }
            },
            "required": ["name", "solid_type", "params"]
        }
    },
    {
        "name": "modify_solid",
        "description": "Update parameters of an existing solid.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "params": {"type": "object", "description": "Dict of parameters to update or replace."}
            },
            "required": ["name", "params"]
        }
    },
    {
        "name": "create_boolean_solid",
        "description": "Create a new boolean solid from existing solids.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "recipe": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "op": {"type": "string", "enum": ["base", "union", "subtraction", "intersection"]},
                            "solid_ref": {"type": "string"},
                            "transform": {
                                "type": "object",
                                "properties": {
                                    "position": {"type": "object"},
                                    "rotation": {"type": "object"}
                                }
                            }
                        }
                    }
                }
            },
            "required": ["name", "recipe"]
        }
    },
    {
        "name": "manage_logical_volume",
        "description": "Create or update a logical volume (binds a solid to a material).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "solid_ref": {"type": "string"},
                "material_ref": {"type": "string"},
                "is_sensitive": {"type": "boolean"}
            },
            "required": ["name"]
        }
    },
    {
        "name": "place_volume",
        "description": "Place a volume (Physical Volume) inside another volume.",
        "parameters": {
            "type": "object",
            "properties": {
                "parent_lv_name": {"type": "string"},
                "placed_lv_ref": {"type": "string"},
                "name": {"type": "string", "description": "Optional name for the placement."},
                "position": {"type": "object"},
                "rotation": {"type": "object"},
                "scale": {"type": "object"}
            },
            "required": ["parent_lv_name", "placed_lv_ref"]
        }
    },
    {
        "name": "modify_physical_volume",
        "description": "Update the transform or name of an existing physical volume placement.",
        "parameters": {
            "type": "object",
            "properties": {
                "pv_id": {"type": "string", "description": "The unique ID of the physical volume."},
                "name": {"type": "string"},
                "position": {"type": "object"},
                "rotation": {"type": "object"},
                "scale": {"type": "object"}
            },
            "required": ["pv_id"]
        }
    },
    {
        "name": "create_detector_ring",
        "description": "High-level tool to create a ring array of volumes (e.g., a PET ring).",
        "parameters": {
            "type": "object",
            "properties": {
                "parent_lv_name": {"type": "string"},
                "lv_to_place_ref": {"type": "string"},
                "ring_name": {"type": "string"},
                "num_detectors": {"type": "string", "description": "Number of detectors in one ring (expression string)."},
                "radius": {"type": "string", "description": "Radius of the ring (expression string)."},
                "center": {"type": "object", "description": "Center of the ring {'x':..., 'y':..., 'z':...}"},
                "orientation": {"type": "object", "description": "Orientation of the ring axes."},
                "point_to_center": {"type": "boolean", "description": "If true, detectors rotate to face the center."},
                "inward_axis": {"type": "string", "enum": ["+x", "-x", "+y", "-y", "+z", "-z"], "description": "Which local axis of the detector should point inward."},
                "num_rings": {"type": "string", "description": "Number of axial rings (expression string)."},
                "ring_spacing": {"type": "string", "description": "Axial distance between rings."}
            },
            "required": ["parent_lv_name", "lv_to_place_ref", "ring_name", "num_detectors", "radius"]
        }
    },
    {
        "name": "delete_objects",
        "description": "Delete one or more objects from the project.",
        "parameters": {
            "type": "object",
            "properties": {
                "objects": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["solid", "logical_volume", "physical_volume", "material", "define", "assembly"]},
                            "id": {"type": "string", "description": "The name or ID of the object."}
                        }
                    }
                }
            },
            "required": ["objects"]
        }
    },
    {
        "name": "run_simulation",
        "description": "Start a Geant4 simulation run to test the current geometry.",
        "parameters": {
            "type": "object",
            "properties": {
                "events": {"type": "integer", "description": "Number of events to simulate (default: 1000)."},
                "threads": {"type": "integer", "description": "Number of CPU threads (default: 1)."}
            }
        }
    },
    {
        "name": "get_simulation_status",
        "description": "Check the status of a previously started simulation job.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The unique ID of the simulation job."}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_analysis_summary",
        "description": "Get a physics-based summary of the simulation results (energy peaks, hit counts, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The unique ID of the simulation job."}
            },
            "required": ["job_id"]
        }
    }
]
