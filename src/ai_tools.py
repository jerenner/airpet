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



# Canonical primitive-solid parameter specs (source of truth for AI schema + backend validation).
def _expr_param(description: str) -> Dict[str, Any]:
    # Keep Gemini-compatible primitive schema types: expression fields are represented as strings.
    return {
        "type": "string",
        "description": f"{description}. Use numeric strings or expressions (e.g., '42', 'radius+5', '360*deg')."
    }


def _int_or_expr_param(description: str) -> Dict[str, Any]:
    # Integer-or-expression fields are represented as strings for cross-provider compatibility.
    return {
        "type": "string",
        "description": f"{description}. Use integer-like strings or expressions."
    }


PRIMITIVE_SOLID_PARAM_SPECS: Dict[str, Dict[str, Any]] = {
    "box": {
        "required": ["x", "y", "z"],
        "properties": {
            "x": _expr_param("Full X length (mm)"),
            "y": _expr_param("Full Y length (mm)"),
            "z": _expr_param("Full Z length (mm)")
        }
    },
    "tube": {
        "required": ["rmin", "rmax", "z", "startphi", "deltaphi"],
        "properties": {
            "rmin": _expr_param("Inner radius (mm)"),
            "rmax": _expr_param("Outer radius (mm)"),
            "z": _expr_param("Half-length in Z (mm)"),
            "startphi": _expr_param("Start angle (e.g., 0*deg)"),
            "deltaphi": _expr_param("Span angle (e.g., 360*deg)")
        }
    },
    "cone": {
        "required": ["rmin1", "rmax1", "rmin2", "rmax2", "z", "startphi", "deltaphi"],
        "properties": {
            "rmin1": _expr_param("Inner radius at -Z side (mm)"),
            "rmax1": _expr_param("Outer radius at -Z side (mm)"),
            "rmin2": _expr_param("Inner radius at +Z side (mm)"),
            "rmax2": _expr_param("Outer radius at +Z side (mm)"),
            "z": _expr_param("Half-length in Z (mm)"),
            "startphi": _expr_param("Start angle (e.g., 0*deg)"),
            "deltaphi": _expr_param("Span angle (e.g., 360*deg)")
        }
    },
    "sphere": {
        "required": ["rmin", "rmax", "startphi", "deltaphi", "starttheta", "deltatheta"],
        "properties": {
            "rmin": _expr_param("Inner radius (mm)"),
            "rmax": _expr_param("Outer radius (mm)"),
            "startphi": _expr_param("Start azimuth angle"),
            "deltaphi": _expr_param("Azimuth span angle"),
            "starttheta": _expr_param("Start polar angle"),
            "deltatheta": _expr_param("Polar span angle")
        }
    },
    "orb": {
        "required": ["r"],
        "properties": {
            "r": _expr_param("Outer radius (mm)")
        }
    },
    "trd": {
        "required": ["x1", "x2", "y1", "y2", "z"],
        "properties": {
            "x1": _expr_param("X length at -Z side (mm)"),
            "x2": _expr_param("X length at +Z side (mm)"),
            "y1": _expr_param("Y length at -Z side (mm)"),
            "y2": _expr_param("Y length at +Z side (mm)"),
            "z": _expr_param("Full Z length (mm)")
        }
    },
    "para": {
        "required": ["x", "y", "z", "alpha", "theta", "phi"],
        "properties": {
            "x": _expr_param("Full X length (mm)"),
            "y": _expr_param("Full Y length (mm)"),
            "z": _expr_param("Full Z length (mm)"),
            "alpha": _expr_param("Alpha angle"),
            "theta": _expr_param("Theta angle"),
            "phi": _expr_param("Phi angle")
        }
    },
    "trap": {
        "required": ["z", "theta", "phi", "y1", "x1", "x2", "alpha1", "y2", "x3", "x4", "alpha2"],
        "properties": {
            "z": _expr_param("Full Z length (mm)"),
            "theta": _expr_param("Theta angle"),
            "phi": _expr_param("Phi angle"),
            "y1": _expr_param("Y length at -Z side (mm)"),
            "x1": _expr_param("X1 at -Z side (mm)"),
            "x2": _expr_param("X2 at -Z side (mm)"),
            "alpha1": _expr_param("Alpha1 angle"),
            "y2": _expr_param("Y length at +Z side (mm)"),
            "x3": _expr_param("X3 at +Z side (mm)"),
            "x4": _expr_param("X4 at +Z side (mm)"),
            "alpha2": _expr_param("Alpha2 angle")
        }
    },
    "hype": {
        "required": ["rmin", "rmax", "inst", "outst", "z"],
        "properties": {
            "rmin": _expr_param("Inner radius at z=0 (mm)"),
            "rmax": _expr_param("Outer radius at z=0 (mm)"),
            "inst": _expr_param("Inner stereo angle"),
            "outst": _expr_param("Outer stereo angle"),
            "z": _expr_param("Half-length in Z (mm)")
        }
    },
    "twistedbox": {
        "required": ["x", "y", "z", "PhiTwist"],
        "properties": {
            "x": _expr_param("Full X length (mm)"),
            "y": _expr_param("Full Y length (mm)"),
            "z": _expr_param("Full Z length (mm)"),
            "PhiTwist": _expr_param("Twist angle")
        }
    },
    "twistedtrd": {
        "required": ["x1", "x2", "y1", "y2", "z", "PhiTwist"],
        "properties": {
            "x1": _expr_param("X length at -Z side (mm)"),
            "x2": _expr_param("X length at +Z side (mm)"),
            "y1": _expr_param("Y length at -Z side (mm)"),
            "y2": _expr_param("Y length at +Z side (mm)"),
            "z": _expr_param("Full Z length (mm)"),
            "PhiTwist": _expr_param("Twist angle")
        }
    },
    "twistedtrap": {
        "required": ["PhiTwist", "z", "Theta", "Phi", "y1", "x1", "x2", "y2", "x3", "x4", "Alph"],
        "properties": {
            "PhiTwist": _expr_param("Twist angle"),
            "z": _expr_param("Full Z length (mm)"),
            "Theta": _expr_param("Theta angle"),
            "Phi": _expr_param("Phi angle"),
            "y1": _expr_param("Y length at -Z side (mm)"),
            "x1": _expr_param("X1 at -Z side (mm)"),
            "x2": _expr_param("X2 at -Z side (mm)"),
            "y2": _expr_param("Y length at +Z side (mm)"),
            "x3": _expr_param("X3 at +Z side (mm)"),
            "x4": _expr_param("X4 at +Z side (mm)"),
            "Alph": _expr_param("Alpha angle")
        }
    },
    "twistedtubs": {
        "required": ["twistedangle", "endinnerrad", "endouterrad", "zlen", "phi"],
        "properties": {
            "twistedangle": _expr_param("Twist angle"),
            "endinnerrad": _expr_param("Inner radius at endcaps (mm)"),
            "endouterrad": _expr_param("Outer radius at endcaps (mm)"),
            "zlen": _expr_param("Full Z length (mm)"),
            "phi": _expr_param("Angular span")
        }
    },
    "genericPolycone": {
        "required": ["startphi", "deltaphi", "rzpoints"],
        "properties": {
            "startphi": _expr_param("Start angle"),
            "deltaphi": _expr_param("Span angle"),
            "rzpoints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "r": _expr_param("Radius at point"),
                        "z": _expr_param("Z coordinate at point")
                    },
                    "required": ["r", "z"]
                }
            }
        }
    },
    "genericPolyhedra": {
        "required": ["startphi", "deltaphi", "numsides", "rzpoints"],
        "properties": {
            "startphi": _expr_param("Start angle"),
            "deltaphi": _expr_param("Span angle"),
            "numsides": _int_or_expr_param("Number of polygon sides"),
            "rzpoints": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "r": _expr_param("Radius at point"),
                        "z": _expr_param("Z coordinate at point")
                    },
                    "required": ["r", "z"]
                }
            }
        }
    },
    "xtru": {
        "required": ["twoDimVertices", "sections"],
        "properties": {
            "twoDimVertices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "x": _expr_param("2D vertex X"),
                        "y": _expr_param("2D vertex Y")
                    },
                    "required": ["x", "y"]
                }
            },
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "zOrder": _int_or_expr_param("Section order index"),
                        "zPosition": _expr_param("Section Z position"),
                        "xOffset": _expr_param("Section X offset"),
                        "yOffset": _expr_param("Section Y offset"),
                        "scalingFactor": _expr_param("Section scale factor")
                    },
                    "required": ["zOrder", "zPosition", "xOffset", "yOffset", "scalingFactor"]
                }
            }
        }
    }
}


def _build_create_primitive_solid_parameters() -> Dict[str, Any]:
    solid_types = list(PRIMITIVE_SOLID_PARAM_SPECS.keys())

    # Gemini's function schema validator rejects JSON-schema combinators like oneOf/anyOf.
    # We keep discriminated requirements in PRIMITIVE_SOLID_PARAM_SPECS (validated server-side)
    # and expose a comprehensive canonical param catalog here for model guidance.
    all_param_props: Dict[str, Any] = {}
    for spec in PRIMITIVE_SOLID_PARAM_SPECS.values():
        for param_name, param_schema in spec.get("properties", {}).items():
            if param_name not in all_param_props:
                all_param_props[param_name] = param_schema

    required_by_type = "; ".join(
        [f"{solid}: {spec.get('required', [])}" for solid, spec in PRIMITIVE_SOLID_PARAM_SPECS.items()]
    )

    return {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "solid_type": {"type": "string", "enum": solid_types},
            "params": {
                "type": "object",
                "properties": all_param_props,
                "description": (
                    "Canonical GDML-style params for the selected solid_type. "
                    f"Required keys by solid_type: {required_by_type}"
                )
            }
        },
        "required": ["name", "solid_type", "params"]
    }


def _create_primitive_solid_tool() -> Dict[str, Any]:
    return {
        "name": "create_primitive_solid",
        "description": (
            "Create a new primitive shape. "
            "Use canonical GDML-style parameter names from the schema for the selected solid_type."
        ),
        "parameters": _build_create_primitive_solid_parameters()
    }

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
    _create_primitive_solid_tool(),
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
        "description": "Create or update a logical volume (binds a solid to a material and sets visual appearance).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "solid_ref": {"type": "string"},
                "material_ref": {"type": "string"},
                "is_sensitive": {"type": "boolean"},
                "color": {"type": "string", "description": "Hex color string (e.g., '#0000ff' for blue) or CSS color name."},
                "opacity": {"type": "number", "description": "Opacity from 0.0 (transparent) to 1.0 (opaque)."}
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
        "name": "set_volume_appearance",
        "description": "Set the visual color and opacity of a logical volume.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "The name of the logical volume."},
                "color": {"type": "string", "description": "Hex color string or common name (blue, red, lead, etc.)."},
                "opacity": {"type": "number", "description": "Opacity from 0.0 to 1.0."}
            },
            "required": ["name", "color"]
        }
    },
    {
        "name": "delete_detector_ring",
        "description": "Delete all instances of a detector ring by its name.",
        "parameters": {
            "type": "object",
            "properties": {
                "ring_name": {"type": "string", "description": "The base name of the ring to delete (e.g., 'PET_ring')."}
            },
            "required": ["ring_name"]
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
    },
    {
        "name": "batch_geometry_update",
        "description": "Execute multiple geometry operations in a single high-efficiency batch. Use this when you have many objects to create or modify at once.",
        "parameters": {
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool_name": {"type": "string", "description": "Name of the tool to call."},
                            "arguments": {"type": "object", "description": "Arguments for that tool."}
                        }
                    }
                }
            },
            "required": ["operations"]
        }
    },
    {
        "name": "insert_physics_template",
        "description": "Insert a pre-defined high-level physics component (like a SiPM array, cryostat, or phantom).",
        "parameters": {
            "type": "object",
            "properties": {
                "template_name": {"type": "string", "enum": ["sipm_array", "cryostat", "phantom"]},
                "params": {"type": "object", "description": "Parameters for the chosen template."},
                "parent_lv_name": {"type": "string", "description": "Which volume to place the component into."},
                "position": {"type": "object", "description": "Relative position of the whole component {'x':..., 'y':..., 'z':...}"}
            },
            "required": ["template_name", "params", "parent_lv_name"]
        }
    },
    {
        "name": "manage_optical_surface",
        "description": "Create or update an optical surface (properties for mirrors, scintillators, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "model": {"type": "string", "enum": ["glisur", "unified"]},
                "finish": {"type": "string", "enum": ["polished", "polishedfrontpainted", "polishedbackpainted", "ground", "groundfrontpainted", "groundbackpainted"]},
                "type": {"type": "string", "enum": ["dielectric_metal", "dielectric_dielectric", "dielectric_LUT", "firsov", "x_ray"]},
                "value": {"type": "string", "description": "Surface property value (e.g., sigma alpha)."},
                "properties": {"type": "object", "description": "Optical properties (REFLECTIVITY, RINDEX, etc.) as name-value or name-array pairs."}
            },
            "required": ["name"]
        }
    },
    {
        "name": "manage_surface_link",
        "description": "Link an optical surface to a volume (Skin Surface) or an interface between two volumes (Border Surface).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "surface_ref": {"type": "string", "description": "Name of the optical surface to apply."},
                "link_type": {"type": "string", "enum": ["skin", "border"]},
                "volume_ref": {"type": "string", "description": "For 'skin' type: the logical volume name."},
                "pv1_id": {"type": "string", "description": "For 'border' type: the first physical volume ID."},
                "pv2_id": {"type": "string", "description": "For 'border' type: the second physical volume ID."}
            },
            "required": ["name", "surface_ref", "link_type"]
        }
    },
    {
        "name": "manage_assembly",
        "description": "Create or update an assembly (a reusable group of placements).",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "placements": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "volume_ref": {"type": "string"},
                            "position": {"type": "object"},
                            "rotation": {"type": "object"},
                            "copy_number": {"type": "integer"}
                        }
                    }
                }
            },
            "required": ["name", "placements"]
        }
    },
    {
        "name": "manage_ui_group",
        "description": "Organize project components into visual groups in the UI.",
        "parameters": {
            "type": "object",
            "properties": {
                "group_type": {"type": "string", "enum": ["solid", "logical_volume", "material", "assembly", "define"]},
                "group_name": {"type": "string"},
                "item_ids": {"type": "array", "items": {"type": "string"}, "description": "List of component names/IDs to move to this group."},
                "action": {"type": "string", "enum": ["create", "add_items", "remove_group"]}
            },
            "required": ["group_type", "group_name", "action"]
        }
    },
    {
        "name": "evaluate_expression",
        "description": "Evaluate a mathematical expression or check a variable value.",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"}
            },
            "required": ["expression"]
        }
    },
    {
        "name": "manage_particle_source",
        "description": "Create or update a particle source (GPS commands, transform, activity, confinement).",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "update", "update_transform"]},
                "source_id": {"type": "string", "description": "Required for update/update_transform."},
                "name": {"type": "string"},
                "gps_commands": {"type": "object"},
                "position": {"type": "object"},
                "rotation": {"type": "object"},
                "activity": {"type": "number"},
                "confine_to_pv": {"type": "string"},
                "volume_link_id": {"type": "string"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "set_active_source",
        "description": "Activate/deactivate a source by id, or clear all active sources by passing null/empty source_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string"}
            }
        }
    },
    {
        "name": "process_lors",
        "description": "Process simulation hits into coincidence LORs for PET reconstruction.",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"},
                "coincidence_window_ns": {"type": "number"},
                "energy_cut": {"type": "number"},
                "energy_resolution": {"type": "number"},
                "position_resolution": {"type": "object"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_lor_status",
        "description": "Get status/progress of a background LOR processing job.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "check_lor_file",
        "description": "Check whether a processed LOR file exists for a run and return metadata if available.",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "run_reconstruction",
        "description": "Run PET image reconstruction from LORs (MLEM + optional normalization/attenuation correction).",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"},
                "iterations": {"type": "integer"},
                "image_size": {"type": "array", "items": {"type": "integer"}},
                "voxel_size": {"type": "array", "items": {"type": "number"}},
                "normalization": {"type": "boolean"},
                "ac_enabled": {"type": "boolean"},
                "ac_shape": {"type": "string", "enum": ["cylinder"]},
                "ac_radius": {"type": "number"},
                "ac_length": {"type": "number"},
                "ac_mu": {"type": "number"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "compute_sensitivity",
        "description": "Compute/store a Monte Carlo sensitivity matrix for a run.",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"},
                "voxel_size": {"type": "number"},
                "matrix_size": {"type": "integer"},
                "ac_enabled": {"type": "boolean"},
                "ac_mu": {"type": "number"},
                "ac_radius": {"type": "number"},
                "num_random_lors": {"type": "integer"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_sensitivity_status",
        "description": "Check if a sensitivity matrix exists for a run.",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "stop_simulation",
        "description": "Stop a running Geant4 simulation job.",
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_simulation_metadata",
        "description": "Fetch metadata for a simulation run (job config, paths, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "get_simulation_analysis",
        "description": "Fetch rich analysis outputs (spectra, heatmaps, volume/particle breakdown).",
        "parameters": {
            "type": "object",
            "properties": {
                "version_id": {"type": "string"},
                "job_id": {"type": "string"},
                "energy_bins": {"type": "integer"},
                "spatial_bins": {"type": "integer"}
            },
            "required": ["job_id"]
        }
    },
    {
        "name": "rename_ui_group",
        "description": "Rename an existing UI group.",
        "parameters": {
            "type": "object",
            "properties": {
                "group_type": {"type": "string", "enum": ["solid", "logical_volume", "material", "assembly", "define"]},
                "old_name": {"type": "string"},
                "new_name": {"type": "string"}
            },
            "required": ["group_type", "old_name", "new_name"]
        }
    }
]
